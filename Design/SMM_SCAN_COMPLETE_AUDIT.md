# SMM Hold 與 ScanCompletedTime 全面盤點

日期：2026-09-23  
範圍：程式、Markdown、情境 catalog、pytest 與產生的查案頁。  
現行規則來源：[DEV_BASELINE.md](DEV_BASELINE.md)

## 結論

目前掃片完成、Default Hold Release、Release 最後查驗與正常結案，都不再以 SMM Hold、AI Result、Alarm Type 或 Defect Hold handoff 作為條件。

唯一仍會讀 SMM Hold 的業務判斷，是**進站分流**：Default Hold 站上已有設定的 SMMH／AOA 時，不再設本系統 Default Hold，並以 A2-20 寫進 Order DB。A2-20 一旦記錄，後續即使 SMM Hold 消失，仍只等本輪每片 `ScanCompletedTime`；掃完立即 `CLOSED`，不等 settle。

## 程式盤點

| 類別 | 位置 | 現況 |
|---|---|---|
| 唯一有效的 SMM 判斷 | `domain/derive.py` A2-20 | 只決定是否略過 Default Hold；不作完成／Release／結案 gate |
| SMM 身分函式 | `domain/ownership.py:is_smm_hold` | 只供 A2-20 及查案觀察使用 |
| SMM 設定 | `application/settings.py`、`Design/config/app.example.yaml` | 只設定進站分流的 Code／User／Step |
| 查案 Facts | `application/log.py` | 保留 `SmmHold` 原始觀察，狀態欄改名為 `entry_smm_hold_present`，避免誤解成 handoff |
| 掃片完成 | `domain/ai_complete.py` | Expected Wafer 每片有非空 `scan_completed_at` 即完成 |
| Result 空值 | `application/services.py:snapshot` | 保留 `ai_result=None`，另記 `missing_alarm_type=true`；不偽造 `OK` |
| Release／結案 | `request_release.py`、`verify_release.py` | 只處理本系統 Default Hold；不查 SMM Hold |
| Incident 自動結束 | `services.py:maybe_resolve_order_incidents` | 每片掃完即可解一般 Incident；不看 SMM Hold |
| SMM 寫入能力 | `HoldPort`、use cases | `transfer_hold` 介面與 `request_transfer.py` 已移除 |
| 歷史相容名稱 | `domain/enums.py`、`application/logevents.py` | `TRANSFER_HOLD`、`AI_RESULT_INVALID`、`DEFECT_HOLD_UNCONFIRMED` 等只為讀舊 DB／log 保留；現行 derive／pipeline 不產生 |

## 文件盤點

已同步：

- `DEV_BASELINE.md`：明訂只看 `ScanCompletedTime`、A2-20 持久化、SMM 不作 Release／結案 gate。
- `ENTRY_PIPELINE.md`：移除 Defect handoff、SMM Memo transfer 與結案再查 SMM 的流程。
- `SCENARIO_DISCUSSION.md`：D04–D06 改為已決議規則，D05 明訂不再確認 SMM。
- `LOG_CODE_MAP.md`、`ACCEPTANCE_STATE_MACHINE.md`、`OPERATIONS_AND_INVESTIGATION.md`：更新查案用語與 Rule 說明。
- V1／V3：加入現行規則覆寫，並把主要衝突表格更新；歷史設計段落保留時會明示不是現行 gate。
- 維護與架構 review：加入 2026-09-23 狀態註記，避免把舊 transfer／handoff 建議誤當現況。

產生檔 `Design/scenarios.html`、`Design/generated/evidence/*`、decision tree 與樣本 DB 必須由工具重建，不手改。

## 測試盤點

| 要證明的規則 | 測試／情境 |
|---|---|
| Result 空值不偽造 OK，仍可 Release | `test_t12_completed_without_result`、T12 |
| 明確 `INVALID` 也不阻止 Release | `test_scan_completed_invalid_result_still_releases` |
| Defect 沒有 SMM Hold，滿 settle 仍 Release | `test_c09_after_two_minutes_releases_scan_completed`、C09 |
| 進站有 SMM Hold，掃完不等 settle 直接 CLOSED | `test_existing_smm_hold_closes_when_all_scan_times_exist_without_settle`、SMM_SCAN_COMPLETE |
| 進站後 SMM Hold 消失，仍只看 ScanCompletedTime | `test_entry_smm_hold_may_disappear_and_scan_completion_still_closes` |
| Release 最後查驗不要求 SMM Hold 仍在 | `test_release_verification_does_not_require_smm_hold` |
| 不送 transfer、不修改 SMM Memo | `test_agent_never_sends_transfer_hold`、XFER_ACCUM、XFER_RETRY3 |

## 仍需知道的邊界

1. 12 小時是硬候選窗，依 `OperationStartTime` 判斷。超過 12 小時仍 OPEN 的單不再由日常 Pipeline 自動處理；這是已指定政策，但營運上必須另有報表或告警承接老單。
2. A2-04「曾確認的 Default Hold 後來消失即 Manual 結案」仍可能發生在掃片未完成時；這是既有 D01 決議，與 SMM 無關。
3. SMMH／AOA 的進站身分沒有 MES Hold Record ID 或 Rework 欄位。它只造成「不再設 Default Hold」，不會讓程式解除任何 SMM Hold；若現場擔心認錯輪，需另補來源欄位。
4. 舊 enum／event 名稱保留是資料相容選擇。若確認不需讀歷史 DB／log，可另做 schema／資料遷移後完全刪除。

## 回歸驗證

2026-09-23 執行結果：

- `python -m pytest -q`：152／152 通過。
- `python -m vai_hold run-scenarios --backend sqlite`：54／54 情境通過。
- decision tree、情境 HTML、evidence、每題 Order DB 與共用樣本 DB 已全部重建。
- `git diff --check`：無 whitespace error；僅 Git 的 LF／CRLF 工作區提示。
- 本結果是 Fake World／SQLite 的離線 regression，不代表已連真實 MES／SMM 驗證。
