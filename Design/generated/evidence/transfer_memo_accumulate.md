# Evidence：`transfer_memo_accumulate`

**情境：** 未掃完：本 Agent 不改 SMM Memo

這份是程式自己印的 log 切片，不是事後摘要。

## MES / Action 次數

- set_hold calls: `1`
- release calls: `0`
- transfer calls: `None`
- work_state: `WAIT_AI`
- lifecycle: `OPEN`

## Action 時間序

- `hold.intent` `SET_DEFAULT_HOLD_BY_Operation_Start` rule=`A1-03` receipt=`None`
- `hold.sent` `SET_DEFAULT_HOLD_BY_Operation_Start` rule=`A1-03` receipt=`None`
- `hold.receipt` `SET_DEFAULT_HOLD_BY_Operation_Start` rule=`A1-03` receipt=`ACCEPTED` attempt_no=1
- `hold.confirmed` `CONFIRM_DEFAULT_HOLD_EXISTS` rule=`A2-02` receipt=`None`

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
    "OrderId": "20260101-000000656-EQP01",
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
    "QueryStatus": "FOUND",
    "Holds": [
      {
        "OpeNo": "OP200",
        "OpeName": "August",
        "RouteId": "RT1",
        "HoldCode": "ENHL",
        "HoldUser": "ABO",
        "HoldMemo": "SMM Default Hold : SMM will auto release this hold, if this hold not auto release > 30 mins , please contact LIT onduty to manual release it."
      }
    ]
  },
  "SmmHold": {
    "StepMode": "DefaultHoldStep",
    "OpeNo": "OP200",
    "QueryStatus": "FOUND",
    "Holds": []
  },
  "Flow": {
    "MainPdId": "RT1",
    "FutureHoldStep": "OP200",
    "FutureHoldOpeName": "August"
  },
  "OrderDb": {
    "OrderId": "20260101-000000656-EQP01",
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
      "ActionState": "ACKNOWLEDGED",
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
  "hold_present": true,
  "ours_hold_count": 1,
  "hold_query": "FOUND",
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
    "QueryStatus": "FOUND",
    "Holds": [
      {
        "OpeNo": "OP200",
        "OpeName": "August",
        "RouteId": "RT1",
        "HoldCode": "ENHL",
        "HoldUser": "ABO",
        "HoldMemo": "SMM Default Hold : SMM will auto release this hold, if this hold not auto release > 30 mins , please contact LIT onduty to manual release it."
      }
    ]
  },
  "SmmHold": {
    "StepMode": "DefaultHoldStep",
    "OpeNo": "OP200",
    "QueryStatus": "FOUND",
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
    "OrderId": "20260101-000000656-EQP01",
    "Lifecycle": "OPEN",
    "WorkState": "WAIT_AI",
    "ProtectionState": "CONFIRMED",
    "AiState": "WAITING",
    "LastRuleId": "A2-02",
    "StateReason": null,
    "CloseReason": null,
    "DataError": null,
    "TargetOpeNo": "OP200",
    "OperationStartAt": "2026-01-01T00:00:00Z",
    "Bindings": [
      {
        "Status": "CONFIRMED",
        "Role": "PREVENTIVE",
        "RouteId": "RT1",
        "OpeNo": "OP200",
        "HoldCode": "ENHL",
        "HoldUser": "ABO",
        "HoldMemo": "SMM Default Hold : SMM will auto release this hold, if this hold not auto release > 30 mins , please contact LIT onduty to manual release it.",
        "BackupHoldOrder": 1,
        "TimeQuality": "ESTIMATED",
        "RequestedAt": "2026-01-01T00:00:00Z",
        "FirstConfirmedAt": "2026-01-01T00:00:00Z"
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
  "hold_present": true,
  "ours_hold_count": 1,
  "hold_query": "FOUND",
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

### EVAL 4 `CHECK_AI_SCAN_COMPLETE`

- **DECISION** `A2-05` / `ai_incomplete` action=`CHECK_AI`

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
    "QueryStatus": "FOUND",
    "Holds": [
      {
        "OpeNo": "OP200",
        "OpeName": "August",
        "RouteId": "RT1",
        "HoldCode": "ENHL",
        "HoldUser": "ABO",
        "HoldMemo": "SMM Default Hold : SMM will auto release this hold, if this hold not auto release > 30 mins , please contact LIT onduty to manual release it."
      }
    ]
  },
  "SmmHold": {
    "StepMode": "DefaultHoldStep",
    "OpeNo": "OP200",
    "QueryStatus": "FOUND",
    "Holds": [
      {
        "RouteId": "RT1",
        "OpeNo": "OP200",
        "OpeName": "August",
        "HoldCode": "SMMH",
        "HoldUser": "AOA",
        "HoldType": "SMMH",
        "HoldMemo": "Please check #1"
      }
    ]
  },
  "AiScan": {
    "QueryStatus": "FOUND",
    "ExpectedCount": 25,
    "ScannedCount": 1,
    "LatestScanTime": "2026-01-01T00:00:00Z",
    "RecTime": "2026-01-01T00:00:00Z"
  },
  "Flow": {
    "MainPdId": "RT1",
    "FutureHoldStep": "OP200",
    "FutureHoldOpeName": "August"
  },
  "OrderDb": {
    "OrderId": "20260101-000000656-EQP01",
    "Lifecycle": "OPEN",
    "WorkState": "WAIT_AI",
    "ProtectionState": "CONFIRMED",
    "AiState": "WAITING",
    "LastRuleId": "A2-02",
    "StateReason": null,
    "CloseReason": null,
    "DataError": null,
    "TargetOpeNo": "OP200",
    "OperationStartAt": "2026-01-01T00:00:00Z",
    "Bindings": [
      {
        "Status": "CONFIRMED",
        "Role": "PREVENTIVE",
        "RouteId": "RT1",
        "OpeNo": "OP200",
        "HoldCode": "ENHL",
        "HoldUser": "ABO",
        "HoldMemo": "SMM Default Hold : SMM will auto release this hold, if this hold not auto release > 30 mins , please contact LIT onduty to manual release it.",
        "BackupHoldOrder": 1,
        "TimeQuality": "ESTIMATED",
        "RequestedAt": "2026-01-01T00:00:00Z",
        "FirstConfirmedAt": "2026-01-01T00:00:00Z"
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
  "work_state": "WAIT_AI",
  "protection_state": "CONFIRMED",
  "ai_state": "WAITING",
  "hold_present": true,
  "ours_hold_count": 1,
  "hold_query": "FOUND",
  "hold_query_ok": true,
  "unverified_set_hold": false,
  "unverified_release": false,
  "ai_gate": "WAITING",
  "expected_count": 25,
  "missing_count": 24,
  "new_hold_allowed": true,
  "defect_handoff_ready": true
}
```

</details>

### EVAL 5 `CHECK_AI_SCAN_COMPLETE`

- **DECISION** `A2-05` / `ai_incomplete` action=`CHECK_AI`

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
    "QueryStatus": "FOUND",
    "Holds": [
      {
        "OpeNo": "OP200",
        "OpeName": "August",
        "RouteId": "RT1",
        "HoldCode": "ENHL",
        "HoldUser": "ABO",
        "HoldMemo": "SMM Default Hold : SMM will auto release this hold, if this hold not auto release > 30 mins , please contact LIT onduty to manual release it."
      }
    ]
  },
  "SmmHold": {
    "StepMode": "DefaultHoldStep",
    "OpeNo": "OP200",
    "QueryStatus": "FOUND",
    "Holds": [
      {
        "RouteId": "RT1",
        "OpeNo": "OP200",
        "OpeName": "August",
        "HoldCode": "SMMH",
        "HoldUser": "AOA",
        "HoldType": "SMMH",
        "HoldMemo": "Please check #1"
      }
    ]
  },
  "AiScan": {
    "QueryStatus": "FOUND",
    "ExpectedCount": 25,
    "ScannedCount": 1,
    "LatestScanTime": "2026-01-01T00:00:00Z",
    "RecTime": "2026-01-01T00:00:00Z"
  },
  "Flow": {
    "MainPdId": "RT1",
    "FutureHoldStep": "OP200",
    "FutureHoldOpeName": "August"
  },
  "OrderDb": {
    "OrderId": "20260101-000000656-EQP01",
    "Lifecycle": "OPEN",
    "WorkState": "WAIT_AI",
    "ProtectionState": "CONFIRMED",
    "AiState": "WAITING",
    "LastRuleId": "A2-05",
    "StateReason": "ai_incomplete",
    "CloseReason": null,
    "DataError": null,
    "TargetOpeNo": "OP200",
    "OperationStartAt": "2026-01-01T00:00:00Z",
    "Bindings": [
      {
        "Status": "CONFIRMED",
        "Role": "PREVENTIVE",
        "RouteId": "RT1",
        "OpeNo": "OP200",
        "HoldCode": "ENHL",
        "HoldUser": "ABO",
        "HoldMemo": "SMM Default Hold : SMM will auto release this hold, if this hold not auto release > 30 mins , please contact LIT onduty to manual release it.",
        "BackupHoldOrder": 1,
        "TimeQuality": "ESTIMATED",
        "RequestedAt": "2026-01-01T00:00:00Z",
        "FirstConfirmedAt": "2026-01-01T00:00:00Z"
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
  "work_state": "WAIT_AI",
  "protection_state": "CONFIRMED",
  "ai_state": "WAITING",
  "hold_present": true,
  "ours_hold_count": 1,
  "hold_query": "FOUND",
  "hold_query_ok": true,
  "unverified_set_hold": false,
  "unverified_release": false,
  "ai_gate": "WAITING",
  "expected_count": 25,
  "missing_count": 24,
  "new_hold_allowed": true,
  "defect_handoff_ready": true
}
```

</details>

