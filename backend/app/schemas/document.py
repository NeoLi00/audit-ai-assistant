from pydantic import BaseModel


class OcrCorrectionRequest(BaseModel):
    text: str


class ReindexRequest(BaseModel):
    force: bool = True

