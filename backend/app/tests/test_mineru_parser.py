import subprocess
import sys
from pathlib import Path

from app.core.config import Settings
from app.services.parser.document_parser import DocumentParser
from app.services.parser.mineru_parser import MinerUParser, MinerURunResult


def test_document_parser_requires_mineru_when_configured(tmp_path: Path):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%fake")
    settings = Settings(
        document_parser_provider="mineru",
        mineru_command="definitely-not-installed-mineru",
    )

    result = DocumentParser(settings=settings).parse(pdf)

    assert result.status == "need_review"
    assert "MinerU" in result.error_message
    assert result.blocks == []


def test_mineru_parser_converts_doc_to_pdf_source(tmp_path: Path, monkeypatch):
    source = tmp_path / "legacy.doc"
    source.write_bytes(b"fake legacy word")
    converted = tmp_path / "legacy.pdf"
    converted.write_bytes(b"%PDF-1.4")

    def fake_convert_doc_to_pdf(path: Path) -> Path:
        assert path == source
        return converted

    monkeypatch.setattr("app.services.parser.mineru_parser.convert_doc_to_pdf", fake_convert_doc_to_pdf)

    prepared = MinerUParser()._prepare_source(source)

    assert prepared == converted


def test_mineru_parser_resolves_command_from_virtualenv_bin_when_path_missing(tmp_path: Path, monkeypatch):
    venv = tmp_path / "venv"
    command = venv / "bin" / "mineru"
    command.parent.mkdir(parents=True)
    command.write_text("#!/bin/sh\n", encoding="utf-8")
    command.chmod(0o755)
    monkeypatch.setattr("app.services.parser.mineru_parser.shutil.which", lambda _: None)
    monkeypatch.setattr(sys, "prefix", str(venv))

    resolved = MinerUParser(Settings(mineru_command="mineru"))._resolve_command_path()

    assert resolved == str(command)


def test_mineru_timeout_zero_disables_subprocess_timeout():
    parser = MinerUParser(Settings(mineru_timeout=0))

    assert parser._communicate_timeout() is None


def test_mineru_markdown_to_blocks_groups_html_table():
    markdown = "\n".join(
        [
            "# 预算执行表",
            "<table>",
            "  <tr><th><p>项目</p></th><th><p>执行率</p></th></tr>",
            "  <tr><td><p>A项目</p></td><td><p>82%</p></td></tr>",
            "</table>",
            "表后说明：低于 85% 需要专项说明。",
        ]
    )

    blocks = MinerUParser()._markdown_to_blocks(markdown)

    assert [block.block_type for block in blocks] == ["heading", "table", "paragraph"]
    assert blocks[1].heading_path == "预算执行表"
    assert "<table>" in blocks[1].text
    assert "A项目" in blocks[1].text


def test_mineru_parser_runs_large_pdf_in_page_batches(tmp_path: Path, monkeypatch):
    source = tmp_path / "large.pdf"
    source.write_bytes(b"%PDF-1.4")
    output_root = tmp_path / "mineru-output"
    parser = MinerUParser(
        Settings(
            mineru_command="mineru",
            mineru_output_dir=output_root,
            mineru_page_batch_size=10,
        )
    )
    commands: list[list[str]] = []
    monkeypatch.setattr(parser, "_resolve_command_path", lambda: "/usr/bin/mineru")
    monkeypatch.setattr(parser, "_pdf_page_count", lambda _: 23)

    def fake_run(command: list[str]) -> MinerURunResult:
        commands.append(command)
        start = int(command[command.index("-s") + 1])
        end = int(command[command.index("-e") + 1])
        batch_root = Path(command[command.index("-o") + 1])
        markdown = batch_root / source.stem / "auto" / f"{source.stem}.md"
        markdown.parent.mkdir(parents=True)
        markdown.write_text(f"第{start + 1}页到第{end + 1}页内容。", encoding="utf-8")
        completed = subprocess.CompletedProcess(command, 0, "", "")
        return MinerURunResult(completed=completed, timed_out=False, stdout="", stderr="", elapsed_seconds=1.0)

    monkeypatch.setattr(parser, "_run_mineru", fake_run)

    result = parser.parse(source)

    assert result.status == "ready"
    assert [command[command.index("-s") + 1 : command.index("-s") + 4 : 2] for command in commands] == [
        ["0", "9"],
        ["10", "19"],
        ["20", "22"],
    ]
    assert "第1页到第10页内容。" in result.text
    assert "第21页到第23页内容。" in result.text
    assert result.metadata["completed_page_batches"] == ["1-10", "11-20", "21-23"]


def test_mineru_parser_reports_pdf_batch_progress(tmp_path: Path, monkeypatch):
    source = tmp_path / "large.pdf"
    source.write_bytes(b"%PDF-1.4")
    output_root = tmp_path / "mineru-output"
    parser = MinerUParser(
        Settings(
            mineru_command="mineru",
            mineru_output_dir=output_root,
            mineru_page_batch_size=10,
        )
    )
    progress_events: list[dict] = []
    monkeypatch.setattr(parser, "_resolve_command_path", lambda: "/usr/bin/mineru")
    monkeypatch.setattr(parser, "_pdf_page_count", lambda _: 23)

    def fake_run(command: list[str]) -> MinerURunResult:
        start = int(command[command.index("-s") + 1])
        end = int(command[command.index("-e") + 1])
        batch_root = Path(command[command.index("-o") + 1])
        markdown = batch_root / source.stem / "auto" / f"{source.stem}.md"
        markdown.parent.mkdir(parents=True)
        markdown.write_text(f"第{start + 1}页到第{end + 1}页内容。", encoding="utf-8")
        completed = subprocess.CompletedProcess(command, 0, "", "")
        return MinerURunResult(completed=completed, timed_out=False, stdout="", stderr="", elapsed_seconds=1.0)

    monkeypatch.setattr(parser, "_run_mineru", fake_run)

    parser.parse(source, progress_callback=progress_events.append)

    assert [event["completed_pages"] for event in progress_events] == [10, 20, 23]
    assert [event["progress_percent"] for event in progress_events] == [43, 87, 100]
    assert progress_events[-1]["progress_stage"] == "解析中（23/23 页）"


def test_mineru_parser_keeps_completed_pdf_batches_when_later_batch_fails(tmp_path: Path, monkeypatch):
    source = tmp_path / "large.pdf"
    source.write_bytes(b"%PDF-1.4")
    output_root = tmp_path / "mineru-output"
    parser = MinerUParser(
        Settings(
            mineru_command="mineru",
            mineru_output_dir=output_root,
            mineru_page_batch_size=10,
        )
    )
    monkeypatch.setattr(parser, "_resolve_command_path", lambda: "/usr/bin/mineru")
    monkeypatch.setattr(parser, "_pdf_page_count", lambda _: 21)

    def fake_run(command: list[str]) -> MinerURunResult:
        start = int(command[command.index("-s") + 1])
        end = int(command[command.index("-e") + 1])
        if start == 10:
            completed = subprocess.CompletedProcess(command, 1, "", "batch failed")
            return MinerURunResult(
                completed=completed,
                timed_out=False,
                stdout="",
                stderr="batch failed",
                elapsed_seconds=1.0,
            )
        batch_root = Path(command[command.index("-o") + 1])
        markdown = batch_root / source.stem / "auto" / f"{source.stem}.md"
        markdown.parent.mkdir(parents=True)
        markdown.write_text(f"第{start + 1}页到第{end + 1}页内容。", encoding="utf-8")
        completed = subprocess.CompletedProcess(command, 0, "", "")
        return MinerURunResult(completed=completed, timed_out=False, stdout="", stderr="", elapsed_seconds=1.0)

    monkeypatch.setattr(parser, "_run_mineru", fake_run)

    result = parser.parse(source)

    assert result.status == "need_review"
    assert "第1页到第10页内容。" in result.text
    assert "第11页" not in result.text
    assert "第 11-20 页" in result.error_message
    assert result.blocks


def test_mineru_parser_reuses_cached_pdf_batch_markdown(tmp_path: Path, monkeypatch):
    source = tmp_path / "large.pdf"
    source.write_bytes(b"%PDF-1.4")
    output_root = tmp_path / "mineru-output"
    parser = MinerUParser(
        Settings(
            mineru_command="mineru",
            mineru_output_dir=output_root,
            mineru_page_batch_size=10,
        )
    )
    monkeypatch.setattr(parser, "_resolve_command_path", lambda: "/usr/bin/mineru")
    monkeypatch.setattr(parser, "_pdf_page_count", lambda _: 11)
    cached_root = parser._batch_output_root(output_root, source, 0, 9)
    cached_markdown = cached_root / source.stem / "auto" / f"{source.stem}.md"
    cached_markdown.parent.mkdir(parents=True)
    cached_markdown.write_text("缓存的第1页到第10页内容。", encoding="utf-8")
    commands: list[list[str]] = []

    def fake_run(command: list[str]) -> MinerURunResult:
        commands.append(command)
        start = int(command[command.index("-s") + 1])
        end = int(command[command.index("-e") + 1])
        batch_root = Path(command[command.index("-o") + 1])
        markdown = batch_root / source.stem / "auto" / f"{source.stem}.md"
        markdown.parent.mkdir(parents=True)
        markdown.write_text(f"新解析第{start + 1}页到第{end + 1}页内容。", encoding="utf-8")
        completed = subprocess.CompletedProcess(command, 0, "", "")
        return MinerURunResult(completed=completed, timed_out=False, stdout="", stderr="", elapsed_seconds=1.0)

    monkeypatch.setattr(parser, "_run_mineru", fake_run)

    result = parser.parse(source)

    assert result.status == "ready"
    assert len(commands) == 1
    assert commands[0][commands[0].index("-s") + 1] == "10"
    assert "缓存的第1页到第10页内容。" in result.text
    assert "新解析第11页到第11页内容。" in result.text
