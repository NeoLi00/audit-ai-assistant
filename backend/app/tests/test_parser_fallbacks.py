from pathlib import Path

from app.services.parser.image_ocr import ImageOCRParser


def test_image_ocr_marks_need_review_when_provider_unavailable(tmp_path: Path):
    image = tmp_path / "scan.png"
    image.write_bytes(b"not-a-real-image")

    parser = ImageOCRParser(force_unavailable=True)
    result = parser.parse(image)

    assert result.status == "need_review"
    assert "OCR provider unavailable" in result.error_message
    assert result.blocks == []

