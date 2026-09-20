from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScenarioCase:
    scenario_id: str
    group_name: str
    title: str
    script: list[dict[str, Any]]
    expect: dict[str, Any]
    given: dict[str, Any] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)
    spec: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    sort_order: int = 0


@dataclass
class ScenarioRunResult:
    scenario_id: str
    passed: bool
    actual: dict[str, Any]
    diffs: list[str]
    title: str = ""
