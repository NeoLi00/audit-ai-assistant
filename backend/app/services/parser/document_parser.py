from pathlib import Path

from app.core.config import Settings, get_settings
from app.services.parser.base import ParseResult
from app.services.parser.excel_parser import ExcelParser
from app.services.parser.image_ocr import ImageOCRParser
from app.services.parser.mineru_parser import MinerUParser
from app.services.parser.pdf_parser import PDFParser
from app.services.parser.progress import progress_for_status
from app.services.parser.word_parser import WordParser

SUPPORTED_EXTENSIONS = {".doc", ".docx", ".xls", ".xlsx", ".pdf", ".png", ".jpg", ".jpeg", ".tiff"}


class DocumentParser:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def parse(self, path: Path) -> ParseResult:
        ext = path.suffix.lower()
        if self.settings.document_parser_provider == "mineru":
            if ext in SUPPORTED_EXTENSIONS:
                return MinerUParser(settings=self.settings).parse(path)
            return ParseResult(status="failed", error_message="当前格式不支持，请上传Word/Excel/PDF/图片文件")

        if ext in {".doc", ".docx"}:
            return WordParser().parse(path)
        if ext in {".xls", ".xlsx"}:
            return ExcelParser().parse(path)
        if ext == ".pdf":
            return PDFParser().parse(path)
        if ext in {".png", ".jpg", ".jpeg", ".tiff"}:
            return ImageOCRParser().parse(path)
        return ParseResult(status="failed", error_message="当前格式不支持，请上传Word/Excel/PDF/图片文件")

    def progress_metadata(self, path: Path) -> dict:
        if self.settings.document_parser_provider == "mineru":
            return MinerUParser(settings=self.settings).progress_metadata(path)
        return {
            "provider": self.settings.document_parser_provider,
            "parser_provider": self.settings.document_parser_provider,
            **progress_for_status("parsing"),
            "status_message": "正在解析文件内容。",
            "parser_detail": f"文件类型：{path.suffix.lower().lstrip('.') or 'unknown'}。",
        }
