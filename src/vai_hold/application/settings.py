from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from vai_hold.domain.errors import ConfigError

DEFAULT_HOLD_MEMO = (
    "SMM Default Hold : SMM will auto release this hold, if this hold not auto release > 30 mins , "
    "please contact LIT onduty to manual release it."
)
DEFAULT_RELEASE_MEMO = "SMM auto release Default Hold."


@dataclass
class Settings:
    runtime_mode: str
    persistence_backend: str
    sqlite_path: str
    hold_user: str
    hold_memo: str
    hold_codes: list[str]
    release_user: str
    release_memo: str
    station_priority: list[str]
    watchdog_minutes: int
    disable_after_overdue_lots: int
    notify_emails: list[str]
    smm_hold_code: str = "SMMH"
    smm_hold_user: str = "AOA"
    smm_hold_step: str = "DefaultHoldStep"
    smm_memo_template: str = "Please check {slots}"
    max_action_attempts: int = 3
    policy_version: str = "v1"
    config_version: str = "v1"
    scope_lot_ids: frozenset[str] = field(default_factory=frozenset)

    @property
    def new_holds_allowed(self) -> bool:
        return True

    def allows_lot(self, lot_id: str | None) -> bool:
        """Empty scope = no restriction. Non-empty = only those Lot IDs."""
        if not self.scope_lot_ids:
            return True
        return bool(lot_id) and lot_id in self.scope_lot_ids


def load_settings(path: str | Path | None = None, overrides: dict | None = None) -> Settings:
    data: dict = {}
    if path is not None:
        p = Path(path)
        if not p.exists():
            raise ConfigError(f"config not found: {p}")
        loaded = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ConfigError("config must be a mapping")
        data = loaded
    if overrides:
        data = _deep_merge(data, overrides)

    runtime = data.get("runtime") or {}
    persistence = data.get("persistence") or {}
    hold = data.get("hold") or {}
    release = data.get("release") or {}
    stations = data.get("stations") or {}
    defense = data.get("smm_exception_defense") or {}
    notify = defense.get("notify") or {}

    mode = str(runtime.get("mode") or "").strip()
    if mode not in {"DEV", "PROD"}:
        raise ConfigError("runtime.mode must be DEV or PROD")
    backend = str(persistence.get("backend") or "").strip()
    if backend not in {"memory", "sqlite", "oracle"}:
        raise ConfigError("persistence.backend must be memory|sqlite|oracle")
    if mode == "PROD" and backend != "oracle":
        raise ConfigError("PROD requires persistence.backend=oracle")

    codes = list(hold.get("codes") or ["ENHL", "OTHL"])
    if not codes:
        raise ConfigError("hold.codes must not be empty")

    scope = data.get("scope") or {}
    raw_lots = scope.get("lot_ids") if scope.get("lot_ids") is not None else scope.get("lots")
    scope_lot_ids = frozenset(str(x).strip() for x in (raw_lots or []) if str(x).strip())

    return Settings(
        runtime_mode=mode,
        persistence_backend=backend,
        sqlite_path=str(persistence.get("sqlite_path") or "var/dev.db"),
        hold_user=str(hold.get("user") or "ABO"),
        hold_memo=str(hold.get("memo") or DEFAULT_HOLD_MEMO),
        hold_codes=[str(c) for c in codes],
        release_user=str(release.get("user") or hold.get("user") or "ABO"),
        release_memo=str(release.get("memo") or DEFAULT_RELEASE_MEMO),
        station_priority=[str(s) for s in (stations.get("priority") or ["August", "Overlay", "CDSEM"])],
        watchdog_minutes=int(defense.get("watchdog_minutes") or 30),
        disable_after_overdue_lots=int(defense.get("disable_new_hold_after_overdue_lots") or 3),
        notify_emails=[str(e) for e in (notify.get("emails") or [])],
        smm_hold_code=str((data.get("smm_hold") or {}).get("hold_code") or "SMMH"),
        smm_hold_user=str((data.get("smm_hold") or {}).get("hold_user") or "AOA"),
        smm_hold_step=str((data.get("smm_hold") or {}).get("step") or "DefaultHoldStep"),
        smm_memo_template=str(
            (data.get("smm_hold") or {}).get("memo_template") or "Please check {slots}"
        ),
        max_action_attempts=max(1, int(((data.get("action") or {}).get("retry") or {}).get("max_attempts") or 3)),
        scope_lot_ids=scope_lot_ids,
    )


def example_config_path() -> Path:
    return Path(__file__).resolve().parents[3] / "Design" / "config" / "app.example.yaml"


def _deep_merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out
