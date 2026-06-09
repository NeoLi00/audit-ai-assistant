def build_citations(items: list[dict]) -> list[dict]:
    citations = []
    for item in items:
        text = item.get("text", "")
        citations.append(
            {
                "chunk_id": item.get("chunk_id"),
                "document_id": item.get("document_id"),
                "file_name": item.get("file_name"),
                "page_number": item.get("page_number"),
                "sheet_name": item.get("sheet_name"),
                "heading_path": item.get("heading_path"),
                "quote": text[:180],
                "score": item.get("rrf_score", item.get("score", 0)),
            }
        )
    return citations

