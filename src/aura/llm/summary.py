from dataclasses import dataclass


DEFAULT_SUMMARY_MODEL = "vrfai/gemma-4-E4B-it-fp8"
DEFAULT_SUMMARY_LANGUAGE = "台灣繁體中文"


class SummaryDependencyError(RuntimeError):
    pass


@dataclass(frozen=True)
class SummarySettings:
    enabled: bool = False
    model_id: str = DEFAULT_SUMMARY_MODEL
    quantization: str = "nvfp8"
    device_map: str = "auto"
    max_new_tokens: int = 768
    temperature: float = 0.2
    language: str = DEFAULT_SUMMARY_LANGUAGE


def transcript_has_content(transcript: str) -> bool:
    return bool(transcript and transcript.strip())


def build_summary_prompt(transcript: str, language: str = DEFAULT_SUMMARY_LANGUAGE) -> str:
    return (
        "你是專業會議紀錄整理助理。請只使用台灣常用的繁體中文，不要使用簡體中文或中國大陸用語。\n"
        "請根據下方逐字稿輸出結構化摘要，並保留可執行資訊。\n\n"
        "輸出格式：\n"
        "1. 一句話總結\n"
        "2. 重點摘要\n"
        "3. 決策與共識\n"
        "4. 待辦事項：列出負責人、事項、期限；若逐字稿沒有提到，寫「未提及」\n"
        "5. 風險、疑問與需要追蹤的地方\n\n"
        f"輸出語言：{language}\n\n"
        "逐字稿：\n"
        f"{transcript.strip()}\n"
    )


def _is_gemma4_model(model_id: str) -> bool:
    normalized = model_id.lower()
    return "gemma-4" in normalized or "gemma4" in normalized


def _load_text_generation_model(settings: SummarySettings):
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoModelForImageTextToText, AutoProcessor, AutoTokenizer, BitsAndBytesConfig
    except ImportError as exc:
        raise SummaryDependencyError(
            "LLM summary requires optional dependencies. Install them with "
            "`python -m pip install -e .[summary]`."
        ) from exc

    model_kwargs = {
        "device_map": settings.device_map,
        "trust_remote_code": True,
    }
    quantization = settings.quantization.lower()
    if quantization == "int8":
        model_kwargs["quantization_config"] = BitsAndBytesConfig(load_in_8bit=True)
    else:
        model_kwargs["torch_dtype"] = "auto" if torch.cuda.is_available() else torch.float32

    if _is_gemma4_model(settings.model_id):
        processor = AutoProcessor.from_pretrained(settings.model_id, trust_remote_code=True)
        model = AutoModelForImageTextToText.from_pretrained(settings.model_id, **model_kwargs)
        return processor, model

    tokenizer = AutoTokenizer.from_pretrained(settings.model_id, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(settings.model_id, **model_kwargs)
    return tokenizer, model


def _tokens_for_prompt(tokenizer_or_processor, prompt: str):
    if hasattr(tokenizer_or_processor, "apply_chat_template"):
        messages = [
            {
                "role": "system",
                "content": "你是專業會議紀錄整理助理，所有輸出必須是台灣繁體中文。",
            },
            {"role": "user", "content": prompt},
        ]
        try:
            return tokenizer_or_processor.apply_chat_template(
                messages,
                add_generation_prompt=True,
                tokenize=True,
                return_tensors="pt",
                return_dict=True,
            )
        except TypeError:
            legacy_messages = [
                {
                    "role": "system",
                    "content": "你是專業會議紀錄整理助理，所有輸出必須是台灣繁體中文。",
                },
                {"role": "user", "content": prompt},
            ]
            text = tokenizer_or_processor.apply_chat_template(legacy_messages, add_generation_prompt=True, tokenize=False)
            return tokenizer_or_processor(text, return_tensors="pt")
    return tokenizer_or_processor(prompt, return_tensors="pt")


def _decode_new_tokens(tokenizer, output_ids, input_length: int) -> str:
    generated = output_ids[0][input_length:]
    return tokenizer.decode(generated, skip_special_tokens=True).strip()


def summarize_transcript(transcript: str, settings: SummarySettings | None = None) -> str:
    settings = settings or SummarySettings(enabled=True)
    if not transcript_has_content(transcript):
        return ""

    prompt = build_summary_prompt(transcript, settings.language)
    tokenizer_or_processor, model = _load_text_generation_model(settings)
    inputs = _tokens_for_prompt(tokenizer_or_processor, prompt)
    device = getattr(model, "device", None)
    if device is not None and hasattr(inputs, "to"):
        inputs = inputs.to(device)

    generate_kwargs = {
        "max_new_tokens": settings.max_new_tokens,
        "do_sample": settings.temperature > 0,
        "temperature": settings.temperature,
    }
    output_ids = model.generate(**inputs, **generate_kwargs)
    input_length = inputs["input_ids"].shape[-1]
    return _decode_new_tokens(tokenizer_or_processor, output_ids, input_length)


def format_summary_block(summary: str) -> str:
    return "\n\n===== LLM Summary =====\n" + summary.strip()
