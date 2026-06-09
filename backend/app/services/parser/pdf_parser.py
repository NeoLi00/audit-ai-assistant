from pathlib import Path

import fitz

from app.services.parser.base import ParsedBlock, ParseResult


class PDFParser:
    def parse(self, path: Path) -> ParseResult:
        try:
            doc = fitz.open(path)
            blocks: list[ParsedBlock] = []
            needs_ocr = False
            for index, page in enumerate(doc, start=1):
                text = page.get_text("text").strip()
                if len(text) < 20:
                    needs_ocr = True
                if text:
                    blocks.append(ParsedBlock(text=text, block_type="page", page_number=index))
            if needs_ocr and not blocks:
                return ParseResult(
                    status="need_review",
                    blocks=[],
                    error_message="OCR provider unavailable，需要人工校对或安装 PaddleOCR",
                    metadata={"reason": "scanned_pdf"},
                )
            return ParseResult(
                status="need_review" if needs_ocr else "ready",
                blocks=blocks,
                text="\n\n".join(b.text for b in blocks),
                error_message="部分页面可能为扫描页，需要 OCR 或人工校对" if needs_ocr else "",
            )
        except Exception as exc:
            return ParseResult(status="failed", error_message=f"PDF 解析失败：{exc}")

