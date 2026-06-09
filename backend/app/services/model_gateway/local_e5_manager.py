import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.core.config import Settings, get_settings
from app.services.model_gateway.runtime_config import configure_local_e5_ready, load_runtime_config, save_runtime_config

LOCAL_E5_LOG_DIR = Path(".local_storage/model-logs")


@dataclass
class LocalE5Manager:
    process: subprocess.Popen | None = None

    def start(self, settings: Settings | None = None) -> dict:
        settings = settings or get_settings()
        status = self.status(settings)
        if status["status"] == "ready":
            configure_local_e5_ready(settings)
            return status
        if status["status"] == "starting" or (self.process and self.process.poll() is None):
            return {"status": "starting", "message": "multilingual-e5-small 冷启动中，请稍候"}

        LOCAL_E5_LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = LOCAL_E5_LOG_DIR / "local-e5.log"
        command = [
            sys.executable,
            "-m",
            "app.services.model_gateway.local_embedding_server",
            "--host",
            settings.local_e5_host,
            "--port",
            str(settings.local_e5_port),
            "--model",
            settings.local_e5_model,
        ]
        log_file = log_path.open("a", encoding="utf-8")
        try:
            self.process = subprocess.Popen(command, stdout=log_file, stderr=subprocess.STDOUT, text=True)
        finally:
            log_file.close()
        config = load_runtime_config()
        config["local_e5"] = {
            "status": "starting",
            "message": "multilingual-e5-small 冷启动中，请稍候",
            "pid": self.process.pid,
            "started_at": datetime.now(UTC).isoformat(),
            "health_url": f"http://{settings.local_e5_host}:{settings.local_e5_port}/health",
            "log_path": str(log_path),
        }
        save_runtime_config(config)
        return config["local_e5"]

    def status(self, settings: Settings | None = None) -> dict:
        settings = settings or get_settings()
        try:
            response = httpx.get(f"http://{settings.local_e5_host}:{settings.local_e5_port}/health", timeout=2)
            if response.status_code == 200:
                payload = response.json()
                if payload.get("status") == "ready":
                    configure_local_e5_ready(settings)
                    return {"status": "ready", "message": "multilingual-e5-small 已就绪，可以开始测试"}
                if payload.get("status") == "starting":
                    return {
                        "status": "starting",
                        "message": payload.get("message") or "multilingual-e5-small 冷启动中，请稍候",
                    }
        except Exception:
            pass
        config = load_runtime_config()
        local_e5 = config.get("local_e5") or {}
        if self.process and self.process.poll() is not None:
            local_e5 = self._mark_failed(config, "本地 embedding 服务启动失败，请确认已安装 local-models 依赖。")
        elif self.process and self.process.poll() is None:
            local_e5 = self._starting_status(local_e5, self.process.pid)
        elif local_e5.get("status") in {"starting", "ready"}:
            pid = local_e5.get("pid")
            if self._pid_is_running(pid):
                local_e5 = self._starting_status(local_e5, pid)
            else:
                local_e5 = self._mark_failed(config, "未检测到本地 embedding 服务进程，可能启动失败或后端已重启。")
        return local_e5 or {"status": "stopped", "message": "尚未启动 multilingual-e5-small"}

    def _mark_failed(self, config: dict, fallback_message: str) -> dict:
        previous = config.get("local_e5") or {}
        log_tail = self._log_tail(previous.get("log_path"))
        status = {
            "status": "failed",
            "message": log_tail or fallback_message,
            "checked_at": datetime.now(UTC).isoformat(),
        }
        if previous.get("health_url"):
            status["health_url"] = previous["health_url"]
        if previous.get("log_path"):
            status["log_path"] = previous["log_path"]
        config["local_e5"] = status
        config["embedding"] = {}
        save_runtime_config(config)
        get_settings.cache_clear()
        return status

    def _starting_status(self, local_e5: dict, pid: int | str | None) -> dict:
        started_at = local_e5.get("started_at")
        elapsed_seconds = self._elapsed_seconds(started_at)
        message = "multilingual-e5-small 冷启动中，请稍候"
        if elapsed_seconds is not None:
            message = f"{message}，已等待 {elapsed_seconds} 秒"
        return {**local_e5, "status": "starting", "message": message, "pid": pid}

    def _pid_is_running(self, pid: int | str | None) -> bool:
        if not pid:
            return False
        try:
            os.kill(int(pid), 0)
        except (OSError, ValueError):
            return False
        return True

    def _elapsed_seconds(self, started_at: str | None) -> int | None:
        if not started_at:
            return None
        try:
            started = datetime.fromisoformat(started_at)
        except ValueError:
            return None
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        return max(0, int((datetime.now(UTC) - started).total_seconds()))

    def _log_tail(self, path_raw: str | None) -> str:
        if not path_raw:
            return ""
        try:
            return Path(path_raw).read_text(encoding="utf-8", errors="replace")[-500:].strip()
        except OSError:
            return ""


local_e5_manager = LocalE5Manager()
