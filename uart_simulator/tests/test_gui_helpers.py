from __future__ import annotations

import pytest

pytest.importorskip("tkinter")

from uart_simulator.gui.app import _scale_kwargs


class FakeIntVar:
    def __init__(self, value: int = 0) -> None:
        self._value = value

    def get(self) -> int:
        return self._value

    def set(self, value: int) -> None:
        self._value = value


class FakeScale:
    def __init__(self, *, variable: FakeIntVar | None = None) -> None:
        self._variable = variable
        self._value = 0

    def get(self) -> int:
        if self._variable is not None:
            return self._variable.get()
        return self._value


def test_scale_variable_binding_tracks_programmatic_var_changes() -> None:
    var = FakeIntVar(10)
    bound_scale = FakeScale(variable=_scale_kwargs(from_=0, to=100, variable=var)["variable"])
    unbound_scale = FakeScale()

    var.set(42)

    assert bound_scale.get() == 42
    assert unbound_scale.get() == 0
