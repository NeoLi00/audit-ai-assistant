import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import Settings, get_settings


class ObjectStorage:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.root = Path(self.settings.local_storage_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    async def save_upload(self, upload: UploadFile, prefix: str = "documents") -> tuple[str, Path]:
        suffix = Path(upload.filename or "upload").suffix.lower()
        object_key = f"{prefix}/{uuid4()}{suffix}"
        local_path = self.root / object_key
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with local_path.open("wb") as target:
            while chunk := await upload.read(1024 * 1024):
                target.write(chunk)
        await upload.seek(0)
        return object_key, local_path

    def local_path_for(self, object_key: str) -> Path:
        return self.root / object_key

    def remove(self, object_key: str) -> None:
        path = self.local_path_for(object_key)
        if path.exists():
            path.unlink()

    def copy_to_storage(self, source: Path, prefix: str = "documents") -> tuple[str, Path]:
        object_key = f"{prefix}/{uuid4()}{source.suffix.lower()}"
        target = self.root / object_key
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        return object_key, target

