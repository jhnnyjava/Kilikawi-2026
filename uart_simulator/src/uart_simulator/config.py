from dataclasses import dataclass


@dataclass(slots=True)
class SerialConfig:
    port: str
    baud: int = 115200
    node_id: int = 1
    timeout_s: float = 0.05
