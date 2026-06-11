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
from app.services.parser.base import ParsedBlock, ParseResult
from app.services.parser.libreoffice_converter import convert_doc_to_docx, convert_doc_to_pdf

_mineru_lock = Lock()


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

    def parse(self, path: Path) -> ParseResult:
        source = self._prepare_source(path)
        if isinstance(source, ParseResult):
            return source

        command_path = self._resolve_command_path()
        if not command_path:
            return ParseResult(
                status="need_review",
                error_message=(
                    "MinerU unavailable：未找到 mineru 命令。请先安装 MinerU，例如 "
                    'uv pip install -U "mineru[all]"，然后重新入库。'
                ),
                metadata={"provider": "mineru", "command": self.settings.mineru_command},
            )

        output_root = Path(self.settings.mineru_output_dir)
        output_root.mkdir(parents=True, exist_ok=True)
        command = [
            command_path,
            "-p",
            str(source),
            "-o",
            str(output_root),
            "-b",
            self.settings.mineru_backend,
        ]
        run = self._run_mineru(command)
        run_metadata = {
            "provider": "mineru",
            "command": command,
            "elapsed_seconds": round(run.elapsed_seconds, 2),
            "stdout_tail": self._tail(run.stdout),
            "stderr_tail": self._tail(run.stderr),
        }
        if run.timed_out:
            return ParseResult(
                status="need_review",
                error_message=f"MinerU 解析超过 {self.settings.mineru_timeout} 秒，已停止后台进程。",
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

    def _run_mineru(self, command: list[str]) -> MinerURunResult:
        with _mineru_lock:
            started = monotonic()
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            try:
                stdout, stderr = process.communicate(timeout=self.settings.mineru_timeout)
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
