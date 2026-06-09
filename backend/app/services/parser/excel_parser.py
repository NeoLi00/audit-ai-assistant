from pathlib import Path

import pandas as pd

from app.services.parser.base import ParsedBlock, ParseResult


class ExcelParser:
    def parse(self, path: Path) -> ParseResult:
        try:
            workbook = pd.read_excel(path, sheet_name=None)
            blocks: list[ParsedBlock] = []
            metadata = {"sheets": []}
            for sheet_name, frame in workbook.items():
                summary = self._summarize_sheet(sheet_name, frame)
                metadata["sheets"].append(summary)
                blocks.append(
                    ParsedBlock(
                        text=summary["markdown"],
                        block_type="sheet_summary",
                        sheet_name=sheet_name,
                    )
                )
            return ParseResult(
                status="ready",
                blocks=blocks,
                text="\n\n".join(b.text for b in blocks),
                metadata=metadata,
            )
        except Exception as exc:
            return ParseResult(status="failed", error_message=f"Excel 表格结构异常：{exc}")

    def _summarize_sheet(self, sheet_name: str, frame: pd.DataFrame) -> dict:
        rows, cols = frame.shape
        amount_columns = [
            str(col)
            for col in frame.columns
            if any(token in str(col) for token in ["金额", "费用", "价款", "合计", "预算"])
        ]
        date_columns = [str(col) for col in frame.columns if "日期" in str(col) or "时间" in str(col)]
        sample = frame.head(20)
        markdown = [
            f"Sheet: {sheet_name}",
            f"行数: {rows}",
            f"列数: {cols}",
            f"字段: {', '.join(map(str, frame.columns))}",
        ]
        if amount_columns:
            markdown.append(f"疑似金额列: {', '.join(amount_columns)}")
            for column in amount_columns:
                numeric = pd.to_numeric(frame[column], errors="coerce")
                markdown.append(
                    f"{column} 统计: count={int(numeric.count())}, sum={numeric.sum():.2f}, "
                    f"max={numeric.max():.2f}, min={numeric.min():.2f}"
                )
        if date_columns:
            markdown.append(f"疑似日期列: {', '.join(date_columns)}")
        markdown.append("前20行样例:")
        markdown.append(sample.to_markdown(index=False))
        return {
            "sheet_name": sheet_name,
            "rows": rows,
            "columns": list(map(str, frame.columns)),
            "amount_columns": amount_columns,
            "date_columns": date_columns,
            "markdown": "\n".join(markdown),
        }
