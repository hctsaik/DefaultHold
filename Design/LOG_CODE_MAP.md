# Log ↔ 程式對照

日期：2026-09-19  
用途：從一條 log 找到該改／該查的檔案。事件名是穩定契約，改名必須同步本文件與 `application/logevents.py`。

## 1. 一條 log 長什麼樣子

每筆 INFO 都是：

```text
<event> {"event":"...","function_code":"...","rule_id":"A2-02","order_id":"...","lot_id":"...","ope_no":"...","rework_count":0,"work_state":"..."}
```

必備欄位：

| 欄位 | 用途 |
|---|---|
| `event` | 穩定事件 ID，用這個 grep |
| `run_id` | 同一輪 Pipeline 呼叫（往前往後對同一批 log） |
| `function_code` | 哪一支 Cron／Pipeline |
| `rule_id` | V1 規則（A1-xx／A2-xx／D-xx） |
| `order_id` / `lot_id` / `ope_no` / `rework_count` | 哪一張單 |
| `work_state` | 當下工作狀態 |
| `facts` | 僅 `decision.applied`：進判斷的資料摘要 |

Python logger 名稱：`vai_hold`。

```text
grep '"event": "hold.sent"'
grep '"rule_id": "A2-03"'
grep '"lot_id": "ABC123"'
```

---

## 2. Function code → 檔案（入口）

Cron 只進 `App.run()`，再分派。

| function_code | 檔案 | 函式 |
|---|---|---|
| （全部） | `application/engine.py` | `App.run` |
| `SET_DEFAULT_HOLD_BY_Operation_Start` | `application/pipelines/set_default_hold.py` | `run` |
| `CONFIRM_DEFAULT_HOLD_EXISTS` | `application/pipelines/confirm_hold.py` | `run` |
| `CHECK_AI_SCAN_COMPLETE` | `application/pipelines/check_ai.py` | `run` |
| `CONFIRM_DEFAULT_HOLD_RELEASED` | `application/pipelines/confirm_release.py` | `run` |
| `SMM_EXCEPTION_DEFENSE` | `application/pipelines/defense.py` | `run` |
| `VAI_RESUME` | `application/pipelines/control.py` | `run_resume` |
| `VAI_MANUAL_CLOSE` | `application/pipelines/control.py` | `run_manual_close` |

CLI：`composition/cli.py` → `composition/bootstrap.py` → `App.run`。

---

## 3. event → 檔案（行為）

| event | 何時 | 程式 |
|---|---|---|
| `pipeline.start` / `pipeline.end` | 每支 Pipeline 進出 | 各 `pipelines/*.py` |
| `order.created` | 唯一建單成功 | `pipelines/set_default_hold.py` |
| `discovery.identity_unknown` | 進站缺 Rework／OpeNo | 同上 |
| `order.skip_claim` | 搶不到 claim | 同上 |
| `scope.skip_lot` | Lot 不在 `scope.lot_ids`，拒寫 MES／結案 | `services.refuse_unscoped_lot` |
| `eval.cycle` | `observation_phase=before_action` 是判斷輸入；`after_write` 是寫入後觀察，兩者分開 | `log.emit_decision` |
| `pipeline.end` | 整支 Cron 結束；`outcome=success\|failure`（例外也會有） | `engine.App.run` |
| `decision.applied` | `derive_state` 結果（與 eval.cycle 同一輪） | 同上 |
| `hold.intent` | Intent 落庫、尚未呼叫 MES | `usecases/request_hold.py` |
| `hold.sent` | 即將 `HoldPort.set_hold` | 同上 |
| `hold.receipt` | MES 回覆 ACCEPTED／REJECTED／UNKNOWN | `services.record_receipt` |
| `hold.confirmed` | 查到本系統 Default Hold | `usecases/verify_hold.py` |
| `hold.verify_unknown` | 查詢失敗或 Timeout 未明 | 同上 |
| `hold.failed` | 備援 Code 用盡 | 同上 |
| `release.intent` / `release.sent` / `release.receipt` | 申請解除 | `usecases/request_release.py` |
| `release.not_unique` | MES 對到 0 或 ≥2 筆，不解除 | 同上 |
| `release.confirmed` | 確認已解除並 CLOSED | `usecases/verify_release.py` |
| `release.failed` | 解除失敗、Hold 仍在 | 同上 |
| `transfer.intent` / `sent` / `receipt` / `confirmed` / `failed` | SmmHold memo 累積（Please check #1,#2） | `usecases/request_transfer.py` |
| `incident.opened` | Incident + Outbox | `services.open_incident` |
| `notify.sent` / `notify.failed` | Defense 送信 | `pipelines/defense.py` |
| `control.disabled` | 第 3 批超時停用新 Hold | `pipelines/defense.py` |
| `control.resume` / `control.resume_denied` | Sponsor 恢復 | `pipelines/control.py` |
| `order.manual_closed` | 人工結案 | `pipelines/control.py` |
| `hold.orphan` | 有本系統 Memo 的 Hold 但沒有訂單 | `pipelines/defense.py` D-04 |
| `agent.stall` | 主路徑心跳超過 5 分鐘 | `pipelines/defense.py` D-06 |
| `roster.changed` | Expected wafer 集合變了 | `pipelines/set_default_hold.py` |
| `observation.stale` | 進站事件時間晚於已處理水位 | `pipelines/set_default_hold.py` |

判斷本身不打 MES：`domain/derive.py` 的 `derive_state`。log 上的 `rule_id` 就是它回傳的。

---

## 4. rule_id → 判斷與執行

| rule_id | 意義 | 判斷 | 執行 |
|---|---|---|---|
| A1-01 | 建單 | `derive.py` | `pipelines/set_default_hold.py` |
| A1-02 | 選站 | `derive.py` + `domain/target.py` | `set_default_hold.py` |
| A1-03 | 送 Default Hold | `derive.py` | `usecases/request_hold.py` |
| A1-04 | 換備援 Code | `derive.py` | `request_hold.py` |
| A1-07 | 身分／Flow 不足 | `derive.py` | `set_default_hold.py`（discovery） |
| A1-08 | 停用新 Hold | `derive.py` | `set_default_hold.py` 投影 BLOCKED |
| A2-01 | Hold 查驗未明 | `derive.py` | `usecases/verify_hold.py` |
| A2-02 | Hold 已確認 | `verify_hold.py` 寫死 A2-02 | 同上 |
| A2-03 | HOLD_FAILED | `derive.py` | `verify_hold.py` |
| A2-04 | 線上代解 → `MANUAL_CLOSED` | `derive.py` | `pipelines/confirm_hold.py`（C08；不是 HOLD_MISSING） |
| A2-05 | WAIT_AI | `derive.py` + `domain/ai_complete.py` | `check_ai.py` |
| A2-06 | AI 結果無效 | 同上 | `check_ai.py` |
| A2-09 | 已掃完，未滿 `release.scan_settle_minutes`，暫不解 | `derive.py` | `check_ai.py` |
| A2-21 | 已掃完且滿 settle，申請解除（SCAN_COMPLETED；OK／NG 同一條） | `derive.py` | `usecases/request_release.py` |
| A2-20 | 現場已有 SMM Hold，不設 Default Hold | `derive.py` | `set_default_hold.py` |
| A2-10 | Release 查驗中 | `derive.py` | `usecases/verify_release.py` |
| A2-11 | CLOSED | `verify_release.py` | 同上 |
| A2-12 | RELEASE_FAILED | `verify_release.py` | 同上 |
| A2-13 | 人工結案 | — | `pipelines/control.py` |
| A2-14 | 觀察 UNKNOWN | `derive.py` | `verify_hold.py` / `defense.py` |
| D-01 | Hold > 30 分 | — | `pipelines/defense.py` |
| D-02 | 停用新 Hold | — | `defense.py` |
| D-03 | 覆蓋率不一致 | — | `defense.py` |
| D-05 | 已結案仍有 Hold | — | `defense.py` |

`last_rule_id` 存在 `hold_order.last_rule_id`，DB 與 log 用同一值。

---

## 5. Incident type → 程式

| incident_type | event／來源 |
|---|---|
| `DISCOVERY_IDENTITY` | `discovery.identity_unknown` |
| `HOLD_QUERY_UNKNOWN` / `HOLD_VERIFY_UNKNOWN` | `hold.verify_unknown` |
| `HOLD_FAILED` | `hold.failed` |
| `HOLD_MISSING` / `DEFECT_HOLD_UNCONFIRMED` / `AI_RESULT_INVALID` | `incident.opened`（check_ai） |
| `RELEASE_NOT_UNIQUE` | `release.not_unique` |
| `RELEASE_FAILED` | `release.failed` |
| `HOLD_OVERDUE` | Defense D-01 |
| `COVERAGE_MISMATCH` | Defense D-03 |
| `CONTROL_DISABLED` | `control.disabled` |
| `DATA_UNAVAILABLE` | Defense 查詢 UNKNOWN |
| `STATE_CONFLICT` | Defense D-05 |
| `RESUME_DENIED` | `control.resume_denied` |

---

## 6. Decision 有問題時：Facts / Decision / 動作 怎麼分

每一筆 `decision.applied` 同時帶三塊：

| JSON 欄位 | 是什麼 |
|---|---|
| `facts` | **當下看到的真實資料摘要**（進 `derive_state` 的輸入） |
| `rule_id` / `work_state` / `action` / `reason` | **判斷結果** |
| 同一 `lot_id` 後面的 `hold.sent` / `hold.receipt` / `release.*` | **實際做出去的動作與 MES 回覆** |

`facts` 內容：

```text
hold_query, mes_hold_count, own_hold_count, in_flight,
control, flow_query, ai_status, expected_wafers, ai_views,
missing_wafers, binding_status, codes_attempted, lifecycle
```

對照方式：

| 你看到 | 問題在哪 | 去改／去查 |
|---|---|---|
| `facts` 就錯了（例如 MES 明明有 Hold，但 `hold_query=UNKNOWN` 或 `own_hold_count=0`） | **Facts／觀察／Ownership 對帳** | Fake／Real MES、`services.snapshot`、`domain/ownership.py` |
| `facts` 看起來對，但 `rule_id`／`action` 不該是這個 | **Decision** | `domain/derive.py`（不要先改 Pipeline） |
| `action=SET_HOLD` 且 facts 也該設，但後面沒有 `hold.intent`／`hold.sent` | **Pipeline 沒執行判斷** | 該支 `pipelines/*.py` |
| 有 `hold.sent`，`hold.receipt` 是 REJECTED／UNKNOWN，或送錯 Code／站 | **動作／MES** | `usecases/request_hold.py` 或 MES Adapter |
| `action=SET_RELEASE` 但 `facts.own_hold_count!=1` 仍送出 | **Release Guard** | `usecases/request_release.py` |

時間序（同一 `lot_id`）：

```text
pipeline.start
  → decision.applied   （facts + rule_id + action）
  → hold.intent        （Intent 已落庫）
  → hold.sent          （呼叫 MES）
  → hold.receipt       （MES 回覆）
  → hold.confirmed     （下一輪查驗成功，rule A2-02）
```

Intent 有、receipt 沒有：程式在呼叫 MES 之後、寫回覆之前死掉 → 重跑同一 CONFIRM，不要重送。

---

新增行為時：先在 `logevents.py` 加常數，再 `emit(...)`，最後在本文件加一列。不要寫沒有 `event` 欄位的 log。`decision.applied` 必須帶 `facts`。
