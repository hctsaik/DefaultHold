from __future__ import annotations

from vai_hold.domain.enums import BindingRole, BindingStatus, Lifecycle
from vai_hold.domain.models import HoldBinding, HoldCommand, HoldOrder


ACTIVE_PREVENTIVE = frozenset(
    {
        BindingStatus.PENDING,
        BindingStatus.CONFIRMED,
        BindingStatus.ACTIVE,
        BindingStatus.RELEASE_PENDING,
    }
)


def memo_matches(hold_memo: str, standard_memo: str) -> bool:
    return (hold_memo or "") == (standard_memo or "")


def is_standard_default_hold(
    mes_hold: HoldCommand,
    *,
    standard_memo: str,
    hold_user: str,
    allowed_codes: list[str],
) -> bool:
    return (
        memo_matches(mes_hold.memo, standard_memo)
        and mes_hold.hold_user == hold_user
        and mes_hold.hold_code in allowed_codes
    )


def is_our_preventive_hold(
    mes_hold: HoldCommand,
    order: HoldOrder,
    binding: HoldBinding,
    *,
    standard_memo: str,
    hold_user: str,
) -> bool:
    # 既有 Hold 的身分以 Intent 當下凍結的 Binding 為準；設定換版不得讓舊 Hold 失聯。
    del standard_memo, hold_user
    if binding.role != BindingRole.PREVENTIVE:
        return False
    if binding.order_id != order.order_id:
        return False
    if order.lifecycle not in (Lifecycle.OPEN, Lifecycle.CLOSED, Lifecycle.MANUAL_CLOSED):
        return False
    return (
        mes_hold.lot_id == binding.lot_id == order.lot_id
        and mes_hold.route_id == binding.route_id
        and mes_hold.ope_no == binding.ope_no
        and mes_hold.hold_code == binding.hold_code
        and mes_hold.hold_user == binding.hold_user
        and memo_matches(mes_hold.memo, binding.hold_memo)
    )


def match_our_holds(
    mes_holds: list[HoldCommand],
    order: HoldOrder,
    bindings: list[HoldBinding],
    *,
    standard_memo: str,
    hold_user: str,
) -> list[HoldCommand]:
    preventive = [
        b
        for b in bindings
        if b.role == BindingRole.PREVENTIVE and b.status in ACTIVE_PREVENTIVE | {BindingStatus.RELEASED}
    ]
    matched: list[HoldCommand] = []
    for hold in mes_holds:
        if any(
            is_our_preventive_hold(hold, order, b, standard_memo=standard_memo, hold_user=hold_user)
            for b in preventive
        ):
            matched.append(hold)
    return matched


def match_by_binding(
    mes_holds: list[HoldCommand],
    binding: HoldBinding,
    *,
    standard_memo: str,
    hold_user: str,
) -> list[HoldCommand]:
    del standard_memo, hold_user
    out = []
    for hold in mes_holds:
        if (
            hold.lot_id == binding.lot_id
            and hold.route_id == binding.route_id
            and hold.ope_no == binding.ope_no
            and hold.hold_code == binding.hold_code
            and hold.hold_user == binding.hold_user
            and memo_matches(hold.memo, binding.hold_memo)
        ):
            out.append(hold)
    return out


def is_smm_hold(
    mes_hold: HoldCommand,
    *,
    lot_id: str,
    hold_code: str,
    hold_user: str,
    ope_no: str | None,
) -> bool:
    """Official AI/SMM defect hold: YAML HoldCode + HoldUser at the configured step."""
    if mes_hold.lot_id != lot_id:
        return False
    if mes_hold.hold_code != hold_code or mes_hold.hold_user != hold_user:
        return False
    # Step unresolved → cannot claim official SmmHold (do not match every SMMH on the lot)
    if not ope_no:
        return False
    return mes_hold.ope_no == ope_no


def is_defect_reference_hold(
    mes_hold: HoldCommand,
    *,
    lot_id: str,
    hold_user: str,
    standard_preventive_memo: str,
    smm_hold_code: str = "SMMH",
    smm_hold_user: str = "AOA",
    ope_no: str | None = None,
) -> bool:
    if smm_hold_code and smm_hold_user:
        return is_smm_hold(
            mes_hold,
            lot_id=lot_id,
            hold_code=smm_hold_code,
            hold_user=smm_hold_user,
            ope_no=ope_no,
        )
    if mes_hold.lot_id != lot_id:
        return False
    if memo_matches(mes_hold.memo, standard_preventive_memo):
        return False
    return mes_hold.hold_user == hold_user
