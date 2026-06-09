from pathlib import Path

from app.services.parser.base import ParsedBlock, ParseResult


class ImageOCRParser:
    def __init__(self, force_unavailable: bool = False) -> None:
        self.force_unavailable = force_unavailable

    def parse(self, path: Path) -> ParseResult:
        if self.force_unavailable:
            return self._unavailable()
        try:
            from paddleocr import PaddleOCR  # type: ignore
        except Exception:
            return self._unavailable()

        try:
            ocr = PaddleOCR(use_angle_cls=True, lang="ch")
            results = ocr.ocr(str(path), cls=True) or []
            blocks: list[ParsedBlock] = []
            confidences: list[float] = []
            for page in results:
                for item in page or []:
                    bbox, payload = item
                    text, confidence = payload
                    confidences.append(float(confidence))
                    blocks.append(
                        ParsedBlock(
                            text=text,
                            block_type="ocr_text",
                            bbox_json={"bbox": bbox},
                            confidence=float(confidence),
                        )
                    )
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0
            status = "need_review" if avg_confidence < 0.6 else "ready"
            return ParseResult(
                status=status,
                blocks=blocks,
                text="\n".join(b.text for b in blocks),
                error_message="OCR 置信度低，需要人工校对" if status == "need_review" else "",
                metadata={"average_confidence": avg_confidence},
            )
        except Exception as exc:
            return ParseResult(status="need_review", error_message=f"OCR 失败，需要人工校对：{exc}")

    def _unavailable(self) -> ParseResult:
        return ParseResult(
            status="need_review",
            blocks=[],
            error_message="OCR provider unavailable，需要人工校对或安装 PaddleOCR",
        )

