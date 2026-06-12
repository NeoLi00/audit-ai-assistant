from collections.abc import Callable
from dataclasses import dataclass, field

ProgressCallback = Callable[[dict], None]


@dataclass
class ParsedBlock:
    text: str
    block_type: str = "paragraph"
    page_number: int | None = None
    sheet_name: str | None = None
    heading_path: str | None = None
    paragraph_index: int | None = None
    bbox_json: dict | None = None
    confidence: float | None = None


@dataclass
class ParseResult:
    status: str
    blocks: list[ParsedBlock] = field(default_factory=list)
    text: str = ""
    error_message: str = ""
    metadata: dict = field(default_factory=dict)
