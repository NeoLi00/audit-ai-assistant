from app.services.rag.fusion import reciprocal_rank_fusion
from app.services.rag.prompt_builder import build_audit_prompt


def test_rrf_promotes_documents_found_by_multiple_searchers():
    vector_results = [{"chunk_id": "a", "score": 0.9}, {"chunk_id": "b", "score": 0.8}]
    keyword_results = [{"chunk_id": "b", "score": 10.0}, {"chunk_id": "c", "score": 8.0}]

    fused = reciprocal_rank_fusion([vector_results, keyword_results], k=60)

    assert fused[0]["chunk_id"] == "b"
    assert {item["chunk_id"] for item in fused} == {"a", "b", "c"}


def test_prompt_builder_treats_knowledge_base_as_retrievable_material_without_fixed_format():
    prompt = build_audit_prompt(
        question="设备采购超过多少金额需要招标？",
        mode="policy",
        evidence=[
            {
                "chunk_id": "chunk-1",
                "file_name": "采购制度.docx",
                "text": "超过限额的设备采购应履行招标程序。",
                "page_number": 2,
                "heading_path": "第二章",
            }
        ],
        uploaded_files=[
            {
                "id": "temp-1",
                "file_name": "本轮合同.pdf",
                "text": "本轮上传合同显示合同金额为 120 万元。",
            }
        ],
    )

    assert "你是广东医科大学审计处的审计 AI 助手" in prompt
    assert "知识库材料" in prompt
    assert "回答结构" not in prompt
    assert "当前模式" not in prompt
    assert "1. 结论" not in prompt
    assert "采购制度.docx" in prompt
    assert "本轮上传合同显示合同金额为 120 万元" in prompt
    assert "设备采购超过多少金额需要招标？" in prompt


def test_prompt_builder_asks_for_plain_answers_without_citation_fragments():
    prompt = build_audit_prompt(
        question="合同付款风险是什么？",
        evidence=[
            {
                "chunk_id": "chunk-1",
                "file_name": "合同.pdf",
                "text": "付款前应完成验收并取得审批记录。",
            }
        ],
    )

    assert "不要在回答正文中输出证据编号" in prompt
    assert "不要附带引用片段" in prompt
    assert "chunk_id" in prompt
