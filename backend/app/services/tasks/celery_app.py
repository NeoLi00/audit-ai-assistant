from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "audit_ai_assistant",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery_app.conf.update(task_track_started=True, task_serializer="json", result_serializer="json")

