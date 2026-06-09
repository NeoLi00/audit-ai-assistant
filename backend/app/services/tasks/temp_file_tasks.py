from app.db.models import TempFile
from app.db.session import SessionLocal
from app.services.parser.document_parser import DocumentParser
from app.services.storage.minio_client import ObjectStorage


def process_temp_file_in_background(temp_file_id: str) -> dict:
    with SessionLocal() as db:
        temp_file = db.get(TempFile, temp_file_id)
        if not temp_file:
            return {"status": "failed", "error": "temp file not found"}

        path = ObjectStorage().local_path_for(temp_file.minio_object_key)
        temp_file.status = "parsing"
        db.commit()

        parse_result = DocumentParser().parse(path)
        temp_file.status = "ready" if parse_result.status == "ready" else parse_result.status
        temp_file.parsed_text = parse_result.text
        temp_file.metadata_json = {
            **parse_result.metadata,
            "error_message": parse_result.error_message,
            "local_path": str(path),
        }
        db.commit()
        return {"status": temp_file.status}
