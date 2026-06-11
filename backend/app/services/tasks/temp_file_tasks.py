from app.db.models import TempFile
from app.db.session import SessionLocal
from app.services.parser.document_parser import DocumentParser
from app.services.parser.progress import progress_for_status
from app.services.storage.minio_client import ObjectStorage


def process_temp_file_in_background(temp_file_id: str) -> dict:
    with SessionLocal() as db:
        temp_file = db.get(TempFile, temp_file_id)
        if not temp_file:
            return {"status": "failed", "error": "temp file not found"}

        path = ObjectStorage().local_path_for(temp_file.minio_object_key)
        parser = DocumentParser()
        temp_file.status = "parsing"
        temp_file.metadata_json = {
            **(temp_file.metadata_json or {}),
            **_parser_progress_metadata(parser, path),
            "local_path": str(path),
        }
        db.commit()

        parse_result = parser.parse(path)
        temp_file.status = "ready" if parse_result.status == "ready" else parse_result.status
        temp_file.parsed_text = parse_result.text
        temp_file.metadata_json = {
            **(temp_file.metadata_json or {}),
            **parse_result.metadata,
            "error_message": parse_result.error_message,
            "local_path": str(path),
        }
        db.commit()
        return {"status": temp_file.status}


def _parser_progress_metadata(parser: DocumentParser, path) -> dict:
    progress_metadata = getattr(parser, "progress_metadata", None)
    if not callable(progress_metadata):
        return {
            **progress_for_status("parsing"),
            "status_message": "正在解析文件内容。",
            "parser_detail": f"文件类型：{path.suffix.lower().lstrip('.') or 'unknown'}。",
        }
    return progress_metadata(path)
