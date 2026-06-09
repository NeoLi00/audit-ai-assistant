TRUNCATED_MARKER = "\n...[已截断]"


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 2)


def truncate_text(text: str, max_chars: int, marker: str = TRUNCATED_MARKER) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    marker_length = len(marker)
    if max_chars <= marker_length:
        return text[:max_chars]
    return f"{text[: max_chars - marker_length]}{marker}"


def total_message_chars(messages: list[dict]) -> int:
    return sum(len(str(message.get("content", ""))) for message in messages)


def enforce_context_budget(messages: list[dict], max_chars: int) -> list[dict]:
    if max_chars <= 0 or total_message_chars(messages) <= max_chars:
        return messages

    trimmed = [dict(message) for message in messages]
    while len(trimmed) > 2 and total_message_chars(trimmed) > max_chars:
        trimmed.pop(1)

    if total_message_chars(trimmed) <= max_chars:
        return trimmed

    user_message = trimmed[-1]
    user_chars = len(str(user_message.get("content", "")))
    system_budget = max(1000, max_chars - user_chars)
    trimmed[0]["content"] = truncate_text(str(trimmed[0].get("content", "")), system_budget)
    return trimmed

