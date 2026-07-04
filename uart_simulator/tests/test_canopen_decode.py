from __future__ import annotations

import csv

import pytest

from uart_simulator.tools.canopen_map import parse_canopen_frame
from uart_simulator.tools.decode_can_log import parse_can_frames
from uart_simulator.tools.decode_can_log import write_csv


@pytest.mark.parametrize(
    ("can_id", "expected_function", "expected_node_id"),
    [
        (0x080, "SYNC", 0),
        (0x081, "EMCY", 1),
        (0x0FF, "EMCY", 0x7F),
    ],
)
def test_sync_and_emcy_classification(can_id: int, expected_function: str, expected_node_id: int) -> None:
    frame = parse_canopen_frame(can_id, b"")

    assert frame.function == expected_function
    assert frame.node_id == expected_node_id


def test_can_csv_flattens_decoded_pdo_payload(tmp_path) -> None:
    log_path = tmp_path / "can.log"
    log_path.write_text(
        "\n".join(
            [
                "CAN0 281 [6] E8 03 F6 FF 05 00",
                "CAN0 381 [6] 1C 02 20 00 1E 00",
            ]
        ),
        encoding="utf-8",
    )
    out_path = tmp_path / "decoded.csv"

    frames = parse_can_frames(log_path)
    write_csv(frames, out_path)

    with out_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert rows[0]["pdo_type"] == "TPDO2"
    assert rows[0]["velocity_feedback_rpm"] == "1000"
    assert rows[0]["current_feedback_da"] == "-10"
    assert rows[0]["torque_actual"] == "5"
    assert rows[0]["bus_voltage_dv"] == ""

    assert rows[1]["pdo_type"] == "TPDO3"
    assert rows[1]["bus_voltage_dv"] == "540"
    assert rows[1]["driver_temp_c"] == "32"
    assert rows[1]["motor_temp_c"] == "30"
    assert rows[1]["velocity_feedback_rpm"] == ""
