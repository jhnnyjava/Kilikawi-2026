import json

from pathlib import Path
from tempfile import TemporaryDirectory

from uart_simulator.tools.decode_receive_log import parse_frames
from uart_simulator.tools.decode_receive_log import write_json
from uart_simulator.tools.windcon_map import classify_marker
from uart_simulator.tools.windcon_map import label_stream_words
from uart_simulator.tools.windcon_map import register_name


def test_classify_marker_known_values() -> None:
    assert classify_marker(0xF00B) == "compat-marker"
    assert classify_marker(0x4CCD) == "float-marker"
    assert classify_marker(0x0000) == "zero-marker"


def test_label_stream_words_uses_readable_field_names() -> None:
    words = [10, -2, 540, 10000, 32, 1, 0, 0xF00B, 23, 1]
    labels = label_stream_words(words)

    assert labels["speed_feedback_rpm"] == 10
    assert labels["current_feedback_da"] == -2
    assert labels["bus_voltage_dv"] == 540
    assert labels["marker_word"] == 0xF00B
    assert labels["fault_code"] == 23


def test_register_name_known_and_unknown() -> None:
    assert register_name(0x1007) == "WorkMode"
    assert register_name(0xDEAD) == "0xDEAD"


def test_write_json_emits_structured_payload() -> None:
    capture = Path(__file__).resolve().parents[2] / "data" / "Receive_20260326164249.txt"
    assert capture.exists()
    frames = parse_frames(capture)

    with TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "decoded.json"
        write_json(frames[:1], out)

        payload = json.loads(out.read_text())
        assert payload["frame_count"] == 1
        assert payload["frames"][0]["readable"]["marker_word"] in (-4085, 19661, 0)
        assert payload["frames"][0]["words_i16"]
