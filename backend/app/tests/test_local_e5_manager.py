import httpx

from app.core.config import Settings
from app.services.model_gateway import local_e5_manager as local_e5_module
from app.services.model_gateway import runtime_config
from app.services.model_gateway.local_e5_manager import LocalE5Manager


def test_local_e5_status_marks_stale_starting_state_as_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_config, "RUNTIME_CONFIG_PATH", tmp_path / ".runtime_model_config.json")
    runtime_config.save_runtime_config(
        {
            "llm": {},
            "embedding": {},
            "local_e5": {
                "status": "starting",
                "message": "multilingual-e5-small 冷启动中，请稍候",
            },
        }
    )

    def unavailable_health(*args, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(local_e5_module.httpx, "get", unavailable_health)

    status = LocalE5Manager().status(Settings())

    assert status["status"] == "failed"
    assert "未检测到本地 embedding 服务进程" in status["message"]
    assert runtime_config.load_runtime_config()["local_e5"]["status"] == "failed"

