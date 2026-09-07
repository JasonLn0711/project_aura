"""Local vocabulary hints shared by live, import, and final ASR."""

import unicodedata

MAX_CONTEXT_TOKENS = 200


def normalize_hotwords(text: str) -> tuple[str, ...]:
    words = (unicodedata.normalize("NFC", line.strip()) for line in text.splitlines())
    return tuple(dict.fromkeys(word for word in words if word))


def validate_context(tokenizer, prompt: str | None, hotwords: str | None) -> None:
    encoded = [tokenizer.encode(" " + value.strip()) for value in (prompt, hotwords) if value]
    count = sum(len(getattr(tokens, "ids", tokens)) for tokens in encoded)
    if count > MAX_CONTEXT_TOKENS:
        raise ValueError(
            f"Prompt and hotwords use {count} tokens; shorten the list to "
            f"{MAX_CONTEXT_TOKENS} tokens or fewer. Terms were not truncated."
        )
