import re
from pathlib import Path

import pandas as pd


def analyze_excel_question(path: Path, question: str) -> str | None:
    threshold = _extract_threshold(question)
    if threshold is None and not any(token in question for token in ["统计", "汇总", "平均", "最大", "最小"]):
        return None
    workbook = pd.read_excel(path, sheet_name=None)
    outputs: list[str] = []
    for sheet_name, frame in workbook.items():
        amount_columns = [
            col for col in frame.columns if any(token in str(col) for token in ["金额", "费用", "价款", "合计"])
        ]
        for column in amount_columns:
            numeric = pd.to_numeric(frame[column], errors="coerce")
            if threshold is not None:
                matched = frame[numeric > threshold].head(50)
                outputs.append(
                    f"Sheet {sheet_name} 中 `{column}` 超过 {threshold:g} 的记录数：{len(matched)}\n"
                    f"{matched.to_markdown(index=False)}"
                )
            else:
                outputs.append(
                    f"Sheet {sheet_name} 中 `{column}` 统计：count={int(numeric.count())}, "
                    f"sum={numeric.sum():.2f}, avg={numeric.mean():.2f}, "
                    f"max={numeric.max():.2f}, min={numeric.min():.2f}"
                )
    return "\n\n".join(outputs) if outputs else None


def _extract_threshold(question: str) -> float | None:
    match = re.search(r"(?:超过|大于|高于)\s*([0-9]+(?:\.[0-9]+)?)", question)
    return float(match.group(1)) if match else None

