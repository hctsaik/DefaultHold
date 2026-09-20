# Order DB 樣本（給人看的）

檔案：`C:/code/claude/defaultHold/Design/generated/order_db.sqlite`

Wafer id 是現場格式 `A123456.01`；片號是小數點後面的 `01` → memo `#1`。

| Lot | 故事 | 你該看到 |
|---|---|---|
| A123456 | C09 掃完 Defect、無 SMM Hold、已滿 2 分鐘 | 申請解除；`close_reason=SCAN_COMPLETED` |
| A123457 | T12 `.03` 有掃完時間、沒 Alarm Type | 當掃完；`order_wafer.missing_alarm_type=1` |
| A123458 | C03 還缺一片 | `WAIT_AI`，沒 Release |
| A123459 | 全 OK | `CLOSED` / `AI_OK` |
| A123460 | Defect + SMM Hold | `CLOSED` / `TRANSFERRED` |
| A123461 | 線上把 Default Hold 解掉 | `MANUAL_CLOSED`（沒有結案 GUI，Hold 沒了就結案） |

## hold_order

| lot_id | work_state | data_error | lifecycle | close_reason | last_rule_id |
| --- | --- | --- | --- | --- | --- |
| A123456 | CLOSED |  | CLOSED | SCAN_COMPLETED | A2-11 |
| A123457 | CLOSED |  | CLOSED | AI_OK | A2-11 |
| A123458 | WAIT_AI |  | OPEN |  | A2-05 |
| A123459 | CLOSED |  | CLOSED | AI_OK | A2-11 |
| A123460 | CLOSED |  | CLOSED | TRANSFERRED | A2-11 |
| A123461 | MANUAL_CLOSED |  | MANUAL_CLOSED | MANUAL | A2-04 |

## order_wafer（含 parse 出的片號）

| lot_id | wafer_id | slot# | ai_result | missing_alarm_type |
| --- | --- | --- | --- | --- |
| A123456 | A123456.01 | 1 | DEFECT | 0 |
| A123456 | A123456.02 | 2 | DEFECT | 0 |
| A123456 | A123456.03 | 3 | DEFECT | 0 |
| A123457 | A123457.01 | 1 | OK | 0 |
| A123457 | A123457.02 | 2 | OK | 0 |
| A123457 | A123457.03 | 3 | OK | 1 |
| A123458 | A123458.01 | 1 | OK | 0 |
| A123458 | A123458.02 | 2 | OK | 0 |
| A123458 | A123458.03 | 3 |  | 0 |
| A123459 | A123459.01 | 1 | OK | 0 |
| A123459 | A123459.02 | 2 | OK | 0 |
| A123459 | A123459.03 | 3 | OK | 0 |
| A123460 | A123460.01 | 1 | DEFECT | 0 |
| A123460 | A123460.02 | 2 | OK | 0 |
| A123460 | A123460.03 | 3 | OK | 0 |
| A123461 | A123461.01 | 1 |  | 0 |
| A123461 | A123461.02 | 2 |  | 0 |
| A123461 | A123461.03 | 3 |  | 0 |

## 還開著的 incident

（空）

## 建議 SQL

```sql
SELECT lot_id, work_state, data_error, lifecycle, close_reason FROM v_order_overview;
SELECT * FROM v_order_errors;
SELECT * FROM v_wafer_flags;
SELECT * FROM v_open_incidents;
SELECT lot_id, wafer_id, ai_result, missing_alarm_type FROM order_wafer ORDER BY lot_id, wafer_id;
```
