from uart_simulator.tools.encoding_reference import (
    best_decode,
    decode_candidates,
    encode_variants,
    is_cjk_char,
)


def test_is_cjk_char_basic():
    assert is_cjk_char("中") is True
    assert is_cjk_char("A") is False


def test_decode_candidates_prefers_utf8_for_utf8_text():
    raw = "电机测试".encode("utf-8")
    cands = decode_candidates(raw, ["utf-8", "gbk", "latin-1"])
    assert cands
    assert cands[0].encoding == "utf-8"


def test_best_decode_for_gbk_bytes():
    raw = "参数读取".encode("gbk")
    best = best_decode(raw, ["utf-8", "gb18030", "gbk"])
    assert best is not None
    assert best.encoding in ("gbk", "gb18030")


def test_encode_variants_contains_requested_encodings():
    out = encode_variants("测试", ["utf-8", "gb18030"])
    assert "utf-8" in out
    assert "gb18030" in out
    assert out["utf-8"]
