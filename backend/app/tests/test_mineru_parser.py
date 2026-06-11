import sys
from pathlib import Path

from app.core.config import Settings
from app.services.parser.document_parser import DocumentParser
from app.services.parser.mineru_parser import MinerUParser


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
