SYSTEM_PROMPT = """你是广东医科大学审计处的审计 AI 助手。
你可以使用会话历史理解用户的指代、省略和连续追问。
知识库材料是可检索参考材料，不是固定问答模块。
请根据用户问题、会话历史、本轮上传文件和检索到的知识库材料自然回答。
不要编造材料中不存在的制度名称、条款号、金额阈值或文件事实。
如果材料不足以支持确定结论，请直接说明缺少哪些材料或信息。
回答不需要固定格式，像正常对话一样直接回答。
不要在回答正文中输出证据编号、chunk_id、来源清单、原文摘录或引用片段；除非用户明确要求，不要附带引用片段。"""


def build_audit_prompt(
    question: str,
    evidence: list[dict],
    mode: str = "normal",
    uploaded_files: list[dict] | None = None,
    conversation_summary: str = "",
    uploaded_file_max_chars: int = 12000,
) -> str:
    evidence_lines = []
    for index, item in enumerate(evidence, start=1):
        source = item.get("file_name") or item.get("document_id") or "未知文件"
        location = item.get("heading_path") or item.get("sheet_name") or item.get("page_number") or "未标注位置"
        context_text = item.get("context_text") or item.get("text", "")
        evidence_lines.append(
            f"[证据{index}] chunk_id={item.get('chunk_id')} source={source} location={location}\n"
            f"{context_text}"
        )
    evidence_text = "\n\n".join(evidence_lines) if evidence_lines else "未检索到知识库材料。"
    uploaded_file_lines = []
    for index, item in enumerate(uploaded_files or [], start=1):
        text = item.get("text", "")
        uploaded_file_lines.append(
            f"[本轮上传文件{index}] file_id={item.get('id')} source={item.get('file_name')}\n"
            f"{text[:uploaded_file_max_chars]}"
        )
    uploaded_file_text = "\n\n".join(uploaded_file_lines) if uploaded_file_lines else "本轮未上传可用文件。"
    summary_text = conversation_summary.strip() or "暂无历史摘要。"
    return (
        f"{SYSTEM_PROMPT}\n\n问题：{question}\n\n"
        f"会话摘要（压缩历史，仅用于理解上下文，不作为独立审计依据）：\n{summary_text}\n\n"
        f"知识库材料：\n{evidence_text}\n\n本轮上传文件：\n{uploaded_file_text}"
    )
