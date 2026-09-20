# Vision AI Preventive Hold Agent — Runtime State 與模擬測試規格 V3

版本：V3 / 2026-09-18  
用途：Agent 1、Agent 2、Defense、DEV 模擬與驗收的共同實作依據。  
狀態：設計基準草案；標示「待確認」的 MES 契約與製程政策，未確認前不得視為正式環境已具備的能力。

## 0. 設計目標與適用範圍

每輪執行遵循：**取得事實 → 推導 State → 產生 Decision → 執行一個 MES 動作 → 下輪重新觀察驗證**。

Agent 不依賴程式上次執行到哪一行，也不以 Order.status 或 API 回傳成功代替現況證據。Order 保存意圖、識別資料與目前的狀態投影；MES/Hold、SMM、AI 等來源提供各自負責的實際事實。

正式環境與 DEV 使用相同的狀態推導、決策、權限守門、紀錄與重試邏輯，僅替換外部讀寫的 Adapter。此設計借用持續觀察現況並推進目標狀態的 Controller / Reconciliation 概念，不要求使用 Kubernetes。[S1]

### 已確認需求

| 項目 | 規則 |
|---|---|
| 啟動事件 | 第一片 Wafer 的 Operation Start；Operation Complete 表示出機 |
| Order 識別 | Lot + 觸發 Operation + Rework Count；跨廠時增加 site/fab namespace |
| 站點 | Config 指定量測站與 Priority，例如 August、Overlay、CDSEM |
| 已經過站 | Config 對應站點都已經過時，改 Hold Current Station |
| 找不到 Config 站 | 依 Flow 的 Process Type，選後續第一個 Process Tool |
| Hold Code | ENHL → OTHL → 第三組待確認 |
| Hold User | ABO；不能單靠 Hold User 辨認本系統的 Hold |
| Ownership | Order Table + Hold Memo + 實際 Hold 識別資料一致 |
| AI 完成 | 本輪整批 Lot 的所有應處理 Wafer 都有 Scan Completed Time |
| AI 無 Defect | 可以申請解除本系統的預防性 Hold |
| AI 有 Defect | 原 AI 系統的異常 Future Hold 已有效建立，才可解除預防性 Hold |
| 異常紀錄 | 每次動作、每次失敗與時間點均可追溯 |
| Hold 失敗 | 最終未成功防守，即使一筆也要告警 Sponsor／線上 |
| Watchdog | 任一筆符合監控條件的預防性 Hold 超過 30 分鐘，線上介入 |
| Defense | SMM 與實際防守狀態有落差要告警並指出 Lot 與原因 |
| 自動停用 | 超過設定批數且超過 30 分鐘，停用新預防性 Hold 並通知值班 |
| 重新啟用 | SMM Sponsor 確認異常 Hold 已解決後才能開啟，不自動恢復 |

### 本版補強，不冒充既有系統能力

本版增加：結果未知狀態、Action Intent、獨立資料品質、精確 Hold Binding、集合核對、可控時鐘、Stateful Fake、並行防重、人工處置與告警交付紀錄。

本系統是非同步防守。若製程要求「絕不能在防守建立前進入特定製程」，必須由製程與 MES 共同定義同步站點／Dispatch 守門條件。不能假設輪詢程式能追回已經開始的實際製程，也不能把「下了 Hold 指令」等同「已有效阻擋」。

## 1. 不可違反的規則（Invariants）

| ID | 規則 |
|---|---|
| I01 | 不得解除無法證明屬於該 Order 的 Hold；不得以 ENHL 或 ABO 做廣域解除。 |
| I02 | 本輪 Expected Wafer 未全部完成有效判斷，不得自動 Release。 |
| I03 | 有 Defect 時，異常 Hold 必須屬於正確 Lot／本輪執行，涵蓋必要 Wafer，且防守位置仍有效。 |
| I04 | API Timeout／斷線／觀察資料過舊，不能直接翻譯為「不存在」或「失敗」。 |
| I05 | 同一邏輯動作尚未排除延遲提交的可能性，不得換 Code 或建立另一筆衝突動作。 |
| I06 | 每個 MES 外部變更前，先持久化 Action Intent；紀錄建立失敗時不執行變更。 |
| I07 | 跨 Rework 不共用完成證據、Hold Ownership、通知識別或動作識別。 |
| I08 | 關閉新 Hold 功能不等於關閉觀察、Agent 2、Watchdog、告警或 Order 建立。 |
| I09 | 同一個 Order 每輪最多一個 MES 寫入動作；告警可由獨立 Dispatcher 同時處理。 |
| I10 | DEV 禁止正式端點與正式憑證；缺情境或 Fake 時立即失敗，不能退回真實服務。 |
| I11 | CLOSED Order 不因「目前沒有 Hold」自動重新 Hold；重工是另一個 Order。 |
| I12 | 發現未預期的人工解除，不可與操作人員自動反覆 Hold／Release；先記錄與升級處理。 |
| I13 | Readiness 未通過的正式 Adapter，不得啟用自動 Hold／Release；尤其要確認精確解除與負向查詢語意。 |
| I14 | AI 資料不可讀會阻止 Release，但不應阻止條件已齊備的首次預防性 Hold。 |

## 2. 識別與時間定義

### 2.1 Order Key

```text
order_key = site_id + lot_id + trigger_operation_id + rework_count
```

trigger_operation_id 是建立本次 Order 的站點，不能隨目前站點變動。current_operation 與 target_hold_operation 為不同欄位。

order_id 為內部不可變識別。若同一 Operation、同一 Rework Count 仍可能重複進站，需增加來源 process_run_id／operation_visit_id；不得用抓資料時間自行推測執行輪次。Rework Count 不明時不能當作 0，先建立 discovery exception。

### 2.2 Hold 識別

每個 Hold Binding 至少包含 order_id、role、MES hold_record_id（若提供）、hold_code、hold_memo、target_step_occurrence、generation 與 active 狀態。

role 區分 PREVENTIVE 與 DEFECT_REFERENCE。原 AI 的 Defect Hold 是交接證據，不是本 Agent 可以解除的資源。

Memo 範例只是格式草案：`VAIPH|order=<id>|rw=<n>|gen=<n>`。Memo 長度、允許字元、MES 是否截斷須確認。若不能完整放入，使用唯一短 token 並在資料庫保存完整映射；不能模糊比對。

多筆 Hold Binding 可以表示經核准的補防守與歷史站點；同一 logical generation 非預期出現多個 Hold，則為重複／不一致事件，不能任意刪除。

### 2.3 時間

紀錄使用帶時區的 UTC，畫面顯示 Asia/Taipei。每筆來源資料保存 event_time（事件實際時間）、observed_at（本程式查到時間）、source watermark/version（來源涵蓋到哪裡）。

分開保存 first_wafer_operation_start、last_wafer_operation_complete、每片 scan_completed_at、整批 ai_completed_at、hold_requested_at、hold_set_at、hold_first_confirmed_at、hold_effective_at（真正卡貨，若來源提供）、release_requested_at、release_confirmed_at。

hold_set_at 無權威值時可使用 first_confirmed_at 做「估計起點」，但要保存時間品質，不能冒充精確時間。重試與切備援 Code 不重設整筆 Order 的原始防守等待起點。

## 3. Facts Snapshot：所有 State 都要能追溯到證據

### 3.1 SourceResult 契約

```text
SourceResult[T]:
  status: FOUND | NOT_FOUND | UNKNOWN | STALE
  value: T or null
  observed_at: timestamp
  source_event_time / watermark / source_version
  error_code / error_message
```

NOT_FOUND 僅用於成功且足夠即時、涵蓋所需範圍的查詢。UNKNOWN 為讀取失敗或無法確認；STALE 為資料成功取得但不符合該動作的 freshness 要求。

若來源是最終一致的列表，即使剛查詢也不必然能排除尚未可見的寫入。必須依來源水位、權威交易查詢或 request status 判定。freshness 不只看本機收到回覆的時間。

### 3.2 Snapshot 欄位

| Facts | 說明 |
|---|---|
| Order / current version | 訂單、目標意圖、人工 disposition、控制版本 |
| Current execution | Lot、Rework、目前 Flow 版本／路徑／站點 occurrence |
| Expected manifest | 本輪應處理的 Wafer ID 集合及版本，來源不能是已出現的 AI Log |
| Actual preventive holds | 本系統候選 Hold、精確識別與有效位置 |
| Defect hold evidence | 原系統建立的正式異常 Hold 與關聯證據 |
| AI evidence | 本輪每片完成時間、結果、任務錯誤與結果版本 |
| Action records | 本次 generation 的 Request、Attempt、未知結果與已確認結果 |
| Active incidents | 目前異常、通知／認領／解決狀態；不以舊 Error 存在與否判定現在失敗 |
| System control | 該作用範圍的 enabled 狀態與版本 |
| Clock | 注入的現在時間，不在規則內直接讀系統時鐘 |

不同來源並非同一筆原子 Snapshot。決策需保存使用的證據 ID／時間，MES 寫入前重查關鍵條件；若 MES 支援 conditional transaction，傳入 expected lot/run/version。若不支援，要記錄競態風險，不能宣稱已達原子保證。

## 4. 狀態模型：主狀態加上可同時存在的子狀態

| 欄位 | 用途／例子 |
|---|---|
| lifecycle | OPEN / RELEASE_PENDING / CLOSED；close_reason 另外記錄 |
| protection_state | NOT_REQUESTED / VERIFYING / PROTECTED / FAILED / MISSING / RELEASED / UNKNOWN |
| ai_state | NOT_READY / PARTIAL / COMPLETE_OK / COMPLETE_DEFECT / ERROR / UNKNOWN |
| work_state | 本輪優先處理的工作，例如 NEED_HOLD、WAIT_AI、READY_RELEASE |
| active_incidents | 可以多筆：AI_TIMEOUT、PROTECTION_GAP、RELEASE_FAILED、DATA_STALE 等 |
| action_state | PREPARED / DISPATCHED / ACKNOWLEDGED / REJECTED / UNKNOWN / CONFIRMED；屬於 Action，不是 Lot 最終結果 |

例如：protection_state=PROTECTED、ai_state=PARTIAL、work_state=WAIT_AI、active_incidents=[HOLD_TIMEOUT] 可以同時成立。

Future Hold 已有效設定時標示 PROTECTED；另用 hold_kind=FUTURE 或 CURRENT 表達它是否已經真正卡住貨。不能把 API 成功一律叫 HELD。

### 4.1 Decision 回傳契約

```text
Decision:
  rule_id
  order_key / order_version / config_version
  work_state / protection_state / ai_state
  owner: AGENT1 | AGENT2 | DEFENSE | MANUAL
  next_action
  action_parameters
  reason_code / human_readable_reason
  evidence_refs
  preconditions
  expected_postcondition
  next_check_at
  incidents_to_open_or_update
```

State Evaluator 是純函式，相同 Snapshot + Config + now 必須得到相同結果。不得直接打 API、讀 DB、寫 Log 或發通知。

## 5. 核心規格表：條件 → State → Action → 驗證

表格中的「有 Hold」均指：本 Order／本輪執行的精確 Ownership 已確認，且 Hold 仍然有效。只看到 Code 相同不算。

### 5.1 共用守門規則

| ID | 實際條件 | Work State | 動作 | 驗證／禁止事項 |
|---|---|---|---|---|
| G01 | 本次動作必要的來源資料不可讀／過舊 | OBSERVATION_UNKNOWN | 重新觀察；持續失敗或已暴露風險時告警 | 不把讀取錯誤當不存在；AI 不可讀不攔阻已具充分資料的首次 Hold |
| G02 | Rework／Order／Memo 身分不明，或無法唯一對應 Hold | MANUAL_REVIEW | 記錄與告警 | 禁止猜測 Ownership 後 Release |
| G03 | 舊動作可能仍在 Server 執行／延遲提交 | ACTION_VERIFY_PENDING | 查 request status 與實際 Hold | 未排除舊副作用前，不換 Code、不送矛盾動作 |
| G04 | 已 CLOSED，且沒有未預期的自有 Hold | CLOSED | 不重新建立 Hold；保留稽核 | Rework 新輪次建立新 Order |
| G05 | 已 CLOSED 卻出現／殘留自有 Hold | CLOSED_WITH_HOLD | 告警、核對晚到 Request／人工動作 | 不以「已結案」為由批次刪除 |
| G06 | 已確認 Hold 非預期消失、或有效防守位置已被跨過 | PROTECTION_LOST | 立即告警；檢查人工紀錄與目前站點 | 禁止當成新訂單默默重建；補防守要經明確 recovery policy／人工授權 |

G01 只影響需要該資料的動作。G03 的「未知」可被足夠的權威證據解除；例如查到精確對應的 Hold 且無其他未結束動作，就可確認成功。

### 5.2 Agent 1：建立與確認防守

| ID | 實際條件 | Work State | 下一動作 | 完成證據 |
|---|---|---|---|---|
| A01 | 偵測本輪 Operation Start，尚無 Order | NEED_ORDER | ensure_order() | 唯一 Key 的 Order 與來源 Event 已持久化；即使系統停用也記錄 |
| A02 | Order 開放、未曾成功防守、確定無 Hold、無未知動作，且允許新 Hold | NEED_HOLD | select_target()；request_hold() | 本輪僅新增 Request，下一輪確認實際 Hold |
| A03 | API 回覆接受／成功，但尚未取得可採信的現況 | HOLD_VERIFY_PENDING | observe_hold() | 精確 Hold 有效存在，才變 PROTECTED |
| A04 | ENHL 明確因 Code 衝突失敗，舊動作已結束，仍有備援 | NEED_BACKUP_HOLD | 下一輪嘗試下一個 Code | 每組嘗試分別留 Action；不得重用不同 payload 的 request_id |
| A05 | 已確認屬於本 Order 的有效 Hold | PROTECTED | 更新投影；交由 Agent 2 評估 AI | 不重複 Hold；舊 Error 保留但不主導現況 |
| A06 | 候選均明確失敗，或權限等不可恢復錯誤使流程確定無法成功 | HOLD_FAILED | 立即建立 Incident／通知線上與 Sponsor | 一筆也告警；保留所有失敗原因 |
| A07 | 有 Order，但系統不允許新增 Hold，且尚未有防守 | SUSPENDED_UNPROTECTED | 保存風險與人工處置責任人，不送 Hold | 不算 PROTECTED，不隱藏在統計外 |
| A08 | 明確暫時性拒絕，允許重試且預算未耗盡 | HOLD_RETRY_WAIT | 等到 next_retry_at，重查條件後重試 | 不以密集掃描代替重試排程；必要時建立等待風險告警 |

正常情況每個 Order 先保護、再判斷，不因 AI 已快速完成而默默新增「跳過 Hold」捷徑。未來若要優化，需另外核准 release/waiver 規則並加入測試。

### 5.3 Agent 2：AI 完成、交接與解除

| ID | 實際條件 | Work State | 下一動作 | 完成證據 |
|---|---|---|---|---|
| B01 | 自有 Hold 有效，但 Expected Wafer 尚未全部完成 | WAIT_AI | 保留 Hold；下輪重查 | 缺哪幾片要可見；Watchdog 獨立計時 |
| B02 | 所有完成時間都有值，但至少一片任務失敗／結果無效 | AI_ERROR | 保留 Hold、記錄並告警 | 不把完成時間視為判斷成功；需確認 AI Log 契約 |
| B03 | 本輪全片完成且結果明確 No Defect | READY_RELEASE | request_release() | API 回傳後仍等待實際 Hold 解除證據 |
| B04 | 本輪全片完成且有 Defect；正式異常 Hold 已有效接手 | READY_RELEASE_TRANSFER | 只 request_release(自有預防性 Hold) | 正式異常 Hold 不能被此動作解除 |
| B05 | 本輪全片完成且有 Defect；異常 Hold 缺失／不適用 | DEFECT_HOLD_MISSING | 保留預防性 Hold，立即告警線上／Sponsor | 原 AI 系統或人工處理異常 Hold；此 Agent 不冒充原系統設碼 |
| B06 | 已送 Release，但結果未知／尚未確認 | RELEASE_VERIFY_PENDING | 查原 Hold record 與必要交接證據 | 不因暫時看不到 Hold 就建立新 Hold |
| B07 | Release 已明確被拒絕，自有 Hold 仍在 | RELEASE_FAILED | 記錄、告警；核准可重試錯誤進入排程 | 重試前重新滿足 Release Guard；不等 30 分鐘才第一次通知 |
| B08 | 對應 Release Intent 存在；權威來源確認所有應解除自有 Hold 已消失；完成／交接條件仍有效 | CLOSED | 記錄 close_reason=OK 或 TRANSFERRED | 留下確認時間、Hold ID、結果版本與證據 |
| B09 | 有核准的人工解除／處置證據 | MANUAL_REVIEW / CLOSED | 驗證處置是否足以結案；不足則保持異常 | close_reason=MANUAL，不能標成自動成功 |

Agent 2 必須讀所有未結案 Order（含失敗、等待確認、停用時發現的 Lot），而非只讀「目前有 ENHL」的 Lot。否則根本 Hold 失敗的 Lot 會被漏掉。

### 5.4 規則衝突與優先序

先處理已結案／人工處置的 lifecycle，再檢查該動作必要資料與 Ownership。未決 Action 先驗證；非預期防守消失先升級。接著才處理正常建立、AI 判斷及 Release。

有效且新鮮的實際 Hold 證據優先於舊失敗 Log。API 回覆未知則不能被「資料表目前沒看到」覆蓋。

規則實作要讓主工作互斥，並保留可並行的 incidents。如果出現未定義組合，回傳 UNCLASSIFIED_STATE + Incident，不得以 default success 結束。

## 6. Hold 站點選擇與有效性

| 條件 | 目標 |
|---|---|
| Config 站名在目前或後續有效路徑中存在 | 先篩出尚未經過且符合防守邊界的候選，再依 Config Priority；同 Priority 選最近 occurrence |
| 選到的候選就是目前站 | 使用 Current Hold（本版建議；需確認 MES 執行語意） |
| Config 站有出現在本輪 Flow，但全部已經過 | 依已確認需求 Hold Current Station |
| 本輪 Flow 完全找不到任何 Config 站 | 第一個目前／後續的 Process Type=Process Tool；目前站可用性需確認 |
| Config 站與後續 Process Tool 都不存在 | 本版建議嘗試 Current Hold；若無法合法執行則立即告警，不默默略過 |
| 讀 Flow／路徑失敗 | UNKNOWN，不等於「找不到 Config」 |
| 執行前 current operation／route version 改變 | 作廢舊計畫、重新選點，不用舊 station 直接送出 |

Operation Number 比較只有在同一條已解析路徑且順序定義可靠時才成立。需以實際路徑 occurrence／ordinal 排序，不能用字串大小或跨 Rework 比數值。Config 的排序不是永遠固定 August → Overlay → CDSEM；此三個只是可設定名稱。

Priority 不能凌駕製程防守邊界。哪個站是最晚安全防守點，需製程確認；若選定站點太晚，需告警／採核准的 Current Hold，不宣稱已防住前面的敏感製程。

## 7. AI Completion 與 Release Guard

### 7.1 完成判定

```text
E = authoritative expected wafer ID set for this execution
C = wafer IDs with valid Scan Completed Time and usable final result for this execution

AI_COMPLETE = manifest_valid AND len(E) > 0 AND E is a subset of C
```

使用 Wafer ID 集合，不用筆數相等。C 必須依本輪 process_run／Rework、任務與結果版本去重，不能從全部歷史 Log 取到一筆完成紀錄就算完成。

若一片有多項必須完成的 scan，先在 wafer 層彙總所有必要任務，再判斷 lot。這是待確認的 AI Log 契約，不自行假設一片只有一筆。

Unexpected Wafer、跨 run 紀錄、manifest split/merge/改變或來源漏資料，應形成 Data Integrity Incident。不能縮小 E 來讓測試或線上資料看起來完成。Manifest 在第一片開始時取得可信完整清單／版本；若尚不能取得，不阻止保護，但阻止 Release。

### 7.2 每次 Release 前都重新檢查

必須同時滿足：Order 仍可處理、執行輪次與權限正確、精確自有 Hold 身分已知、沒有未知／互斥動作、Expected Manifest 有效且全片完成、結果是明確 No Defect 或有效 Defect Hold 接手、必要觀察足夠即時。

不能用「有任意 Future Hold」通過交接，尤其不能拿自有預防性 Future Hold 當成原系統的異常 Hold。

若 MES 支援以 Hold Record ID 解除，優先使用。若僅能按 Code 解除，必須證明此呼叫只影響目標 Hold，否則自動 Release 不得上線。

## 8. Function 入口與 Implementation 分離

### 8.1 核心介面

| Function | 類型 | 責任 |
|---|---|---|
| discover_candidates(cursor) | I/O | 讀 SMM 事件／候選；保存可恢復游標，補掃不得依賴已有 Order |
| ensure_order(event) | DB action | 依唯一 Key 建立或取得 Order，不重複建立 |
| observe_order(key) | I/O | 蒐集帶品質與時間戳的 Snapshot |
| derive_state(snapshot, policy, now) | Pure | 把 Facts 轉成子狀態與工作狀態 |
| decide_next_action(evaluation, role) | Pure | 輸出 Rule、Action、理由、前後條件與 Incident |
| select_hold_target(flow, current, policy) | Pure | 選 station occurrence，不讀 Server |
| request_hold(context, command) | Action entry | 記 Intent、檢查守門、呼叫 HoldPort、記 Request 結果 |
| request_release(context, command) | Action entry | 完整 Release Guard；精確解除；不能直接 CLOSED |
| record_observation_and_decision(...) | DB action | 保存證據與 State 投影，不覆寫歷史 |
| open_or_update_incident(...) | DB action | 維護異常／通知待送紀錄與防重 |
| dispatch_notifications(...) | I/O | 傳送、重試、記交付狀態，不只記已產生通知 |
| evaluate_defense(snapshot, now) | Pure | Watchdog、對帳、停用條件 |

### 8.2 Ports

OrderRepository、SmmPort、FlowPort、HoldPort、AiPort、NotifierPort、Clock、SystemControlRepository。外部健康檢查、認證、背景讀取亦需被 Mode 統一管理。

DEV 用本機 Repository 與 Stateful Fake Ports；PROD 用正式 Adapter。核心 Function 不寫 if lot_id == ... 或 if DEV 分支。啟動時只組裝一次依賴；未知 Mode 直接啟動失敗，不能默認 PROD。

### 8.3 Action 執行契約

1. 以目前 Order version／控制版本重新檢查決策；必要時重讀 MES。
2. 在短 DB transaction 內取得執行權並持久化 Action Intent、參數指紋與 logical action key。
3. transaction 結束後才呼叫外部服務，不長時間持有 DB row lock 等待網路。
4. 記錄 Transport Result：ACKNOWLEDGED、REJECTED 或 UNKNOWN。
5. 下一輪透過實際資料確認 expected postcondition；確認後追加 CONFIRMED Event。

這五步是每個 Action 共用的外殼；不同動作的 implementation 僅處理對應 I/O，不內藏下一個業務動作。

## 9. Retry、並行與重啟恢復

### 9.1 Action Identity

```text
SET logical_action_key = order_id + SET + generation + target_occurrence + hold_code
RELEASE logical_action_key = order_id + RELEASE + hold_record_identity
```

同一邏輯動作的重試沿用 request_id 與 payload；attempt_id 每次不同。換 Code／換目標產生新的 logical action，前一個必須已確定結束。改站或補防守需 generation 與原因紀錄。

Timeout 不代表未執行；Server 可能已成功或仍在處理。AWS 的 idempotent API 設計特別處理重試與晚到請求。[S2] 因此：先查 request status／Hold；若沒有權威的「不會再提交」證據，保持 UNKNOWN 並告警，不用任意等待秒數猜測舊請求已失效。

### 9.2 Error 分類

| 類型 | 處置 |
|---|---|
| Code conflict，且不是本 Order 既有成功 Hold | 明確拒絕後才切下一 Code |
| Rate limit／明確暫時拒絕 | 同一 logical action 有限重試，退避並記 next_retry_at |
| Timeout／網路中斷／意義不明的 5xx | UNKNOWN；驗證先於重試與切碼 |
| Invalid operation／Lot 移站 | 重新觀察與選點，不盲目換 Code |
| Permission／不合法設定／API 契約錯誤 | 告警並停止該動作，不耗完三組 Code 才發現共通問題 |
| Release failed | 保留 Hold、記錄並告警；重試前再跑 Release Guard |

### 9.3 並行

Order Key 設資料庫 UNIQUE。用 CAS version／短 row lock 或具租約的 command claim，防兩個 Worker 同時領到相同動作；若使用 PostgreSQL，其 row locking 能互斥資料列更新，但不能替外部 MES 提供原子保證。[S3]

同 Lot 可能有多個 Rework Order，因此 MES 外部寫入還要以 site+lot 做衝突協調，並於送出前驗證當前 run；不能只靠 Order lock。

租約過期不代表舊 Worker 絕對不會再送出請求。本地 version/fencing 防止舊 Worker 覆寫資料；遠端副作用防重仍需 MES idempotency／conditional command 支援。若不支援，保留 UNKNOWN 並核對，不能宣稱 exactly once。

### 9.4 重啟

啟動後先讀未結案 Order、未確認 Action、未送達通知與來源游標，再重新觀察。既有 Hold 成功但回應／DB 寫回前當機，重啟後應找到同一筆 Hold，而不是發第二次。

已記 Intent 但不確定是否發送過的 Action，不能直接當成「沒送過」。若 DB 不可寫，禁止新增 MES 變更，並由獨立健康監控發出系統告警。

## 10. 資料結構：六類邏輯資料

這是邏輯分層，不要求恰好六張物理表，也不要求完整 Event Sourcing 系統。

| 類別 | 主要欄位／用途 |
|---|---|
| HoldOrder | order_id、唯一 Key、trigger/current/target operation、route/config/manifest version、各狀態投影、next_check_at、row_version、close_reason |
| OrderWafer / Manifest | order_id、wafer_id、required tasks、manifest version、AI run/result ref、完成時間與結果；保存預期集合來源 |
| HoldBinding | role、generation、hold record identity、Code、Memo、目標 occurrence、來源確認時間與有效性 |
| ActionCommand + ActionHistory | logical action key、request_id、attempt_id、payload hash、預期前後條件、started/response/confirmed time、raw result、exception；History append-only |
| Incident + NotificationOutbox | episode key、嚴重度、原因、證據、首次／最近發生、ack/resolved、通知待送／已接受／失敗、通知交付重試 |
| SystemControl + Audit | scope、mode、control version、停用原因／時間、Sponsor 核准人／證據、恢復時間與配置版本 |

每個 Decision 保存 rule_id、reason_code、必要證據參照、演算法規則版本。狀態變化與每次執行的起訖、錯誤都可回放；敏感回應欄位要遮罩。

Incident 去重建議使用 order_id + incident_type + episode_id，同一次事件不每輪狂發，但要更新發生次數。ACK（有人認領）與 RESOLVED（問題已解）分開。

在本地 transaction 內同時寫 Incident 與 NotificationOutbox，可降低「已記錄異常但還沒發通知就當機」的遺漏；通知仍可能重複，因此 Dispatcher/接收端需防重。這符合 transactional outbox 的適用方式，但不會讓 MES 與資料庫變成同一交易。[S4]

## 11. Defense、Watchdog 與停止／恢復

### 11.1 時間要拆開

| 計時 | 起點與用途 |
|---|---|
| setup age | Operation Start 到確認防守；不可等 30 分鐘才發現尚未 Hold |
| request verification age | Request 送出到結果確認；逾時保持 UNKNOWN 並升級 |
| preventive hold age | 本輪最早防守 Hold 的建立起點到解除；本版建議用於 30 分鐘 Watchdog |
| actual blocked age | Lot 真正被站點卡住的時間，若來源提供；另列 Dashboard |
| AI latency / release latency | 各自起訖，不混成一個 Hold Duration |

30 分鐘起點採「預防性 Hold 建立」是本版建議，仍需確認線上是否原本指「真實卡貨起點」。

### 11.2 告警

明確 Hold 流程失敗、Defect Hold 缺失、防守意外消失、Release 明確失敗，立即記錄並告警，不等待 30 分鐘。30 分鐘是額外的持續超時監控。

如果資料來源不可讀，Defense 必須顯示 UNKNOWN／DATA_UNAVAILABLE，不可顯示 0 筆差異即健康。Defense 要有獨立排程／heartbeat 監控；Agent 自己停止時仍需有人知道。

### 11.3 SMM 對帳不是單純數字相減

使用相同 scope、執行輪次、來源水位與觀察時間窗，至少核對：

- 應納管 execution keys 與 Order keys：找漏建 Order。
- 仍需要防守的 execution keys 與有效 Hold 對應 keys：找漏防守。
- 系統 Memo 範圍內實際 Hold 與 HoldBinding／Order：找無訂單 Hold 與結案殘留。

已合法 Release 的 Order、正在驗證的 Request、停用期間未保護的 Lot 要分類，不直接混入「歷史 SMM Count 減目前 Hold Count」。未保護與未知狀態不能被當成成功扣掉。

總數相等仍要比對 Key。例如預期 A/B/C，實際 A/B/D，仍是漏 C、額外 D。依既定需求落差即記錄並告警；訊息要區分進行中、資料未知、確定缺漏，Sponsor 的事件嚴重度依風險與期限升級，而非把所有暫態一律叫永久失敗。

顯示 Order-level 覆蓋率時以完整 execution key 去重；「超時幾批貨」以 distinct site+lot_id 計算，避免同 Lot 多個 Hold Code 重複計數。

### 11.4 系統控制

```text
ENABLED → DISABLED_NEW_HOLD → RECOVERY_PENDING → ENABLED
```

DISABLED_NEW_HOLD 的本版語意：停止所有新的自動 SET_HOLD 指令（含尚未防守的既有 Order）；繼續 Discovery、Order 建立、觀察、AI 判斷、符合 Guard 的 Release、Defense 與通知。若停用原因涉及 Release 通道本身不可信，該動作另依 Source/Action Guard 停止，不能盲目繼續。

系統控制狀態必須持久化；程式重啟不得用 Config 的初始 ENABLED 覆蓋既有停用狀態。

停用後才領出的已排程 Action 必須在 Dispatch 前再次檢查控制版本。已在 MES 執行中的 Request 無法假設能撤回，必須繼續核對。

原話「超過兩批」按字面為 count > 2，即第 3 批觸發。若要第 2 批觸發，需改 count >= 2。無論採哪個門檻，不能保證最多只有兩三批受影響：輪詢與已送出的 Request 仍有延遲及並行窗口。

重新啟用至少具備：SMM Sponsor 確認異常 Hold 已解決／合法處置、根因證據與健康檢查通過、停用期間未保護 Lot 清單已交接、核准人與控制版本已記錄。最後一項是補強建議；Sponsor 確認為已確定需求。

停用不是產品風險已消失。告警必須列出後續未防守 Lot 與核准的人工替代措施；安全要求高的製程應由 MES／現場控制新進機，而非僅停用保護程式。

## 12. DEV：共享、可改變的模擬世界

Scenario Registry 依完整 execution key 選 scenario_id；測試世界的行為與正式程式分離。Agent 1、Agent 2、Defense 共用同一個 Fake World、同一個本機 Repository 與 FakeClock。

Fake World 至少保存 Lot／Wafer／Flow、實際 Hold、AI 任務、待提交 Request、歷史操作與事件排程。呼叫 SET_HOLD 可以改變模擬世界；下一輪 QUERY 讀到改變，不能每次都回固定空列表。

**模擬原始事實與副作用，不直接指定 derive_state 的輸出。** 初始 fixture 可以設定崩潰前留下的 Order／Action 紀錄，但之後的判斷必須由正式 evaluator 產生。

每個 Scenario 分開定義 effect 與 response，例如 effect=CREATE_HOLD、response=TIMEOUT；也可以是 effect=PENDING_LATE_COMMIT、response=TIMEOUT，用來測試不能過早換 Code。

Clock.advance()、run_agent1_once()、run_agent2_once()、run_defense_once() 由測試排程控制；不用真實睡 30 分鐘。隨機測試要固定 seed，並保存失敗事件序列供重播。

DEV 所有外部端點、通知、認證與健康檢查均替換；可用本機記憶體／SQLite 保存模擬 Order。禁止載入正式 credentials，網路 egress 另行封鎖。缺 Mock、未知 Lot fixture、超過情境定義的呼叫、傳入不存在參數，全部讓測試失敗，不默認回成功。

Python 的 autospec/spec_set 可協助限制 Mock 介面與呼叫參數；這仍不能證明 Real Adapter 語意正確，所以還需要測試環境的 Adapter Contract Tests。[S5]

## 13. 驗收測試矩陣

詳細矩陣另附《驗收情境矩陣.md》。至少涵蓋：正常無 Defect、有效異常 Hold 交接、異常 Hold 缺失、少片、重複片、空 Manifest、Rework 舊資料、Code fallback、全部拒絕、Timeout 已成功、Timeout 晚提交、Release Timeout、外人 Hold、意外人工解除、崩潰恢復、多 Worker、路徑移動、30 分鐘邊界、停用／Sponsor 恢復、相同 Count 但 Key 不同、來源不可讀、DEV 禁止聯網與通知故障。

每一個案例驗證 State、Rule ID、外部動作次數與參數、禁止呼叫的動作、Order／History／Incident／Outbox、以及事件順序。不能只驗證最後 state=CLOSED。

成功標準是每個規格 Rule 至少有正例與反例，必要相鄰狀態與故障注入時點均被覆蓋；不是宣稱列出的案例等於現實中所有可能路徑。

## 14. 實作順序與驗收層級

第一階段：固定 Facts／Decision 契約、Pure Evaluator、Rule ID、Shared Fake World，完成核心功能測試。

第二階段：Repository 唯一性、Intent／History、並行 claim、重啟恢復、Outbox 與系統控制。

第三階段：用非生產端點驗證真實 Adapter：Code 衝突、權威負向查詢、Timeout、精確 Release、Flow occurrence、AI 完成語意。

第四階段：經授權的唯讀觀察模式比較系統 Decision 與實際人工判定。唯讀模式只能驗證觀察與決策，不等於驗證寫入安全。

第五階段：核准 scope 小範圍啟用，先有停用與人工接管方法，再擴大範圍。

附帶 YAML 為 Configuration／Scenario 規格範例，不是已完成的 Agent 或已接上 MES 的測試程式。本文件不宣稱真實 Server 的整合測試已執行。

## 15. 上線前必須確認的契約／政策

| 待確認項目 | 未確認前的處置 |
|---|---|
| 第三組正式 Hold Code | PROD 不可把 MOCK_ONLY_HOLD3 或 null 當有效 Code；三碼需求未滿足時 readiness fail |
| MES Hold Record ID、Memo 限制與精確 Release 範圍 | 無法證明只解除目標時，關閉自動 Release |
| Timeout 後 request status、idempotency、負向讀取權威性、late commit 時限 | 未知維持 UNKNOWN，人工介入；不可假設查不到就一定沒成功 |
| Operation／Rework 唯一性、Flow 路徑順序、目前站 Hold 實際攔阻範圍 | 補 run/visit key；規則無法定義時不猜測 |
| Expected Wafer Manifest 的權威來源與 split/merge 規則 | 欠缺名單時不能 Release，不能只從 AI Log 反推 |
| Scan Completed Time 是否保證所有必要 AI 任務成功且結果定稿 | 先把任務錯誤／缺結果視為不可 Release |
| 30 分鐘起點，超過兩批是 >2 還是 >=2 | 本版草案採建立防守起算、>2；投產前由 Sponsor 確認 |
| setup／verification／freshness 的正式 SLA | YAML 的數字只供 DEV，不可直接當正式保護時限 |
| Pause scope、人工替代措施與恢復 backlog | 明確指定責任人，不把停用當成風險解除 |
| 製程最晚防守邊界 | 不允許 Priority 選到已無法防守敏感製程的站點而仍顯示安全 |

## 參考來源

以下是通用工程設計依據，不是對廠內 MES 能力的證明。

[S1] Kubernetes — Controllers：https://kubernetes.io/docs/concepts/architecture/controller/

[S2] AWS Builders' Library — Making retries safe with idempotent APIs：https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/

[S3] PostgreSQL — Explicit Locking：https://www.postgresql.org/docs/current/explicit-locking.html

[S4] AWS Prescriptive Guidance — Transactional outbox pattern：https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html

[S5] Python — unittest.mock：https://docs.python.org/3/library/unittest.mock.html
