import hashlib
import os
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from time import monotonic

from app.core.config import Settings, get_settings
from app.services.parser.base import ParsedBlock, ParseResult, ProgressCallback
from app.services.parser.libreoffice_converter import convert_doc_to_docx, convert_doc_to_pdf
from app.services.parser.progress import progress_for_status

_mineru_lock = Lock()
MINERU_CAPABILITIES = ["版面分析", "表格结构识别", "图片/扫描件 OCR 文字识别", "公式/印章等视觉元素检测"]


@dataclass
class MinerURunResult:
    completed: subprocess.CompletedProcess | None
    timed_out: bool
    stdout: str
    stderr: str
    elapsed_seconds: float


class MinerUParser:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def parse(self, path: Path, progress_callback: ProgressCallback | None = None) -> ParseResult:
        source = self._prepare_source(path)
        if isinstance(source, ParseResult):
            return source

        progress_metadata = self.progress_metadata(path)
        command_path = self._resolve_command_path()
        if not command_path:
            return ParseResult(
                status="need_review",
                error_message=(
                    "MinerU unavailable：未找到 mineru 命令。请先安装 MinerU，例如 "
                    'uv pip install -U "mineru[all]"，然后重新入库。'
                ),
                metadata={**progress_metadata, "command": self.settings.mineru_command},
            )

        output_root = Path(self.settings.mineru_output_dir)
        output_root.mkdir(parents=True, exist_ok=True)
        if source.suffix.lower() == ".pdf" and int(self.settings.mineru_page_batch_size or 0) > 0:
            return self._parse_pdf_in_batches(source, command_path, output_root, progress_metadata, progress_callback)

        return self._parse_single_source(source, command_path, output_root, progress_metadata)

    def _parse_single_source(
        self,
        source: Path,
        command_path: str,
        output_root: Path,
        progress_metadata: dict,
        extra_args: list[str] | None = None,
    ) -> ParseResult:
        command = [
            command_path,
            "-p",
            str(source),
            "-o",
            str(output_root),
            "-b",
            self.settings.mineru_backend,
        ]
        if extra_args:
            command.extend(extra_args)
        run = self._run_mineru(command)
        run_metadata = {
            **progress_metadata,
            "provider": "mineru",
            "command": command,
            "elapsed_seconds": round(run.elapsed_seconds, 2),
            "stdout_tail": self._tail(run.stdout),
            "stderr_tail": self._tail(run.stderr),
        }
        if run.timed_out:
            return ParseResult(
                status="need_review",
                error_message=(
                    f"MinerU 解析超过 {self.settings.mineru_timeout} 秒，已停止后台进程。"
                    "将 MINERU_TIMEOUT 设为 0 可禁用超时。"
                ),
                metadata=run_metadata,
            )

        completed = run.completed
        if completed is None:
            return ParseResult(
                status="need_review",
                error_message="MinerU 解析进程异常结束。",
                metadata=run_metadata,
            )
        if completed.returncode != 0:
            return ParseResult(
                status="need_review",
                error_message=f"MinerU 解析失败：{self._tail(completed.stderr or completed.stdout, 500)}",
                metadata=run_metadata,
            )

        markdown = self._find_latest_markdown(output_root, source)
        if not markdown:
            return ParseResult(
                status="need_review",
                error_message="MinerU 已运行但未找到 Markdown 输出，请检查 MinerU 输出目录。",
                metadata={**run_metadata, "output_root": str(output_root)},
            )

        text = markdown.read_text(encoding="utf-8", errors="ignore").strip()
        blocks = self._markdown_to_blocks(text)
        return ParseResult(
            status="ready",
            blocks=blocks,
            text=text,
            metadata={**run_metadata, "markdown_path": str(markdown)},
        )

    def _parse_pdf_in_batches(
        self,
        source: Path,
        command_path: str,
        output_root: Path,
        progress_metadata: dict,
        progress_callback: ProgressCallback | None,
    ) -> ParseResult:
        page_count = self._pdf_page_count(source)
        batch_size = max(1, int(self.settings.mineru_page_batch_size or 10))
        texts: list[str] = []
        page_batches: list[dict] = []
        total_elapsed = 0.0
        cache_key = self._source_cache_key(source)

        for start in range(0, page_count, batch_size):
            end = min(page_count - 1, start + batch_size - 1)
            batch_label = f"{start + 1}-{end + 1}"
            batch_output_root = self._batch_output_root(output_root, source, start, end, cache_key=cache_key)
            batch_output_root.mkdir(parents=True, exist_ok=True)
            markdown = self._find_latest_markdown(batch_output_root, source)
            batch_status = "cached"
            batch_metadata: dict = {
                "page_batch": batch_label,
                "page_start": start + 1,
                "page_end": end + 1,
            }

            if not self._usable_markdown(markdown):
                batch_status = "parsed"
                result = self._parse_single_source(
                    source,
                    command_path,
                    batch_output_root,
                    progress_metadata,
                    extra_args=["-s", str(start), "-e", str(end)],
                )
                total_elapsed += float(result.metadata.get("elapsed_seconds") or 0)
                batch_metadata.update(
                    {
                        "command": result.metadata.get("command"),
                        "elapsed_seconds": result.metadata.get("elapsed_seconds"),
                        "stdout_tail": result.metadata.get("stdout_tail"),
                        "stderr_tail": result.metadata.get("stderr_tail"),
                    }
                )
                if result.status != "ready":
                    page_batches.append({**batch_metadata, "status": result.status})
                    return self._partial_batch_result(
                        source=source,
                        status="need_review",
                        error_message=f"MinerU 第 {batch_label} 页解析失败：{result.error_message}",
                        texts=texts,
                        progress_metadata=progress_metadata,
                        page_batches=page_batches,
                        page_count=page_count,
                        total_elapsed=total_elapsed,
                    )
                markdown = Path(result.metadata["markdown_path"]) if result.metadata.get("markdown_path") else None

            if not self._usable_markdown(markdown):
                page_batches.append({**batch_metadata, "status": "need_review"})
                return self._partial_batch_result(
                    source=source,
                    status="need_review",
                    error_message=f"MinerU 第 {batch_label} 页解析后未找到 Markdown 输出。",
                    texts=texts,
                    progress_metadata=progress_metadata,
                    page_batches=page_batches,
                    page_count=page_count,
                    total_elapsed=total_elapsed,
                )

            assert markdown is not None
            text = markdown.read_text(encoding="utf-8", errors="ignore").strip()
            texts.append(text)
            page_batches.append(
                {
                    **batch_metadata,
                    "status": batch_status,
                    "markdown_path": str(markdown),
                    "blocks": len(self._markdown_to_blocks(text)),
                    "text_chars": len(text),
                }
            )
            self._emit_batch_progress(
                progress_callback,
                page_count=page_count,
                completed_pages=end + 1,
                page_batch=batch_label,
                page_batches=page_batches,
            )

        combined_text = "\n\n".join(texts).strip()
        return ParseResult(
            status="ready",
            blocks=self._markdown_to_blocks(combined_text),
            text=combined_text,
            metadata=self._batch_metadata(
                source=source,
                progress_metadata=progress_metadata,
                page_batches=page_batches,
                page_count=page_count,
                total_elapsed=total_elapsed,
            ),
        )

    def _run_mineru(self, command: list[str]) -> MinerURunResult:
        with _mineru_lock:
            started = monotonic()
            timeout = self._communicate_timeout()
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                self._stop_process_group(process)
                stdout, stderr = process.communicate()
                return MinerURunResult(
                    completed=None,
                    timed_out=True,
                    stdout=stdout,
                    stderr=stderr,
                    elapsed_seconds=monotonic() - started,
                )
            finally:
                if process.poll() is not None:
                    self._stop_process_group(process)
            completed = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
            return MinerURunResult(
                completed=completed,
                timed_out=False,
                stdout=stdout,
                stderr=stderr,
                elapsed_seconds=monotonic() - started,
            )

    def _communicate_timeout(self) -> int | None:
        timeout = int(self.settings.mineru_timeout or 0)
        return timeout if timeout > 0 else None

    def progress_metadata(self, path: Path) -> dict:
        timeout = self._communicate_timeout()
        timeout_text = "无后端超时限制" if timeout is None else f"后端超时 {timeout} 秒"
        ext = path.suffix.lower().lstrip(".") or "unknown"
        batch_size = max(0, int(self.settings.mineru_page_batch_size or 0))
        batch_text = f"PDF 每 {batch_size} 页分段解析" if batch_size else "PDF 不分段解析"
        return {
            "provider": "mineru",
            "parser_provider": "mineru",
            "parser_backend": self.settings.mineru_backend,
            **progress_for_status("parsing"),
            "capabilities": MINERU_CAPABILITIES,
            "status_message": (
                "MinerU 正在解析：版面分析、表格结构识别、图片/扫描件 OCR 文字识别运行中；"
                "首次加载模型或大文件可能需要较长时间。"
            ),
            "parser_detail": f"文件类型：{ext}；能力：{'、'.join(MINERU_CAPABILITIES)}；{timeout_text}。",
            "parser_batch_detail": batch_text,
            "page_batch_size": batch_size,
            "timeout_seconds": timeout,
            "timeout_disabled": timeout is None,
        }

    def _stop_process_group(self, process: subprocess.Popen) -> None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        except PermissionError:
            return
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                return
            process.wait(timeout=5)

    def _tail(self, text: str, limit: int = 2000) -> str:
        return (text or "").strip()[-limit:]

    def _pdf_page_count(self, source: Path) -> int:
        import fitz

        with fitz.open(source) as document:
            return max(1, int(document.page_count))

    def _batch_output_root(
        self,
        output_root: Path,
        source: Path,
        start: int,
        end: int,
        cache_key: str | None = None,
    ) -> Path:
        return output_root / "pdf-batches" / (cache_key or self._source_cache_key(source)) / (
            f"pages-{start + 1:06d}-{end + 1:06d}"
        )

    def _source_cache_key(self, source: Path) -> str:
        digest = hashlib.sha256()
        with source.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _usable_markdown(self, markdown: Path | None) -> bool:
        return bool(markdown and markdown.exists() and markdown.stat().st_size > 0)

    def _partial_batch_result(
        self,
        source: Path,
        status: str,
        error_message: str,
        texts: list[str],
        progress_metadata: dict,
        page_batches: list[dict],
        page_count: int,
        total_elapsed: float,
    ) -> ParseResult:
        combined_text = "\n\n".join(texts).strip()
        return ParseResult(
            status=status,
            blocks=self._markdown_to_blocks(combined_text),
            text=combined_text,
            error_message=error_message,
            metadata=self._batch_metadata(
                source=source,
                progress_metadata=progress_metadata,
                page_batches=page_batches,
                page_count=page_count,
                total_elapsed=total_elapsed,
            ),
        )

    def _emit_batch_progress(
        self,
        progress_callback: ProgressCallback | None,
        page_count: int,
        completed_pages: int,
        page_batch: str,
        page_batches: list[dict],
    ) -> None:
        if not progress_callback:
            return
        completed_pages = max(0, min(page_count, completed_pages))
        percent = round((completed_pages / max(1, page_count)) * 100)
        progress_callback(
            {
                "progress_stage": f"解析中（{completed_pages}/{page_count} 页）",
                "progress_percent": percent,
                "progress_estimated": False,
                "status_message": f"MinerU 正在分段解析 PDF：已完成 {completed_pages}/{page_count} 页。",
                "page_count": page_count,
                "completed_pages": completed_pages,
                "current_page_batch": page_batch,
                "page_batch_size": max(1, int(self.settings.mineru_page_batch_size or 10)),
                "completed_page_batches": [
                    str(item["page_batch"])
                    for item in page_batches
                    if item.get("status") in {"cached", "parsed"}
                ],
            }
        )

    def _batch_metadata(
        self,
        source: Path,
        progress_metadata: dict,
        page_batches: list[dict],
        page_count: int,
        total_elapsed: float,
    ) -> dict:
        completed = [
            str(item["page_batch"])
            for item in page_batches
            if item.get("status") in {"cached", "parsed"}
        ]
        return {
            **progress_metadata,
            "provider": "mineru",
            "source_path": str(source),
            "page_count": page_count,
            "page_batch_size": max(1, int(self.settings.mineru_page_batch_size or 10)),
            "page_batches": page_batches,
            "completed_page_batches": completed,
            "elapsed_seconds": round(total_elapsed, 2),
        }

    def _prepare_source(self, path: Path) -> Path | ParseResult:
        ext = path.suffix.lower()
        if ext == ".doc":
            errors = []
            try:
                return convert_doc_to_pdf(path)
            except Exception as exc:
                errors.append(f"PDF 转换失败：{exc}")
            try:
                return convert_doc_to_docx(path)
            except Exception as exc:
                errors.append(f"DOCX 转换失败：{exc}")
                error_message = f".doc 转换失败，MinerU 无法处理：{'；'.join(errors)}"
                return ParseResult(status="need_review", error_message=error_message)
        if ext == ".xls":
            return ParseResult(status="need_review", error_message="MinerU 本地解析建议使用 .xlsx，请先转换后上传。")
        return path

    def _find_latest_markdown(self, output_root: Path, source: Path) -> Path | None:
        candidates = list(output_root.rglob("*.md"))
        if not candidates:
            return None
        source_stem = source.stem.lower()
        related = [candidate for candidate in candidates if source_stem in candidate.stem.lower()]
        pool = related or candidates
        return max(pool, key=lambda item: item.stat().st_mtime)

    def _markdown_to_blocks(self, text: str) -> list[ParsedBlock]:
        blocks: list[ParsedBlock] = []
        heading_stack: list[str] = []
        paragraph_index = 0
        lines = text.splitlines()
        line_index = 0
        while line_index < len(lines):
            raw = lines[line_index]
            line = raw.strip()
            if not line:
                line_index += 1
                continue
            if line.lower().startswith("<table"):
                table_lines = [raw.rstrip()]
                line_index += 1
                while line_index < len(lines):
                    table_lines.append(lines[line_index].rstrip())
                    if lines[line_index].strip().lower().endswith("</table>"):
                        break
                    line_index += 1
                blocks.append(
                    ParsedBlock(
                        text="\n".join(table_lines).strip(),
                        block_type="table",
                        heading_path="/".join(heading_stack) if heading_stack else None,
                        paragraph_index=paragraph_index,
                    )
                )
                paragraph_index += 1
                line_index += 1
                continue
            if line.startswith("#"):
                level = min(len(line) - len(line.lstrip("#")), 6)
                heading = line.lstrip("#").strip()
                heading_stack = heading_stack[: level - 1] + [heading]
                blocks.append(
                    ParsedBlock(
                        text=heading,
                        block_type="heading",
                        heading_path="/".join(heading_stack),
                        paragraph_index=paragraph_index,
                    )
                )
            else:
                blocks.append(
                    ParsedBlock(
                        text=line,
                        block_type="paragraph",
                        heading_path="/".join(heading_stack) if heading_stack else None,
                        paragraph_index=paragraph_index,
                    )
                )
            paragraph_index += 1
            line_index += 1
        return blocks

    def _resolve_command_path(self) -> str | None:
        command = str(self.settings.mineru_command or "").strip()
        if not command:
            return None
        if os.sep in command or (os.altsep and os.altsep in command):
            candidate = Path(command).expanduser()
            return str(candidate) if candidate.exists() and os.access(candidate, os.X_OK) else None

        resolved = shutil.which(command)
        if resolved:
            return resolved

        candidate_dirs = [
            Path(sys.prefix) / "bin",
            Path(sys.prefix) / "Scripts",
            Path(sys.executable).parent,
        ]
        for directory in candidate_dirs:
            candidate = directory / command
            if candidate.exists() and os.access(candidate, os.X_OK):
                return str(candidate)
        return None
