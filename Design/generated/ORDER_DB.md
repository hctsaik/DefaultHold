# Order DB 樣本（給人看的）

檔案：`C:/code/claude/defaultHold/Design/generated/order_db.sqlite`

Wafer id 是現場格式 `A123456.01`；片號是小數點後面的 `01` → memo `#1`。

| Lot | 故事 | 你該看到 |
|---|---|---|
| A123456 | C09 掃完 Defect、已滿 settle | 申請解除；`close_reason=SCAN_COMPLETED` |
| A123457 | T12 `.03` 有 ScanCompletedTime | 當掃完；滿 settle 可解 |
| A123458 | C03 還缺一片 | `WAIT_AI`，沒 Release |
| A123459 | 全 OK 且滿 settle | `CLOSED` / `SCAN_COMPLETED` |
| A123460 | Defect + 現場 SMM Hold | `CLOSED` / `SCAN_COMPLETED`；SMM Hold 未動 |
| A123461 | 線上把 Default Hold 解掉 | `MANUAL_CLOSED`（沒有結案 GUI，Hold 沒了就結案） |

## hold_order

| lot_id | work_state | data_error | lifecycle | close_reason | last_rule_id |
| --- | --- | --- | --- | --- | --- |
| A123456 | CLOSED |  | CLOSED | SCAN_COMPLETED | A2-11 |
| A123457 | CLOSED |  | CLOSED | SCAN_COMPLETED | A2-11 |
| A123458 | WAIT_AI |  | OPEN |  | A2-05 |
| A123459 | CLOSED |  | CLOSED | SCAN_COMPLETED | A2-11 |
| A123460 | CLOSED |  | CLOSED | SCAN_COMPLETED | A2-11 |
| A123461 | MANUAL_CLOSED |  | MANUAL_CLOSED | MANUAL | A2-04 |

## wafers_json（含 parse 出的片號）

| lot_id | wafer_id | slot# | ai_result |
| --- | --- | --- | --- |
| A123456 | A123456.01 | 1 | DEFECT |
| A123456 | A123456.02 | 2 | DEFECT |
| A123456 | A123456.03 | 3 | DEFECT |
| A123457 | A123457.01 | 1 | OK |
| A123457 | A123457.02 | 2 | OK |
| A123457 | A123457.03 | 3 |  |
| A123458 | A123458.01 | 1 | OK |
| A123458 | A123458.02 | 2 | OK |
| A123458 | A123458.03 | 3 |  |
| A123459 | A123459.01 | 1 | OK |
| A123459 | A123459.02 | 2 | OK |
| A123459 | A123459.03 | 3 | OK |
| A123460 | A123460.01 | 1 | DEFECT |
| A123460 | A123460.02 | 2 | OK |
| A123460 | A123460.03 | 3 | OK |
| A123461 | A123461.01 | 1 |  |
| A123461 | A123461.02 | 2 |  |
| A123461 | A123461.03 | 3 |  |

## 還開著的 incident

（空）

## 建議 SQL

```sql
SELECT lot_id, work_state, data_error, lifecycle, close_reason FROM v_order_overview;
SELECT * FROM v_order_errors;
SELECT * FROM v_wafer_flags;
SELECT * FROM v_open_incidents;
SELECT lot_id, json_extract(j.value,'$.wafer_id'), json_extract(j.value,'$.ai_result')
FROM hold_order, json_each(wafers_json) j;
```
