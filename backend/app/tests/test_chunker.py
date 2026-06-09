from app.services.rag.chunker import Chunker


def test_chunker_keeps_document_metadata_and_splits_long_text():
    chunker = Chunker(max_chars=40, overlap=8)
    blocks = [
            {
                "id": "block-1",
                "document_id": "doc-1",
                "text": (
                    "第一条 学校设备采购应按制度执行。第二条 超过限额的项目应履行招标程序。"
                    "第三条 审计人员应核对审批记录、采购文件、合同文本和验收付款材料。"
                ),
            "page_number": 3,
            "heading_path": "采购管理/设备采购",
            "sheet_name": None,
        }
    ]

    chunks = chunker.chunk_blocks(blocks)

    assert len(chunks) >= 2
    assert chunks[0]["document_id"] == "doc-1"
    assert chunks[0]["metadata"]["page_number"] == 3
    assert chunks[0]["metadata"]["heading_path"] == "采购管理/设备采购"
    assert chunks[0]["block_ids"] == ["block-1"]


def test_chunker_merges_small_blocks_and_adds_context_metadata():
    chunker = Chunker(max_chars=80, overlap=10)
    blocks = [
        {
            "id": "block-1",
            "document_id": "doc-1",
            "block_type": "paragraph",
            "text": "第一条 采购申请应说明预算来源。",
            "page_number": 1,
            "heading_path": "采购管理/申请",
        },
        {
            "id": "block-2",
            "document_id": "doc-1",
            "block_type": "paragraph",
            "text": "第二条 采购审批应保留完整记录。",
            "page_number": 1,
            "heading_path": "采购管理/申请",
        },
        {
            "id": "block-3",
            "document_id": "doc-1",
            "block_type": "paragraph",
            "text": "第三条 验收付款材料应归档。",
            "page_number": 2,
            "heading_path": "采购管理/验收",
        },
    ]

    chunks = chunker.chunk_blocks(blocks)

    assert chunks[0]["block_ids"] == ["block-1", "block-2"]
    assert "第一条" in chunks[0]["text"]
    assert "第二条" in chunks[0]["text"]
    assert chunks[0]["metadata"]["chunk_type"] == "paragraph"
    assert chunks[0]["metadata"]["token_count"] > 0
    assert chunks[0]["metadata"]["content_hash"]
    assert chunks[0]["metadata"]["chunker_version"]
    assert chunks[0]["parent_chunk_id"]
    assert chunks[0]["prev_chunk_id"] is None
    assert chunks[1]["prev_chunk_id"] == chunks[0]["id"]
    assert chunks[0]["next_chunk_id"] == chunks[1]["id"]


def test_chunker_serializes_table_context_for_retrieval():
    chunker = Chunker(max_chars=200, overlap=20)
    blocks = [
        {
            "id": "table-1",
            "document_id": "doc-1",
            "block_type": "table",
            "text": "项目,预算金额,执行金额\n设备采购,120000,118000",
            "sheet_name": "预算执行表",
            "page_number": 4,
            "heading_path": "预算执行",
        }
    ]

    chunks = chunker.chunk_blocks(blocks)

    assert len(chunks) == 1
    assert chunks[0]["metadata"]["chunk_type"] == "table"
    assert chunks[0]["metadata"]["sheet_name"] == "预算执行表"
    assert "工作表: 预算执行表" in chunks[0]["text"]
    assert "项目,预算金额,执行金额" in chunks[0]["text"]
