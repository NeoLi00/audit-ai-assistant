import argparse

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Local multilingual-e5-small embedding server")
state: dict = {"model": None, "model_name": "", "ready": False}


class EmbeddingRequest(BaseModel):
    input: str | list[str]
    model: str | None = None


@app.get("/health")
def health():
    return {
        "status": "ready" if state["ready"] else "starting",
        "model": state["model_name"],
        "message": "multilingual-e5-small 已就绪，可以开始测试" if state["ready"] else "模型冷启动中",
    }


@app.post("/v1/embeddings")
def embeddings(payload: EmbeddingRequest):
    texts = [payload.input] if isinstance(payload.input, str) else payload.input
    model = state["model"]
    vectors = model.encode(texts, normalize_embeddings=True).tolist()
    return {
        "object": "list",
        "model": state["model_name"],
        "data": [
            {"object": "embedding", "index": index, "embedding": vector}
            for index, vector in enumerate(vectors)
        ],
    }


def create_app(model_name: str) -> FastAPI:
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as exc:  # pragma: no cover - depends on optional local model packages
        raise RuntimeError(
            "缺少本地 embedding 依赖。请运行：pip install -e '.[local-models]'"
        ) from exc
    state["model_name"] = model_name
    state["model"] = SentenceTransformer(model_name)
    state["ready"] = True
    print("multilingual-e5-small 已就绪，可以开始测试", flush=True)
    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--model", default="intfloat/multilingual-e5-small")
    args = parser.parse_args()

    create_app(args.model)
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
