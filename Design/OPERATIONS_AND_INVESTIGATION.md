# 操作與查案入口

日常 pytest **不會**覆寫 `Design/generated`。要更新給人看的 SQLite／HTML：

```text
python -m vai_hold run-scenarios
python -m vai_hold gen-scenario-html
```

## 三份 SQLite 不要搞混

| 檔 | 用途 |
|---|---|
| `Design/generated/scenario_catalog.sqlite` | 題庫＋Expect／actual JSON，**沒有** hold_order |
| `Design/generated/scenario_orders/<題>/order.db` | 該題 Order DB（C09 的 `data_error` 在這裡） |
| `Design/generated/order_db.sqlite` | `gen-order-db` 樣本 Lot，不是 C01 |

## 查案

1. 識別：`lot_id`、`order_id`、`run_id`、`command_id`、`attempt_id`（receipt 上）。
2. `python -m vai_hold investigate --lot LOT1 --log path\to.log`（可加 `--order-id`）。
3. 報告裡 **before_action** 是判斷輸入；**after_write** 是寫入後觀察，不要拿 after 解釋「為何決定」。
4. `recorded_at_utc` 是 log 牆鐘；業務 RecTime 是注入 Clock，兩套時間不要混。
5. 分類：來源 UNKNOWN → `snapshot`／ownership；rule 錯 → `derive.py`；有 sent 無合理 receipt → usecase／MES。

## 常見問句

| 問 | 先看 |
|---|---|
| 為什麼沒 Hold | before_action 的 own_hold／SET；再 `hold.receipt` |
| 為什麼不解 Default Hold | 最後 before_action 的 A2-05（尚缺 ScanCompletedTime）或 A2-09（未滿 settle）；SMM Hold 不參與解除判斷 |
| 重試幾次 | 同一 `command_id` 的 `attempt_no`／`attempt_id` |
| Timeout | receipt UNKNOWN，下一輪 CONFIRM 的 list_holds |

查案命令只產報告，不修單、不打 MES。
