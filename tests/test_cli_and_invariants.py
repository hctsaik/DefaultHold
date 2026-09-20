from __future__ import annotations

from vai_hold.composition.cli import main
from vai_hold.domain.enums import FunctionCode


def test_unknown_function_code_exit(tmp_path, monkeypatch):
    cfg = tmp_path / "app.yaml"
    cfg.write_text(
        "runtime: {mode: DEV}\npersistence: {backend: memory}\nhold: {codes: [ENHL, OTHL]}\n",
        encoding="utf-8",
    )
    assert main(["run", "--function-code", "NOPE", "--config", str(cfg)]) == 2


def test_cli_known_code(tmp_path):
    cfg = tmp_path / "app.yaml"
    cfg.write_text(
        "runtime: {mode: DEV}\npersistence: {backend: memory}\nhold: {codes: [ENHL]}\n",
        encoding="utf-8",
    )
    assert main(["run", "--function-code", FunctionCode.SET_DEFAULT_HOLD.value, "--config", str(cfg)]) == 0
