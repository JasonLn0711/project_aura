"""Check real cached punctuation inference; run with HF_HUB_OFFLINE=1."""
from aura.asr.punctuation import CHINESE_PUNCTUATION, default_restorer, restore_chinese_punctuation


def main():
    cases = [
        "今天我們討論實驗室進度請大家確認下週的會議時間",
        "今天開會，討論 namespace token 版本3.14以及後續工作",
        "我們使用 nnU-Net 處理影像接著比較 Dice score 並確認 CCM 的分割結果",
        "這是長篇會議紀錄我們需要確認模型會保留所有文字並補上標點" * 30,
    ]
    lexical = lambda text: "".join(c for c in text if c not in CHINESE_PUNCTUATION)
    for text in cases:
        result = restore_chinese_punctuation(text, "zh")
        assert result.backend == "model", result.detail
        assert lexical(result.text) == lexical(text), "Transcript content changed"
        assert any(c in CHINESE_PUNCTUATION for c in result.text), "No punctuation produced"
    restorer = default_restorer()
    print(f"PASS: {len(cases)} real inference cases; {restorer.model_id}; {restorer.device}")


if __name__ == "__main__":
    main()
