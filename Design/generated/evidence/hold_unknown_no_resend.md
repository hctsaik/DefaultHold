# Evidence：`hold_unknown_no_resend`

**情境：** Hold 查詢仍 UNKNOWN：不准重送

這份是程式自己印的 log 切片，不是事後摘要。

## MES / Action 次數

- set_hold calls: `1`
- release calls: `0`
- transfer calls: `None`
- work_state: `HOLD_VERIFY_PENDING`
- lifecycle: `OPEN`

## Action 時間序

- `hold.intent` `SET_DEFAULT_HOLD_BY_Operation_Start` rule=`A1-03` receipt=`None`
- `hold.sent` `SET_DEFAULT_HOLD_BY_Operation_Start` rule=`A1-03` receipt=`None`
- `hold.receipt` `SET_DEFAULT_HOLD_BY_Operation_Start` rule=`A1-03` receipt=`UNKNOWN` attempt_no=1
- `incident.opened` `CONFIRM_DEFAULT_HOLD_EXISTS` rule=`A2-14` receipt=`None`

## 每一輪 EVAL（Facts → State → Decision）

### EVAL 1 `SET_DEFAULT_HOLD_BY_Operation_Start`

- **DECISION** `A1-03` / `need_preventive_hold` action=`SET_HOLD`

<details><summary>OBSERVED（原始 Facts）</summary>

```json
{
  "Lot": {
    "LotId": "LOT1",
    "OpeNo": "OP100",
    "ReworkCount": 0,
    "ToolId": "EQP01",
    "RouteId": "RT1",
    "OperationStartTime": "2026-01-01T00:00:00Z",
    "RecTime": "2026-01-01T00:00:00Z"
  },
  "DefaultHold": {
    "QueryStatus": "NOT_FOUND",
    "Holds": []
  },
  "SmmHold": {
    "StepMode": "DefaultHoldStep",
    "OpeNo": "OP200",
    "QueryStatus": "NOT_FOUND",
    "Holds": []
  },
  "Flow": {
    "MainPdId": "RT1",
    "FutureHoldStep": "OP200",
    "FutureHoldOpeName": "August"
  },
  "OrderDb": {
    "OrderId": "20260101-000000289-EQP01",
    "Lifecycle": "OPEN",
    "WorkState": "NEED_HOLD",
    "ProtectionState": "NONE",
    "AiState": "WAITING",
    "LastRuleId": null,
    "StateReason": null,
    "CloseReason": null,
    "DataError": null,
    "TargetOpeNo": "OP200",
    "OperationStartAt": "2026-01-01T00:00:00Z",
    "Bindings": [],
    "ActionInFlight": null
  }
}
```

</details>

<details><summary>STATE</summary>

```json
{
  "lifecycle": "OPEN",
  "work_state": "NEED_HOLD",
  "protection_state": "NONE",
  "ai_state": "WAITING",
  "hold_present": false,
  "ours_hold_count": 0,
  "hold_query": "NOT_FOUND",
  "hold_query_ok": true,
  "unverified_set_hold": false,
  "unverified_release": false,
  "new_hold_allowed": true,
  "defect_handoff_ready": false
}
```

</details>

### EVAL 2 `SET_DEFAULT_HOLD_BY_Operation_Start`

- **DECISION** `A1-03` / `need_preventive_hold` action=`SET_HOLD`

<details><summary>OBSERVED（原始 Facts）</summary>

```json
{
  "Lot": {
    "LotId": "LOT1",
    "OpeNo": "OP100",
    "ReworkCount": 0,
    "ToolId": "EQP01",
    "RouteId": "RT1",
    "OperationStartTime": "2026-01-01T00:00:00Z",
    "RecTime": "2026-01-01T00:00:00Z"
  },
  "DefaultHold": {
    "QueryStatus": "NOT_FOUND",
    "Holds": []
  },
  "SmmHold": {
    "StepMode": "DefaultHoldStep",
    "OpeNo": "OP200",
    "QueryStatus": "NOT_FOUND",
    "Holds": []
  },
  "Flow": {
    "MainPdId": "RT1",
    "FutureHoldStep": "OP200",
    "FutureHoldOpeName": "August"
  },
  "OrderDb": {
    "OrderId": "20260101-000000289-EQP01",
    "Lifecycle": "OPEN",
    "WorkState": "HOLD_VERIFY_PENDING",
    "ProtectionState": "SET_PENDING",
    "AiState": "WAITING",
    "LastRuleId": "A1-03",
    "StateReason": null,
    "CloseReason": null,
    "DataError": null,
    "TargetOpeNo": "OP200",
    "OperationStartAt": "2026-01-01T00:00:00Z",
    "Bindings": [
      {
        "Status": "PENDING",
        "Role": "PREVENTIVE",
        "RouteId": "RT1",
        "OpeNo": "OP200",
        "HoldCode": "ENHL",
        "HoldUser": "ABO",
        "HoldMemo": "SMM Default Hold : SMM will auto release this hold, if this hold not auto release > 30 mins , please contact LIT onduty to manual release it.",
        "BackupHoldOrder": 1,
        "TimeQuality": "ESTIMATED",
        "RequestedAt": "2026-01-01T00:00:00Z",
        "FirstConfirmedAt": null
      }
    ],
    "ActionInFlight": {
      "ActionType": "SET_HOLD",
      "ActionState": "UNKNOWN",
      "HoldCode": "ENHL"
    }
  }
}
```

</details>

<details><summary>STATE</summary>

```json
{
  "lifecycle": "OPEN",
  "work_state": "NEED_HOLD",
  "protection_state": "NONE",
  "ai_state": "WAITING",
  "hold_present": false,
  "ours_hold_count": 0,
  "hold_query": "NOT_FOUND",
  "hold_query_ok": true,
  "unverified_set_hold": true,
  "unverified_release": false,
  "new_hold_allowed": true,
  "defect_handoff_ready": false
}
```

</details>

