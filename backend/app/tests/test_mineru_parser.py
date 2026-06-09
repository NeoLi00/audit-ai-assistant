from pathlib import Path

from app.core.config import Settings
from app.services.parser.document_parser import DocumentParser


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

