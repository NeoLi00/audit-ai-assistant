from typing import Any

STATUS_PROGRESS: dict[str, tuple[str, int]] = {
    "uploaded": ("已上传", 8),
    "parsing": ("解析中", 40),
    "ocr_running": ("OCR 中", 50),
    "chunking": ("切分中", 70),
    "embedding": ("索引中", 88),
    "ready": ("已完成", 100),
    "indexed": ("已完成", 100),
    "need_review": ("待复核", 100),
    "failed": ("失败", 100),
}

ESTIMATED_STATUSES = {"uploaded", "parsing", "ocr_running", "chunking", "embedding"}


def progress_for_status(status: str, metadata: dict[str, Any] | None = None) -> dict[str, int | str | bool]:
    stage, percent = STATUS_PROGRESS.get(status, (status or "处理中", 0))
    metadata = metadata or {}
    if status in ESTIMATED_STATUSES:
        stage = str(metadata.get("progress_stage") or stage)
        percent = _coerce_percent(metadata.get("progress_percent"), percent)
    return {
        "progress_stage": stage,
        "progress_percent": percent,
        "progress_estimated": status in ESTIMATED_STATUSES,
    }


def _coerce_percent(value: Any, fallback: int) -> int:
    try:
        percent = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(0, min(100, percent))
