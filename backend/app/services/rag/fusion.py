def reciprocal_rank_fusion(result_sets: list[list[dict]], k: int = 60) -> list[dict]:
    by_id: dict[str, dict] = {}
    for results in result_sets:
        for rank, item in enumerate(results, start=1):
            chunk_id = item["chunk_id"]
            existing = by_id.setdefault(chunk_id, {**item, "rrf_score": 0.0})
            existing["rrf_score"] += 1 / (k + rank)
            existing["score"] = max(float(existing.get("score", 0)), float(item.get("score", 0)))
    return sorted(by_id.values(), key=lambda item: item["rrf_score"], reverse=True)

