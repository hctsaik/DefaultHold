from __future__ import annotations

from vai_hold.domain.enums import HoldKind
from vai_hold.domain.models import FlowStep, FlowView, HoldTarget, SourceResult
from vai_hold.domain.enums import SourceStatus


def next_process_step(flow: FlowView) -> FlowStep | None:
    """First Process Tool *after* the current station.

    Anchor is ``flow.current_ope_no`` (the station being processed now, e.g. OP100).
    That station itself is excluded. This is **not** "from the Default Hold
    station (OP200) look further forward".
    """
    by_ope = {s.ope_no: s for s in flow.steps}
    if flow.current_ope_no not in by_ope:
        return None
    current = by_ope[flow.current_ope_no]
    for step in flow.steps:
        if step.index > current.index and step.process_type.upper() in {"PROCESS_TOOL", "PROCESS"}:
            return step
    return None


def smm_hold_ope_no(flow: FlowView | None, default_hold_ope: str | None, mode: str) -> str | None:
    """OpeNo where official SmmHold (YAML SMMH/AOA) must sit.

    DefaultHoldStep → the Default Hold target station.
    NextProcessStep → :func:`next_process_step` from *current* station, not from Default Hold.
    """
    mode = (mode or "DefaultHoldStep").strip()
    if mode == "NextProcessStep":
        if flow is None:
            return None
        step = next_process_step(flow)
        return step.ope_no if step else None
    return default_hold_ope


def choose_hold_target(
    flow_result: SourceResult,
    *,
    station_priority: list[str],
) -> HoldTarget | None:
    """Pure function. UNKNOWN flow is not 'no config stations'."""
    if flow_result.status in (SourceStatus.UNKNOWN, SourceStatus.STALE):
        return None
    if flow_result.status == SourceStatus.NOT_FOUND or flow_result.value is None:
        return None

    flow: FlowView = flow_result.value
    if not flow.steps:
        return None

    by_ope = {s.ope_no: s for s in flow.steps}
    if flow.current_ope_no not in by_ope:
        return None
    current = by_ope[flow.current_ope_no]

    def not_passed(step) -> bool:
        return step.index >= current.index

    def matches_config(step, name: str) -> bool:
        n = name.casefold()
        return n == step.name.casefold() or n in step.name.casefold()

    remaining_config: list[tuple[int, int, object]] = []
    any_config_in_flow = False
    for prio, cfg_name in enumerate(station_priority):
        for step in flow.steps:
            if matches_config(step, cfg_name):
                any_config_in_flow = True
                if not_passed(step):
                    remaining_config.append((prio, step.index, step))

    if remaining_config:
        remaining_config.sort(key=lambda t: (t[0], t[1]))
        step = remaining_config[0][2]
        kind = HoldKind.CURRENT if step.ope_no == current.ope_no else HoldKind.FUTURE
        return HoldTarget(
            route_id=flow.route_id,
            ope_no=step.ope_no,
            ope_name=step.name,
            kind=kind,
            reason="config_priority",
            flow_version=flow.version,
        )

    if any_config_in_flow:
        return HoldTarget(
            route_id=flow.route_id,
            ope_no=current.ope_no,
            ope_name=current.name,
            kind=HoldKind.CURRENT,
            reason="all_config_stations_passed_hold_current",
            flow_version=flow.version,
        )

    for step in flow.steps:
        if step.index >= current.index and step.process_type.upper() in {
            "PROCESS_TOOL",
            "PROCESS",
        }:
            kind = HoldKind.CURRENT if step.ope_no == current.ope_no else HoldKind.FUTURE
            return HoldTarget(
                route_id=flow.route_id,
                ope_no=step.ope_no,
                ope_name=step.name,
                kind=kind,
                reason="first_process_tool",
                flow_version=flow.version,
            )

    return HoldTarget(
        route_id=flow.route_id,
        ope_no=current.ope_no,
        ope_name=current.name,
        kind=HoldKind.CURRENT,
        reason="fallback_current_station",
        flow_version=flow.version,
    )
