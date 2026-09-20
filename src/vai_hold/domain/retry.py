from __future__ import annotations

from vai_hold.domain.enums import ActionState, ReceiptOutcome
from vai_hold.domain.models import ActionAttempt, ActionCommand, TransportReceipt

TERMINAL_ERRORS = frozenset({"CODE_CONFLICT", "CONFLICT", "PERMISSION"})
RETRYABLE_CLASSES = frozenset({"TRANSIENT", "RATE_LIMIT", "TIMEOUT"})
DEFAULT_MAX_ATTEMPTS = 3


def attempts_for(command_id: str, history: list[ActionAttempt]) -> int:
    return sum(1 for a in history if a.command_id == command_id)


def next_attempt_no(command_id: str, history: list[ActionAttempt]) -> int:
    return 1 + attempts_for(command_id, history)


def is_retryable_reject(receipt: TransportReceipt) -> bool:
    """Immediate retry is only for explicit temporary rejects — not timeout/UNKNOWN."""
    if receipt.outcome != ReceiptOutcome.REJECTED:
        return False
    err = (receipt.normalized_error or receipt.retry_class or "").upper()
    if err in TERMINAL_ERRORS:
        return False
    cls = (receipt.retry_class or "").upper()
    return err in RETRYABLE_CLASSES or cls in RETRYABLE_CLASSES


def state_after_receipt(
    receipt: TransportReceipt,
    *,
    attempt_no: int,
    max_attempts: int,
) -> ActionState:
    if receipt.outcome == ReceiptOutcome.ACCEPTED:
        return ActionState.ACKNOWLEDGED
    if is_retryable_reject(receipt) and attempt_no < max_attempts:
        return ActionState.RETRY_WAIT
    if receipt.outcome == ReceiptOutcome.REJECTED:
        return ActionState.REJECTED
    return ActionState.UNKNOWN


def retry_wait_commands(commands: list[ActionCommand]) -> list[ActionCommand]:
    return [c for c in commands if c.action_state == ActionState.RETRY_WAIT]
