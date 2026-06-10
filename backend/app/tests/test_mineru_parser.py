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
