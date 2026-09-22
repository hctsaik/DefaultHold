# 每一題的 SQLite Order DB

現場仍是 MOCK。Order DB 是 SQLite（Oracle 彩排）。每題一個檔，互不覆蓋。

- 題庫／是否通過：`Design/generated/scenario_catalog.sqlite` 的 `scenario_run`
- 本目錄：`C:/code/claude/defaultHold/Design/generated/scenario_orders`
- 啟用 54 題，通過 54，失敗 0
- 缺檔：無

未跑（enabled=0）：

| `T25` | 現場不適用：MES 一定能回答有沒有 Hold，這題不跑 | 題庫關掉，不算驗收 |

| ID | 情境 | 結果 | Order DB | HTML |
|---|---|---|---|---|
| `C01` | C01 送 Hold（原 T01-SET） | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/C01/order.db` | `Design/generated/evidence/C01.html` |
| `T01` | 【串接】進站到結案（對照用，驗收看 C01～C06） | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T01/order.db` | `Design/generated/evidence/T01.html` |
| `C02` | C02 查 Hold 存在（原 T01-CONFIRM） | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/C02/order.db` | `Design/generated/evidence/C02.html` |
| `T02` | 【串接】ENHL 衝突後改 OTHL | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T02/order.db` | `Design/generated/evidence/T02.html` |
| `C03` | C03 等所有 Wafer 掃完（原 T01-WAIT） | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/C03/order.db` | `Design/generated/evidence/C03.html` |
| `T03` | 所有 Hold Code 失敗 | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T03/order.db` | `Design/generated/evidence/T03.html` |
| `C04` | C04 申請解除 Default Hold（原 T01-CHECK） | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/C04/order.db` | `Design/generated/evidence/C04.html` |
| `T04` | Timeout 但 MES 已有 Hold，不重送 | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T04/order.db` | `Design/generated/evidence/T04.html` |
| `C05` | C05 查驗解除（允許 DB Delay） | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/C05/order.db` | `Design/generated/evidence/C05.html` |
| `T05` | Timeout 且查詢 UNKNOWN，不當失敗 | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T05/order.db` | `Design/generated/evidence/T05.html` |
| `C06` | C06 確認已解除才結案（原 T01-RELEASE） | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/C06/order.db` | `Design/generated/evidence/C06.html` |
| `T06` | 送出後重啟只查驗不重送 | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T06/order.db` | `Design/generated/evidence/T06.html` |
| `C07` | C07 ENHL 衝突後同一輪改送 OTHL（原 T02） | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/C07/order.db` | `Design/generated/evidence/C07.html` |
| `C08` | C08 線上代解視為成功（原 T19） | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/C08/order.db` | `Design/generated/evidence/C08.html` |
| `C09` | C09 有 Defect，settle 後解（原 T15） | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/C09/order.db` | `Design/generated/evidence/C09.html` |
| `T09` | 缺一片，繼續等 | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T09/order.db` | `Design/generated/evidence/T09.html` |
| `C10` | C10 Defect 掃完 + settle 申請解除（原 T14-CHECK） | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/C10/order.db` | `Design/generated/evidence/C10.html` |
| `T10` | 數量對但缺＋重，繼續等 | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T10/order.db` | `Design/generated/evidence/T10.html` |
| `C11` | C11 確認已解除才結案（Defect 路徑，原 T14-RELEASE） | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/C11/order.db` | `Design/generated/evidence/C11.html` |
| `T11` | 空 roster 不解 | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T11/order.db` | `Design/generated/evidence/T11.html` |
| `T12` | 有 ScanCompletedTime 即當掃完 | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T12/order.db` | `Design/generated/evidence/T12.html` |
| `T13` | Rework 隔離 | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T13/order.db` | `Design/generated/evidence/T13.html` |
| `T14` | 【串接】Defect 掃完 + settle 走到結案 | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T14/order.db` | `Design/generated/evidence/T14.html` |
| `T16` | Release timeout 但 Hold 已消失 → CLOSED | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T16/order.db` | `Design/generated/evidence/T16.html` |
| `T17` | Release 被拒，Hold 仍在 | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T17/order.db` | `Design/generated/evidence/T17.html` |
| `T18` | 別人的 ENHL 不是我們的 | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T18/order.db` | `Design/generated/evidence/T18.html` |
| `T20` | 人工結案 | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T20/order.db` | `Design/generated/evidence/T20.html` |
| `T21` | 配置站都過了 → Hold 目前站 | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T21/order.db` | `Design/generated/evidence/T21.html` |
| `T22` | 目前 OP100 → Future August OP200 | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T22/order.db` | `Design/generated/evidence/T22.html` |
| `T24` | 已保護不因移站重送 | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T24/order.db` | `Design/generated/evidence/T24.html` |
| `T26` | Watchdog >30 分標 ESTIMATED | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T26/order.db` | `Design/generated/evidence/T26.html` |
| `T27` | 三批超時停用新 Hold | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T27/order.db` | `Design/generated/evidence/T27.html` |
| `T28` | 停用新 Hold 仍可解除 | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T28/order.db` | `Design/generated/evidence/T28.html` |
| `T29` | 覆蓋率不一致 | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T29/order.db` | `Design/generated/evidence/T29.html` |
| `T30` | Orphan Hold 不自動解 | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T30/order.db` | `Design/generated/evidence/T30.html` |
| `T31` | 已結案又出現本系統 Hold | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T31/order.db` | `Design/generated/evidence/T31.html` |
| `T34` | Resume 要 sponsor | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T34/order.db` | `Design/generated/evidence/T34.html` |
| `T35` | 心跳過期 AGENT_STALL | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T35/order.db` | `Design/generated/evidence/T35.html` |
| `T36` | Roster 變更 → MANUAL_REVIEW | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T36/order.db` | `Design/generated/evidence/T36.html` |
| `T37` | 過期進站事件不重建 | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T37/order.db` | `Design/generated/evidence/T37.html` |
| `T38` | Permission 失敗不換備援 Code | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T38/order.db` | `Design/generated/evidence/T38.html` |
| `AI_UNKNOWN` | AI UNKNOWN 不當空掃完 | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/AI_UNKNOWN/order.db` | `Design/generated/evidence/AI_UNKNOWN.html` |
| `HOLD_RETRY3` | SET_HOLD 暫時拒絕同一命令 3 次 | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/HOLD_RETRY3/order.db` | `Design/generated/evidence/HOLD_RETRY3.html` |
| `HOLD_TIMEOUT_RETRY3` | SET_HOLD timeout 查驗後重送 3 次 | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/HOLD_TIMEOUT_RETRY3/order.db` | `Design/generated/evidence/HOLD_TIMEOUT_RETRY3.html` |
| `HOLD_UNKNOWN_NO_RESEND` | 查詢 UNKNOWN 不重送 | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/HOLD_UNKNOWN_NO_RESEND/order.db` | `Design/generated/evidence/HOLD_UNKNOWN_NO_RESEND.html` |
| `REL_RETRY3` | SET_RELEASE 暫時拒絕同一命令 3 次 | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/REL_RETRY3/order.db` | `Design/generated/evidence/REL_RETRY3.html` |
| `REL_TIMEOUT_RETRY3` | Release timeout 且 Hold 還看得到＝Delay，不重送 | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/REL_TIMEOUT_RETRY3/order.db` | `Design/generated/evidence/REL_TIMEOUT_RETRY3.html` |
| `XFER_ACCUM` | 未掃完不改 SMM Memo、不解 Default Hold | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/XFER_ACCUM/order.db` | `Design/generated/evidence/XFER_ACCUM.html` |
| `XFER_RETRY3` | 本 Agent 不送 transferHold | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/XFER_RETRY3/order.db` | `Design/generated/evidence/XFER_RETRY3.html` |
| `T18b` | 別人的 ENHL 不是我們的，自己的 ENHL 設不上就試 OTHL | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T18b/order.db` | `Design/generated/evidence/T18b.html` |
| `T34b` | Resume 有 sponsor | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/T34b/order.db` | `Design/generated/evidence/T34b.html` |
| `REL_OVERDUE_2H` | Release 查驗超過 2 小時開 Incident | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/REL_OVERDUE_2H/order.db` | `Design/generated/evidence/REL_OVERDUE_2H.html` |
| `LOOKBACK_12H` | 只讀最近 12 小時 Operation Start | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/LOOKBACK_12H/order.db` | `Design/generated/evidence/LOOKBACK_12H.html` |
| `SMM_SCAN_COMPLETE` | 已有 SMM Hold；掃完立即結案 | 通過 | `C:/code/claude/defaultHold/Design/generated/scenario_orders/SMM_SCAN_COMPLETE/order.db` | `Design/generated/evidence/SMM_SCAN_COMPLETE.html` |

題庫 `scenario_catalog.sqlite` **沒有** hold_order。查 C09 請開該題 `order.db`：

```sql
SELECT * FROM v_order_errors;
SELECT * FROM v_wafer_flags;
SELECT * FROM v_open_incidents;
SELECT lot_id, work_state, data_error, lifecycle FROM hold_order;
```
