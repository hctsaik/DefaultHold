from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from vai_hold.application.log import emit, pipeline_run
from vai_hold.application.logevents import Event
from vai_hold.application.pipelines import check_ai, confirm_hold, confirm_release, control, defense, set_default_hold
from vai_hold.application.ports.clock import Clock
from vai_hold.application.ports.gateways import AiPort, FlowPort, HoldPort, NotifierPort, SmmPort
from vai_hold.application.ports.persistence import UnitOfWorkFactory
from vai_hold.application.settings import Settings
from vai_hold.domain.enums import FunctionCode
from vai_hold.domain.errors import UnknownFunctionCode


@dataclass
class RunResult:
    function_code: str
    processed: int = 0
    created_orders: int = 0
    holds_sent: int = 0
    releases_sent: int = 0
    emails_sent: int = 0
    errors: list[str] | None = None


class App:
    """Composition-facing façade. Cron hits run(); pipelines live under application/pipelines/."""

    def __init__(
        self,
        *,
        settings: Settings,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        hold: HoldPort,
        flow: FlowPort,
        ai: AiPort,
        smm: SmmPort,
        notifier: NotifierPort,
        worker_id: str = "worker-1",
    ) -> None:
        self.settings = settings
        self.uow_factory = uow_factory
        self.clock = clock
        self.hold = hold
        self.flow = flow
        self.ai = ai
        self.smm = smm
        self.notifier = notifier
        self.worker_id = worker_id

    def run(self, function_code: str, params: dict[str, Any] | None = None) -> RunResult:
        params = params or {}
        try:
            code = FunctionCode(function_code)
        except ValueError as exc:
            raise UnknownFunctionCode(function_code) from exc
        dispatch = {
            FunctionCode.SET_DEFAULT_HOLD: set_default_hold.run,
            FunctionCode.CONFIRM_HOLD: confirm_hold.run,
            FunctionCode.CHECK_AI: check_ai.run,
            FunctionCode.CONFIRM_RELEASE: confirm_release.run,
            FunctionCode.DEFENSE: defense.run,
            FunctionCode.RESUME: control.run_resume,
            FunctionCode.MANUAL_CLOSE: control.run_manual_close,
        }
        handler = dispatch.get(code)
        if handler is None:
            raise UnknownFunctionCode(function_code)
        with pipeline_run(code.value):
            try:
                result = handler(self, params)
            except Exception as exc:
                emit(
                    Event.PIPELINE_END,
                    function_code=code.value,
                    outcome="failure",
                    error_type=type(exc).__name__,
                )
                raise
            emit(
                Event.PIPELINE_END,
                function_code=code.value,
                outcome="success",
                processed=result.processed,
                created_orders=result.created_orders,
                holds_sent=result.holds_sent,
                releases_sent=result.releases_sent,
                emails_sent=result.emails_sent,
            )
            return result
