"""Recognize Ozon's visible access denial before saving browser cookies."""


def blocked_page_text(text: str) -> bool:
    normalized = text.casefold()
    return "похоже, нет соединения" in normalized and "обратиться в поддержку" in normalized
