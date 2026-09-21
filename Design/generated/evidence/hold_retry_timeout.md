# Evidence：`hold_retry_timeout`

**情境：** SET_HOLD timeout：先查驗再重送，最多 3 次

這份是程式自己印的 log 切片，不是事後摘要。

## MES / Action 次數

- set_hold calls: `3`
- release calls: `0`
- transfer calls: `None`
- work_state: `HOLD_FAILED`
- lifecycle: `OPEN`

## Action 時間序

- `hold.intent` `SET_DEFAULT_HOLD_BY_Operation_Start` rule=`A1-03` receipt=`None`
- `hold.sent` `SET_DEFAULT_HOLD_BY_Operation_Start` rule=`A1-03` receipt=`None`
- `hold.receipt` `SET_DEFAULT_HOLD_BY_Operation_Start` rule=`A1-03` receipt=`UNKNOWN` attempt_no=1
- `hold.sent` `SET_DEFAULT_HOLD_BY_Operation_Start` rule=`A1-09` receipt=`None`
- `hold.receipt` `SET_DEFAULT_HOLD_BY_Operation_Start` rule=`A1-09` receipt=`UNKNOWN` attempt_no=2
- `hold.sent` `SET_DEFAULT_HOLD_BY_Operation_Start` rule=`A1-09` receipt=`None`
- `hold.receipt` `SET_DEFAULT_HOLD_BY_Operation_Start` rule=`A1-09` receipt=`UNKNOWN` attempt_no=3
- `incident.opened` `CONFIRM_DEFAULT_HOLD_EXISTS` rule=`A2-18` receipt=`None`
- `hold.failed` `CONFIRM_DEFAULT_HOLD_EXISTS` rule=`A2-18` receipt=`None`

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
    "OrderId": "20260101-000000765-EQP01",
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
    "OrderId": "20260101-000000765-EQP01",
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

### EVAL 3 `CONFIRM_DEFAULT_HOLD_EXISTS`

- **DECISION** `A2-01` / `set_hold_in_flight` action=`VERIFY_HOLD`

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
  "AiScan": {
    "QueryStatus": "NOT_FOUND",
    "ExpectedCount": 25,
    "ScannedCount": 0,
    "LatestScanTime": null,
    "RecTime": "2026-01-01T00:00:00Z"
  },
  "Flow": {
    "MainPdId": "RT1",
    "FutureHoldStep": "OP200",
    "FutureHoldOpeName": "August"
  },
  "OrderDb": {
    "OrderId": "20260101-000000765-EQP01",
    "Lifecycle": "OPEN",
    "WorkState": "NEED_HOLD",
    "ProtectionState": "FAILED",
    "AiState": "WAITING",
    "LastRuleId": "A1-09",
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
    "ActionInFlight": null
  }
}
```

</details>

<details><summary>STATE</summary>

```json
{
  "lifecycle": "OPEN",
  "work_state": "HOLD_VERIFY_PENDING",
  "protection_state": "SET_PENDING",
  "ai_state": "WAITING",
  "hold_present": false,
  "ours_hold_count": 0,
  "hold_query": "NOT_FOUND",
  "hold_query_ok": true,
  "unverified_set_hold": false,
  "unverified_release": false,
  "ai_gate": "WAITING",
  "expected_count": 25,
  "missing_count": 25,
  "new_hold_allowed": true,
  "defect_handoff_ready": false
}
```

</details>

### EVAL 4 `SET_DEFAULT_HOLD_BY_Operation_Start`

- **DECISION** `A1-09` / `retry_same_action` action=`SET_HOLD`

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
    "OrderId": "20260101-000000765-EQP01",
    "Lifecycle": "OPEN",
    "WorkState": "NEED_HOLD",
    "ProtectionState": "FAILED",
    "AiState": "WAITING",
    "LastRuleId": "A1-09",
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
  "protection_state": "FAILED",
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

### EVAL 5 `SET_DEFAULT_HOLD_BY_Operation_Start`

- **DECISION** `A1-09` / `retry_same_action` action=`SET_HOLD`

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
    "OrderId": "20260101-000000765-EQP01",
    "Lifecycle": "OPEN",
    "WorkState": "HOLD_VERIFY_PENDING",
    "ProtectionState": "SET_PENDING",
    "AiState": "WAITING",
    "LastRuleId": "A1-09",
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
  "protection_state": "FAILED",
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

### EVAL 6 `CONFIRM_DEFAULT_HOLD_EXISTS`

- **DECISION** `A2-01` / `set_hold_in_flight` action=`VERIFY_HOLD`

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
  "AiScan": {
    "QueryStatus": "NOT_FOUND",
    "ExpectedCount": 25,
    "ScannedCount": 0,
    "LatestScanTime": null,
    "RecTime": "2026-01-01T00:00:00Z"
  },
  "Flow": {
    "MainPdId": "RT1",
    "FutureHoldStep": "OP200",
    "FutureHoldOpeName": "August"
  },
  "OrderDb": {
    "OrderId": "20260101-000000765-EQP01",
    "Lifecycle": "OPEN",
    "WorkState": "NEED_HOLD",
    "ProtectionState": "FAILED",
    "AiState": "WAITING",
    "LastRuleId": "A1-09",
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
    "ActionInFlight": null
  }
}
```

</details>

<details><summary>STATE</summary>

```json
{
  "lifecycle": "OPEN",
  "work_state": "HOLD_VERIFY_PENDING",
  "protection_state": "SET_PENDING",
  "ai_state": "WAITING",
  "hold_present": false,
  "ours_hold_count": 0,
  "hold_query": "NOT_FOUND",
  "hold_query_ok": true,
  "unverified_set_hold": false,
  "unverified_release": false,
  "ai_gate": "WAITING",
  "expected_count": 25,
  "missing_count": 25,
  "new_hold_allowed": true,
  "defect_handoff_ready": false
}
```

</details>

### EVAL 7 `SET_DEFAULT_HOLD_BY_Operation_Start`

- **DECISION** `A1-09` / `retry_same_action` action=`SET_HOLD`

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
    "OrderId": "20260101-000000765-EQP01",
    "Lifecycle": "OPEN",
    "WorkState": "NEED_HOLD",
    "ProtectionState": "FAILED",
    "AiState": "WAITING",
    "LastRuleId": "A1-09",
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
  "protection_state": "FAILED",
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

### EVAL 8 `SET_DEFAULT_HOLD_BY_Operation_Start`

- **DECISION** `A1-09` / `retry_same_action` action=`SET_HOLD`

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
    "OrderId": "20260101-000000765-EQP01",
    "Lifecycle": "OPEN",
    "WorkState": "HOLD_VERIFY_PENDING",
    "ProtectionState": "SET_PENDING",
    "AiState": "WAITING",
    "LastRuleId": "A1-09",
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
  "protection_state": "FAILED",
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

### EVAL 9 `CONFIRM_DEFAULT_HOLD_EXISTS`

- **DECISION** `A2-01` / `set_hold_in_flight` action=`VERIFY_HOLD`

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
  "AiScan": {
    "QueryStatus": "NOT_FOUND",
    "ExpectedCount": 25,
    "ScannedCount": 0,
    "LatestScanTime": null,
    "RecTime": "2026-01-01T00:00:00Z"
  },
  "Flow": {
    "MainPdId": "RT1",
    "FutureHoldStep": "OP200",
    "FutureHoldOpeName": "August"
  },
  "OrderDb": {
    "OrderId": "20260101-000000765-EQP01",
    "Lifecycle": "OPEN",
    "WorkState": "HOLD_FAILED",
    "ProtectionState": "FAILED",
    "AiState": "WAITING",
    "LastRuleId": "A2-18",
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
    "ActionInFlight": null
  }
}
```

</details>

<details><summary>STATE</summary>

```json
{
  "lifecycle": "OPEN",
  "work_state": "HOLD_VERIFY_PENDING",
  "protection_state": "SET_PENDING",
  "ai_state": "WAITING",
  "hold_present": false,
  "ours_hold_count": 0,
  "hold_query": "NOT_FOUND",
  "hold_query_ok": true,
  "unverified_set_hold": false,
  "unverified_release": false,
  "ai_gate": "WAITING",
  "expected_count": 25,
  "missing_count": 25,
  "new_hold_allowed": true,
  "defect_handoff_ready": false
}
```

</details>

### EVAL 10 `CONFIRM_DEFAULT_HOLD_EXISTS`

- **DECISION** `A2-18` / `retry_exhausted` action=`OPEN_INCIDENT`

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
  "AiScan": {
    "QueryStatus": "NOT_FOUND",
    "ExpectedCount": 25,
    "ScannedCount": 0,
    "LatestScanTime": null,
    "RecTime": "2026-01-01T00:00:00Z"
  },
  "Flow": {
    "MainPdId": "RT1",
    "FutureHoldStep": "OP200",
    "FutureHoldOpeName": "August"
  },
  "OrderDb": {
    "OrderId": "20260101-000000765-EQP01",
    "Lifecycle": "OPEN",
    "WorkState": "HOLD_FAILED",
    "ProtectionState": "FAILED",
    "AiState": "WAITING",
    "LastRuleId": "A2-18",
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
    "ActionInFlight": null
  }
}
```

</details>

<details><summary>STATE</summary>

```json
{
  "lifecycle": "OPEN",
  "work_state": "HOLD_FAILED",
  "protection_state": "FAILED",
  "ai_state": "WAITING",
  "hold_present": false,
  "ours_hold_count": 0,
  "hold_query": "NOT_FOUND",
  "hold_query_ok": true,
  "unverified_set_hold": false,
  "unverified_release": false,
  "ai_gate": "WAITING",
  "expected_count": 25,
  "missing_count": 25,
  "new_hold_allowed": true,
  "defect_handoff_ready": false
}
```

</details>

