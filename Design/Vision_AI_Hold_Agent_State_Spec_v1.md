# Vision AI Preventive Hold Agent
## 執行狀態、動作入口與 DEV 模擬規格 V1

日期：2026-09-18  
用途：Agent 1／Agent 2 實作、設計評審、DEV 情境測試與上線驗收。  
狀態：設計提案；使用者已確認的業務規則予以保留，新增防護與介面契約仍須在實際系統整合時驗證。本文不代表已連線 MES／SMM 或已完成正式系統測試。

## 1. 設計摘要

每輪工作固定為：讀取實際資料 → 正規化 Facts → 推導 State → 選擇 Action → 記錄意圖 → 執行 Implementation → 記錄結果 → 下一輪重新觀察驗證。

正式環境與 DEV 使用相同的判斷與動作入口。DEV 只替換外部資料來源、執行實作與時鐘，不直接指定 State，也不略過正式判斷。

本設計採反覆對帳的控制迴圈概念；並不要求使用 Kubernetes、工作流產品或另建微服務。[R1]

### 1.1 已確認的業務規則

| 項目 | 規則 |
|---|---|
| 觸發點 | 本輪第一片 Wafer 的 Operation Start |
| 時間名詞 | 進機為 Operation Start；出機為 Operation Complete |
| 訂單識別 | Lot + 觸發 Operation + Rework Count |
| 預防性 Hold | ENHL → OTHL → 第三組待確認；Hold User = ABO |
| Ownership | 必須比對 Order Table 與 Hold Memo，並識別實際 Hold |
| Hold 站點 | 按 Config Priority 找 August／Overlay／CDSEM 等；無配置站點時找 Process Type 對應的 Process Tool；配置站點均已通過時 Hold 現在站點 |
| AI 完成 | 本輪整批 Lot 所有預期 Wafer 都有 Scan Completed Time |
| 正常解除 | AI 完成且無 Defect，或 AI 完成有 Defect且正式異常 Future Hold 已確認接手 |
| 異常 | Hold 未成功必須記錄原因；確認防守失敗即使一筆也通知線上／Sponsor |
| Watchdog | 超過 30 分鐘需介入 |
| Defense | SMM 應防守 Lot 與實際防守比對；系統性逾時可自動停用新 Default Hold |
| 恢復 | 問題解決後，經 SMM Sponsor 確認才重新 Enable |

### 1.2 必须維持的安全不變條件

| ID | 不變條件 |
|---|---|
| I01 | 不解除其他系統、其他訂單或其他 Rework 輪次的 Hold。 |
| I02 | 查詢失敗／資料過舊不等於「沒有 Hold」。 |
| I03 | Timeout 不等於動作沒有發生；結果未明前不盲目重送或換 Hold Code。 |
| I04 | 未證明本輪整批 Wafer 完成且結果有效，不自動 Release。 |
| I05 | 有 Defect 時，未確認有效的正式異常 Hold 接手，不自動 Release。 |
| I06 | API 回覆受理不等於實際效果已完成；結案需重新查驗。 |
| I07 | 歷史 Exception 不直接決定目前 State；後續成功不抹除歷史錯誤。 |
| I08 | 同一 Order 的未確定修改命令不並行；重複掃描不產生重複 Order。 |
| I09 | DEV 不連正式外部服務；缺少 Mock／Scenario 立即失敗，不回退 PROD。 |
| I10 | 關閉 Default Hold 不等於停止查驗、通知、對帳或符合條件的 Release。 |
| I11 | 停用期間未防守 Lot 必須可見，不得假裝成功或自動排除風險。 |
| I12 | 每個決策可追到 Rule ID、Facts、Policy Version 及 Action。 |

## 2. 識別與資料範圍

### 2.1 Order Key

`OrderKey = (lot_id, origin_operation_id, rework_count)`。

`origin_operation_id` 是啟動這筆防守的原始 Operation，不是會隨 Lot 移動而改變的 Current Operation。三個欄位不得為 NULL；Rework Count 取不到不得默認為 0。

另設不可變的 `order_id` 作為內部關聯 ID。跨廠共用資料庫且 Lot ID 不全域唯一時，將 `site_id` 納入唯一性範圍。若 MES 證實同一組三欄仍可能重複進站，另加入 MES 的 `visit_id`／`operation_start_event_id`，不能僅靠時間字串猜測輪次。

DB 必須有組合 UNIQUE／NOT NULL 限制，而非只有「先查、再新增」。複合唯一約束及 NULL 行為需依實際 DB 驗證。[R3]

### 2.2 Hold Identity

建議 Hold Memo 攜帶系統識別與唯一 Order Token，例如：

`VAI_PREVENTIVE|order=<order_id>|rw=<rework_count>`

實際字元、長度、截斷與精確查詢能力待 MES 契約確認。不得只用模糊子字串比對。識別至少包含：Lot、Order Token、實際 Hold Code、Memo；有 MES Hold ID 時一併保存並優先用它指定解除對象。

`ABO` 是共用 Hold User，不能單獨證明 Ownership。正式 Defect Hold 與本系統 Preventive Hold 必須有不同的用途識別，不得拿預防性 Hold 自己證明「正式異常已接手」。

### 2.3 Rework 資料隔離

Order、Wafer Roster、AI Result、Hold Binding、Action、Exception、Scenario 均須關聯本輪 OrderKey／Visit。Rework 0 的完成時間或 Hold 不可供 Rework 1 使用。

Lot Split／Merge、輪次不明、Wafer Roster 改變時，不自動把母批／舊批證據套用新批；進入 MANUAL_REVIEW 並告警，待有正式承接規則後再支援。

## 3. Facts：外部資料觀察契約

### 3.1 Observation Envelope

所有查詢入口回傳正規化 Observation，而非只回傳 True／False。

| 欄位 | 說明 |
|---|---|
| outcome | PRESENT／ABSENT／UNKNOWN；集合可為已確認空集合 |
| value | 本次查到的資料；UNKNOWN 不可假裝成空資料 |
| queried_at | 程式執行此次查詢的時間 |
| source_as_of | 來源證明的資料時間／水位；不能用 queried_at 代替來源新鮮度 |
| source_version | 來源版本／交易序號；有則保存 |
| source_name | 實際資料來源／介面版本 |
| error | 查詢失敗、權限、逾時、格式異常等原因 |
| evidence_ref | 本次觀察證據／Snapshot 的可追溯 ID |

「剛查完報表」不代表「報表內容沒有延遲」。用來確認 Hold／Release 的來源必須能提供足夠即時、涵蓋完整目標集合的權威證據。無此能力時維持 UNKNOWN，不以單次查無資料斷言沒有 Hold。

新鮮度與必要欄位採 Action-specific Guard：AI Log 暫時不可用不能阻止安全建立預防性 Hold，但一定會阻止自動 Release。

### 3.2 Lot Snapshot

| 欄位 | 內容 |
|---|---|
| identity | OrderKey、Order ID、Current Visit／Rework |
| order | 訂單、版本、結案原因、是否人工接管 |
| lot_position | Current Operation、Flow／Route Version、位置版本 |
| preventive_holds | 活動 Hold 與尚未觸發的 Future Hold；用途與 Ownership |
| actions | 本 Order 的未完成命令及相關嘗試 |
| roster | 本輪預期 Wafer ID 集合與有效版本 |
| ai | 每片本輪 Scan Completed Time、結果、結果版本 |
| defect_holds | 正式異常 Hold 的實際狀態與涵蓋範圍 |
| incidents | 尚未解決的 Exception／人工處置 |
| control | 系統停用狀態與設定版本 |
| now | 注入的時鐘時間 |

Snapshot 是觀察集合，不能假設跨系統原子一致。記錄每個來源的時間與版本；執行 Hold／Release 前重新檢查該動作必要的條件。

## 4. State：避免一個 Status 承載所有事情

### 4.1 建議保存的狀態面向

| 面向 | 主要值 |
|---|---|
| lifecycle | OPEN／CLOSED／MANUAL_CLOSED |
| protection | NONE／SET_PENDING／CONFIRMED／UNKNOWN／FAILED／LOST／RELEASE_PENDING／RELEASED |
| ai | UNKNOWN／WAITING／COMPLETE_OK／COMPLETE_DEFECT／INVALID |
| next_action | CREATE_ORDER／SELECT_TARGET／REQUEST_HOLD／VERIFY_HOLD／WAIT_AI／VERIFY_DEFECT_HOLD／REQUEST_RELEASE／VERIFY_RELEASE／ESCALATE／NONE 等 |
| incidents | 可同時存在的例外，例如 AI_TIMEOUT、NOTIFICATION_FAILED |

例：protection=CONFIRMED、ai=WAITING、incidents=[AI_TIMEOUT]。不能把 State 改成 AI_TIMEOUT 後，反而不知道 Hold 是否還在。

另由上述欄位導出 `display_state`，供 Dashboard 與工程師閱讀，例如 WAIT_AI、RELEASE_VERIFY_PENDING、HOLD_FAILED。下方規格表的 State 主要指此執行／顯示狀態。

資料庫的 last_evaluated_state 是快取與追蹤資訊，不是唯一真相；每次執行仍重新讀取 Facts。Historical Intent、正式人工處置與已確認結案證據則是決策所需的持久資料，不能遺失。

### 4.2 決策入口

`derive_state(snapshot, policy, now) -> StateAssessment`

`plan_action(assessment, actor, control) -> Decision`

兩者是無 I/O 的 Pure Function。相同輸入、設定版本、時間與 Actor，必須產生相同輸出。

Decision 至少包含：`rule_id, display_state, state_reason, business_action, required_guards, evidence_refs, next_check_at, alerts, policy_version`。

每輪每個 Order 最多選一個改變外部 Hold 狀態的 business_action。告警可在同轮寫入 Outbox，不能因為「只能做一動」而把安全告警推遲到後面。

## 5. 核心規格表

### 5.1 判斷優先序

先驗證 Identity 與人工／結案情況；再處理未確定的修改命令；再判斷目前防守；最後才判斷 AI 與 Release。告警是可並行的判斷結果，不應被較低優先序覆蓋。

已有 Release 意圖且符合驗證條件時，Hold 消失優先解讀為待確認 Release，不得又判成 NEED_HOLD 而重新上 Hold。已結案 Order 不因没有 Hold 而再啟動。

當資料只能支持 UNKNOWN 時，不把任何涉及該資料的安全 Guard 視為通過。

### 5.2 Agent 1：發現、建單與建立防守

發現 Operation Start 應支援可重播的事件／歷史查詢與持久化游標，不能只依賴「這一秒還在 Operation Start 的 Lot」。游標推進須與已接收事件／已建立待辦的持久紀錄協調；時間窗可重疊，靠 OrderKey／Source Event ID 去重。重新啟動應能補掃停機期間的事件，並由 SMM 獨立對帳找出漏單。

| Rule | Facts／前提 | State | Action | 成功驗證／限制 |
|---|---|---|---|---|
| A1-01 | 本輪首片 Operation Start；Identity 已知；Order 不存在 | NEED_ORDER | create_order | DB 依唯一鍵確認一筆；建立後重新觀察 |
| A1-02 | Order OPEN；沒有有效 Target；Flow／位置可用 | NEED_TARGET | select_hold_target | 保存站點、選擇原因、Flow／Config Version |
| A1-03 | 有 Target；確認無本 Order Hold；未送過設定命令或上一命令已確認無效果；本輪允許執行 | NEED_HOLD | request_hold | 執行前重驗位置／訂單版本；後續由實際查詢確認，非 API 回覆即成功 |
| A1-04 | 確認本次 ENHL 沒有設定成功；原因允許換 Code；無未確定命令 | NEED_BACKUP_HOLD | request_hold 使用下一組 | 只有 Code-specific Conflict 等可補救情況依序切換；新 Code 為不同邏輯命令 |
| A1-05 | 存在本 Order 有效 Hold，且覆蓋防守需求 | PROTECTION_CONFIRMED | 不再新增 Hold | 交由 Agent 2 追蹤；不得因舊 Exception 再 Hold |
| A1-06 | Order 已合法 CLOSED／MANUAL_CLOSED，且無矛盾證據 | CLOSED | 不再建立 Hold | 相同輪次重掃為 No-op；新 Rework 應建立新 Order |
| A1-07 | 無法取得可證明安全的站點、Identity 或必要 MES 資料 | MANUAL_REVIEW／OBSERVATION_UNKNOWN | 記錄並告警／重查 | 不假造 Rework Count、不用錯輪次或過期站點 |
| A1-08 | Default Hold 停用；發現新的應防守 Lot | BLOCKED_BY_CONTROL | 建立／保留待處理風險紀錄，通知人工接管 | 不新增自動 Hold；不得標示防守成功；持續列入未防守追蹤 |

### 5.3 Agent 2：獨立查驗、AI 判斷與解除

Agent 2 從所有未結案 Order／待驗證命令開始查，不是只撈目前已經有 Hold 的 Lot。

| Rule | Facts／前提 | State | Action | 成功驗證／限制 |
|---|---|---|---|---|
| A2-01 | 有設定命令，尚未完成查驗，包括 Accepted、Timeout、程式中斷 | HOLD_VERIFY_PENDING | verify_hold | 查實際 Active／Future Hold；未明前不得換 Code／盲目重送 |
| A2-02 | 本輪本 Order 的有效 Hold 已確認存在 | PROTECTION_CONFIRMED | 綁定 Hold、記錄查驗證據；下一輪檢查 AI | 舊失敗紀錄仍保留，不阻擋目前成功 |
| A2-03 | 權威來源確認無 Hold；本次設定流程已確定失敗且無可執行備援／錯誤不可恢復 | HOLD_FAILED | open_incident + enqueue_alarm | 即使一筆也通知；記錄未防守風險；不等 30 分鐘 |
| A2-04 | 曾確認有 Hold，現在沒有；沒有合法 Release 意圖／人工處置 | HOLD_MISSING | 告警、查原因；符合明確修復政策時交 Agent 1 補防守 | 不誤當新單；重 Hold 必須重新確認當前站點 |
| A2-05 | Hold 存在；本輪 Wafer Roster 未確定或有任何一片 Scan 未完成 | WAIT_AI | 稍後重查；同時執行 Watchdog | 不 Release；空 Roster 不算完成 |
| A2-06 | Scan 時間都有，但結果缺值、輪次不符或結果資料互相矛盾 | AI_RESULT_INVALID | 保留 Hold、記錄例外並通知 | 不把空結果當 OK |
| A2-07 | 本輪整批完成，所有結果有效且無 Defect；本 Order Hold 可精確識別 | READY_RELEASE_OK | request_release | 執行前重新驗證 Release Guard；之後必須 verify_release |
| A2-08 | 本輪整批完成且有 Defect；有效正式異常 Hold 已確認涵蓋本次異常 | READY_RELEASE_HANDOFF | request_release | 只解除本 Order 的預防性 Hold，不碰正式 Defect Hold |
| A2-09 | 有 Defect；正式 Hold 尚未確認，包含缺少、錯站、錯輪次或來源未知 | DEFECT_HOLD_UNCONFIRMED | 保留防守、立即告警並重查 | 已記錄的正式 Hold Failure 保留其原因；未知不假裝成成功 |
| A2-10 | 已送 Release 命令，尚未確認結果或發生 Timeout | RELEASE_VERIFY_PENDING | verify_release | 查該 Hold ID／Token 的效果，不直接結案、不重建 Hold |
| A2-11 | 正確 Release 命令可追溯；權威證據確認本 Order 所有應解除 Hold 均已解除；有 Defect 時正式保護仍有效 | CLOSED | 保存結案原因與確認時間 | 外部其他 Hold 不影響本 Order 的正常結案，不得順便解除 |
| A2-12 | Release 明確失敗，Hold 仍在 | RELEASE_FAILED | 立即留 Error／告警；僅按策略重試 | 不等 30 分鐘才記錄；Watchdog 獨立運作 |
| A2-13 | 有經授權的人工處置及 MES 解除證據 | MANUAL_CLOSED 或待人工確認 | 記錄操作者、原因、批准人與風險處置 | 不能標成 AI_OK；不憑 Hold 消失推定已人工批准 |
| A2-14 | 必要 Hold／Order 查詢失敗或來源不足以證明不存在 | OBSERVATION_UNKNOWN | 依來源重試與告警 | 不 Release；不將未知轉成 ABSENT；可執行不依賴失敗資料的其他安全工作 |

### 5.4 Defense／資料矛盾規格

| Rule | Facts／前提 | State／Incident | Action | 成功驗證／限制 |
|---|---|---|---|---|
| D-01 | 依定義計算的預防性 Hold 年齡 > 30 分鐘 | HOLD_OVERDUE | 通知線上／Sponsor；標明 AI、Release、正式 Hold 等原因 | 留 Hold Created 與實際 Active 時間，不混為一談 |
| D-02 | 同範圍超時的不同 Lot 數量 > 2 | CONTROL_DISABLED | 原子設定停用、記錄原因、送告警與值班通知 | 「> 2」為第 3 批；非「>= 2」 |
| D-03 | SMM 應防守集合與實際有效防守集合不同 | COVERAGE_MISMATCH | 列出缺少、多餘、重複及未知項；告警 | 不是只比總數；依本輪 OrderKey 比對 |
| D-04 | 有屬於本系統的 Hold Token，但 Order 找不到 | ORPHAN_HOLD | 告警、查驗／修復關聯 | 未建立可信 Ownership 前不自動解除 |
| D-05 | Order CLOSED 但本 Order Hold 又被確認存在，或有多筆重複 Hold | STATE_CONFLICT | 告警與對帳 | 不自動忽略、不用 Hold Code 整批清除 |
| D-06 | Agent 心跳／成功掃描／資料來源水位停滯 | AGENT_UNHEALTHY | 由獨立監視點告警 | 不能只依靠已當機的 Agent 自己告警 |
| D-07 | Incident 已寫入，通知仍未成功送達／未被接手 | NOTIFICATION_PENDING | 重送與升級；保留 delivery/ack 狀態 | Log 存在不代表 Sponsor 已知道 |

## 6. Hold Target 選擇規格

| 情況 | 選擇結果 |
|---|---|
| Config 匹配站點仍在當前或後續 Flow | 先排除已通過的候選，再依 Config Priority 選站型；同順位取最近的有效站點 |
| 被選中的站點就是 Current Operation | 使用 Current Hold 語義，而不是對已到站位置再掛未來站 |
| Flow 曾有配置站點，但全部已通過 | 依使用者規則直接嘗試 Hold Current Station |
| 本 Flow 根本沒有配置站點 | 依 Flow 中的 Process Type 找第一個當前／下游可用 Process Tool |
| 找不到 Process Tool | 建議嘗試 Current Station 作為防守；須通過 MES 合法性與製程安全條件，否則告警人工接管 |
| 執行前 Current Operation／Flow Version 改變 | 丟棄舊 Target 決策，重新選擇；不能沿用過期參數 |
| 讀不到 Flow 或無法判斷順序 | UNKNOWN，不能把讀取失敗當作「配置站點不存在」 |

在 MES 證明 Operation Number 能代表本輪 Flow 順序時才用數字比較；不要以字串大小比較，也不要跨不同 Route／Rework 直接比較。Config Priority 是使用者設定，不能把 August→Overlay→CDSEM 固定寫死在程式。

需要製程端定義「最晚安全防守站點」與 Current Hold 是否會影響已進行中的加工。Caller 重新查一次 Current Operation 不能單獨消除所有競態；MES 若提供條件式 Hold／位置版本檢查，應使用它。不支援時必須承認仍有時間窗，經製程端接受後上線。Hold 不能追回已完成的不可逆製程。

## 7. AI 完成與 Release Guard

### 7.1 AI 完成

`expected_wafer_ids` 來自本輪權威 Lot／Wafer Roster，不可由「已出現在 AI Log 的 Wafer」反推。

完成條件：

- Roster 已確認、非空，且與當前 Order／Visit 相符。
- 每個預期 Wafer 都有本輪的有效 Scan Completed Time。
- 每個 Wafer 都有已完成提交的有效判斷結果；結果缺值、錯誤或版本矛盾不是 OK。
- 重複 Log 依明確版本／任務規則去重，不用列數代替 Wafer ID 集合覆蓋。
- Roster 有 Split／Merge／移片變更時重新驗證，不自動沿用舊集合。

可比較 `expected_set - completed_set`；差集為空只是必要條件，還需非空 Roster 與有效結果。Operation Complete 不等於 AI Complete。

### 7.2 Release 前全部必須通過

| Guard | 必須具備的證據 |
|---|---|
| G01 Ownership | 欲解除的每筆 Hold 都精確屬於本 Order |
| G02 Cycle | 當前資料仍是同一 Operation／Rework／Visit |
| G03 Completion | 本輪整批 AI 已完成且結果有效 |
| G04 Quality | 無 Defect；或正式異常 Hold 已有效接手且涵蓋範圍正確 |
| G05 No conflict | 無未解的修改命令、人工接管衝突或阻止 Release 的 Incident |
| G06 Freshness | 本次必要證據仍符合新鮮度／版本契約 |
| G07 Precision | Release 介面可以精確指定本系統 Hold，不會解除別人的 Hold |

Default Hold 已停用不應單獨阻止符合以上條件的既有 Order 安全 Release。若實際 MES 只能按共用 Hold Code 大範圍解除，則 G07 不成立，不能假設現有接口安全。

## 8. Function 入口與 Implementation 契約

### 8.1 分層

| 層 | Function 範例 | 是否允許外部 I/O |
|---|---|---|
| 排程與協調 | agent1_tick、agent2_tick、defense_tick、reconcile_order | 可透過注入的 Ports |
| 觀察 | observe_lot、observe_hold、observe_ai、load_order | 只能經 Repository／Gateway |
| 規則 | derive_state、plan_action、evaluate_release_guard、choose_hold_target | 不允許 |
| 動作入口 | create_order、request_hold、verify_hold、request_release、verify_release、raise_alarm | 管理共同 Guard／Journal／呼叫底層 |
| 外部實作 | RealMesGateway、FakeMesGateway 等 | PROD 實作連線；DEV 不連正式服務 |

### 8.2 動作入口表

| Function | 主要輸入 | 共同責任 | 可替換 Implementation |
|---|---|---|---|
| create_order | OrderKey、Start Event、Policy Version | 唯一性、建立事件、訂單落庫 | OrderRepository |
| select_hold_target | Flow、Current Position、Config | 純規則選擇；保存選擇理由 | FlowGateway 只負責提供資料 |
| request_hold | Order ID、Target、Code、Memo、Command ID | 重驗 Guard、持久化意圖、呼叫、記錄 Receipt | MesGateway.set_hold |
| verify_hold | Order ID、Command、Hold Token | 查所有相關 Hold、Ownership 與效果 | MesGateway.list_holds／transaction_status |
| check_ai_completion | 本輪 Roster、AI Observation | 集合覆蓋、結果／輪次檢查 | AiGateway.read_results |
| check_defect_hold | Order、Defect Coverage | 確認正式異常 Hold 接手 | MesGateway 查詢 |
| request_release | 精確 Hold Binding、Command ID | 重驗 Release Guard、記錄意圖與 Receipt | MesGateway.release_hold |
| verify_release | Release Command、Hold Binding | 確認解除與正式保護；保存結案證據 | MesGateway 查詢 |
| raise_alarm | Incident、Order、Severity | 去重、持久化 Outbox | NotificationGateway |
| disable_new_holds | Scope、Reason、Evidence | 控制版本、停用事件、通知 | ControlRepository |
| approve_resume | Sponsor、Resolution、Evidence | 授權／健康檢查／審計 | ControlRepository／AuthGateway |

每個 Action 的入口是共用業務程式；DEV 不可以換掉整個 request_hold 以跳過 Guard 和紀錄。只替換最底層 Gateway。

### 8.3 Action Receipt

| outcome | 定義 | 後續 |
|---|---|---|
| NOT_SENT | 尚未對外送出，例如本地 Guard 未通過或序列化失敗 | 記錄原因；修正後重新決策 |
| ACCEPTED | 對方受理／回應成功，但尚未以權威資料驗證副作用 | 進 VERIFY_PENDING |
| REJECTED | 介面契約可證明明確拒絕，且沒有產生副作用 | 按錯誤分類重試／備援／告警 |
| UNKNOWN | Timeout、斷線或中斷，無法確定是否已執行 | 先查驗；不可當 REJECTED |

Receipt 同時記錄 command_id、attempt_id、provider_request_id、started_at、finished_at、raw_error_code、normalized_error、retry_class、response_evidence。

只有查驗入口才能將效果標成 CONFIRMED。若 MES 的成功回覆本身具有已提交且可證明的語義，可以記錄該證據，但本設計仍要求後續對帳驗證。

## 9. 併發、重啟與重試

### 9.1 命令身份

一個邏輯命令有固定 `command_id` 與 `idempotency_key`。同參數的傳輸重試保留該 Key；`attempt_id` 每次可不同。改 Target／改 Hold Code 是新意圖，必須在舊命令已確認無副作用或已妥善收斂後建立新命令。

不能把 Retry Count 加入 Idempotency Key，否則重試就被外部視為新命令。外部 API 沒有提供冪等／條件式執行能力時，Caller 的 DB 鎖不能保證真正 exactly-once；結果不明應保守停住、查驗並告警。[R2]

### 9.2 執行次序

1. 以 DB 的原子 Claim／Version Guard 取得該 Order 執行權。
2. 讀取新 Snapshot，再次推導 State，避免執行先前排程時的舊決策。
3. 在同一 DB Transaction 保存 Action Intent 與必要 Order 更新；成功後才呼叫外部服務。
4. 呼叫外部 Implementation；不要把跨服務呼叫假裝成與 DB 同一筆原子 Transaction。
5. 另存 Action Receipt；下一輪查驗外部實際效果。
6. 程式在第 4／5 步之間中斷時，重啟先查外部效果，不直接重送。

Lease 到期不表示舊 Worker 的外部 Request 已取消。若有未確定命令，新 Worker 只能先查驗；不能因拿到新 Lease 就再送一筆。外部支援 fencing／version precondition 時使用，否則保留上述限制。

### 9.3 錯誤分類與備援

| 類型 | 策略 |
|---|---|
| Code-specific conflict，且已確認沒設定 | 按 ENHL→OTHL→第三組順序嘗試 |
| 明確未送出／可重試的暫時拒絕 | 有界重試；限制次數、deadline、backoff |
| Timeout／結果不明 | Query command／Hold 狀態，保持 UNKNOWN；未證實失敗不換 Code |
| Permission／非法 Operation／錯誤參數 | 立即停止無意義備援，記錄並告警 |
| Target 已變動 | 重讀 Flow／Current Operation，重新決策 |
| DB 不可用，無法保存 Intent | 不執行無法追蹤的自動修改；獨立健康告警，線上人工防守 |

「所有未成功防守都留 Exception」保留；但記錄時區分單次 Code Attempt Failure、仍在備援中的未確認防守、與整體確定失敗。第一個確定的整體防守失敗立即通知。備援期間也要在 Dashboard 顯示尚未確認，不假裝已防守。

## 10. 資料表／紀錄規格

以下是邏輯資料群，不強制每群獨立 DB，也不要求 Event Sourcing Framework。

| 資料群 | 必要資訊 |
|---|---|
| Order | order_id、OrderKey、Site、Origin/Current Operation、Tool、Flow Version、Target、Policy Version、各 State 面向、Rule ID、Reason、last_snapshot_ref、version、next_check_at、人工控制、結案原因 |
| OrderWafer | Order ID、Wafer ID、Roster Version、Operation Start/Complete、Scan Completed Time、AI Result／Defect Types、Result Version |
| ActionJournal | Command／Attempt ID、Action Type、意圖時間、送出時間、回覆時間、驗證時間、Receipt、Error、Before/After Facts Ref、Actor、規則／程式版本 |
| HoldBinding | Order ID、用途、實際 Code／Memo／MES Hold ID、Target、Future/Active 狀態、created/confirmed/active/release requested/released/verified 時間 |
| Incident + AlarmOutbox | Incident ID、Order、原因、Error 明細、首次／最近發生、次數、狀態、通知目標、send attempts、delivery、ack、resolution；Outbox 可獨立成表 |
| SystemControl | Scope、ENABLED/DISABLED、版本、Trigger、停用時間、Sponsor Approval、恢復時間、健康檢查證據 |

發現事件但尚未建單、Order 建立失敗或 Identity 不明時，Incident 允許暫無 Order ID，但必須保留 Source Event ID、Lot、原始輪次資訊與來源時間；不能因為「還沒有訂單」就沒有 Error Log。

Action History 採追加紀錄。訂單摘要可以更新，但不得覆蓋掉舊動作事實。Error Log 不是目前狀態的唯一来源；判定看當前證據與本次未解決的 Incident。

每次必要資料讀取與決策保留精簡 Snapshot／Hash、來源時間、水位、Rule ID。大量原始資料可引用保存位置，不必反覆塞進 Order。禁止把認證 Secret 寫入 Log。

### 10.1 時間定義

保留：Operation Start、Operation Complete、首片 Scan Completed、整批 AI Completed（本輪有效結果的完成）、Order Created、Hold Requested、Hold Provider Created、Hold Confirmed、Hold Active、Release Requested、Release Provider Completed、Release Verified、Order Closed。

時間保存帶時區的 UTC，顯示可轉 Asia/Taipei；同一命令的耗時另使用注入的單調時鐘。若來源時間不可信，標註品質，不捏造精確時間。

### 10.2 告警可靠性

同一 DB Transaction 寫入 Incident 和待通知 Outbox；Dispatcher 送達後更新結果，失败可重送。此設計借用 Transactional Outbox 解決「資料已寫、通知沒送」的雙寫問題，不代表 DB 與 MES Hold 被納入同一原子交易。[R4]

告警去重 Key 建議為 Order ID + Incident Type + Incident Generation。同一持續 Incident 的重掃更新次數，不每秒建立一個新通知；恢復後再發生可建立新 Generation。通知成功、對方 Ack、異常 Resolved 是三種不同狀態。

## 11. Watchdog、對帳與系統停用

### 11.1 Watchdog 時計

V1 建議將使用者的 30 分鐘規則定義為：本筆 Preventive Hold 在 MES 建立後尚未解除的時間。若 MES Created Time 不可取得，使用可追溯的最早確認時間並標示估計，另以 Request 年齡追蹤未知結果。此起算點須與線上確認，不能混用 Future Hold Created 與 Lot 到站後 Active Time。

另保留三種量測：Operation Start 到 Protection Confirmed 的未防守時間、Hold 建立到解除時間、Lot 實際 Active Hold 阻塞時間。確認 Hold 失敗或正式 Defect Hold 缺少時立即告警，不等 Watchdog 的 30 分鐘。

### 11.2 SMM 對帳

以相同 Scope、輪次與資料截止點取得：

- E：SMM 的應防守事件／本輪 OrderKey 集合。
- P：已確認的有效預防性 Hold 集合。
- C：有證據的正常結案／正式交接完成集合。
- M：明確批准的人工處置集合，另列，不視為自動正常成功。

正在等待防守驗證的項目、真正缺少的項目、資料未知的項目分開顯示。對帳不能只讀 Order Table，否则 Agent 根本漏建 Order 時會一起漏掉。也不能比較累積 SMM 事件數與此刻仍存在的 Hold 數，因為正常 Release 會造成自然差異。

對 OPEN 且仍需防守的輪次，比對有效 P；對已完成輪次檢查 C／M 的證據。Count 只是摘要，必須列缺少／多餘／重複／UNKNOWN 的 Key。A 有兩筆 Hold、B 沒有 Hold，即使總數相同仍為異常。

新事件可標記 WAITING_VERIFICATION 以區別正常查驗時間窗；任何已確認 Hold Failure 立即 Alarm，不能以 grace period 隱藏。資料新鮮度不足時標 UNKNOWN 而非精確聲稱缺一批。

### 11.3 Disable／Resume

`overdue_lot_count > 2` 依使用者字面為 3 批觸發。數量按同一控制範圍的不同實體 Lot 去重，另保留各 Order／Rework 明細，避免一批多組 Hold 重複計數。

停用後：不發出新的預防性 Hold 修改命令；已送出且在途命令繼續查驗；既有 Order、AI、Release、Watchdog、告警與對帳繼續。對需要補防守的 Lot 立即顯示缺口並人工接管；未獲批准不繞過停用開關偷偷新增 Hold。

新 SMM Lot 仍須被觀察與記錄為 BLOCKED_BY_CONTROL／未防守，不能默默放行並從統計消失。關掉 Default Hold 會移除該層自動防守，必須配合線上人工／其他保護 SOP。數量門檻與輪詢延遲不能保證只影響 2 或 3 批。

Resume 必須同時有：SMM Sponsor 授權、異常 Hold 已處理的證據、必要資料源／命令／Release 健康檢查通過、恢復紀錄。不能只因為 Error 數下降或時間到了而自動 Enable。

外部心跳監視點至少能偵測 Agent Process 停止、成功掃描停滯、通知 Dispatcher 停滯；不能完全依附相同故障程序。

## 12. DEV／Mock 規格

### 12.1 環境配置

| 配置 | V1 建議 |
|---|---|
| runtime.mode | DEV 或 PROD；不可預設缺省為 PROD |
| adapter_bundle | DEV=全套 Fake；PROD=經核准的真實連接器 |
| scenario_registry | DEV 必填；以 OrderKey／Visit 配置情境 |
| clock | DEV=ManualClock；PROD=SystemClock |
| network_policy | DEV 禁止外部網路；需要本機服務时僅明確允許測試端點 |
| credentials | DEV 不載入正式憑證 |
| missing_scenario | FAIL_FAST，禁止回退正式環境 |
| hold_codes | ENHL、OTHL、第三組待確認；測試第三組只能是明確 DEV-only Code |
| policy_version | 每筆 Order 固定可追溯版本；新政策變更需重新評估並留紀錄 |

Poll interval、資料新鮮度、確認 deadline、重試次数／backoff 需依實際 MES 回應與製程容許時間確定，V1 不捏造正式數值。DEV 為測試可明確給小值，不能直接當正式安全參數。

第三組正式 Code 尚未確認，若正式上線條件要求三組則啟動檢核不通過；不可拿 TEST_ONLY Code 進 PROD。以兩組先上線須另取得明確的變更批准。

### 12.2 Fake World

Fake World 是有狀態的模擬外部世界，至少含 Mes、AI、Order Repository、Roster、Clock、Notifier。Agent 1 和 Agent 2 必須共用同一世界。

不要讓 Scenario 直接回傳 NEED_HOLD 或 CLOSED。Scenario 指定的是「初始世界、外部動作效果、回覆方式、資料可見延遲、時間事件」；State 必須由正式 evaluator 算出。

| Scenario 維度 | 例子 |
|---|---|
| initial_world | Order 不存在；Lot 在 Op100；Rework 0；預期 W01-W25 |
| on_set_hold.effect | 真的在 Fake World 建立 Hold，或明確拒絕不建立 |
| on_set_hold.response | ACCEPTED、REJECTED、Timeout |
| visibility | 已建立但下一次查詢尚不可見；之後可見 |
| on_release.effect | 移除指定 Hold；其他系統 Hold 必須保持不變 |
| scheduled_events | 模擬時鐘 +5 分鐘 AI 完成、+8 分鐘 Lot 移動 |
| expectations | State、Action、呼叫次數、禁止行為、Log、通知 |

同一 Lot 不同 Rework 可用不同 Scenario；情境不能只根據 Lot 名稱而忘了 Operation／輪次。

單元測試 Mock 要與正式介面規格對齊。Python 可使用 autospec／spec_set 檢查方法與參數，以及 call assertions 驗證有呼叫和不得呼叫的動作；其他語言採等效工具。[R5]

### 12.3 示範情境：Hold 生效但回覆 Timeout

| Tick | 模擬事實／行為 | 預期 State／Action |
|---|---|---|
| 1 | 新 Lot、無 Order | A1 建立 Order |
| 2 | Order 已存在；Flow 可用 | 選擇 Target |
| 3 | 無 Hold、無未定命令 | A1 發出一次 SET_HOLD；Fake 建立 Hold，但回覆 Timeout |
| 4 | 真實 evaluator 看到未定命令 | HOLD_VERIFY_PENDING；查 Fake MES，不重送 |
| 5 | 查到本 Order Hold | PROTECTION_CONFIRMED，記錄證據；Timeout 歷史保留 |
| 6 | 本輪缺一片 AI 結果 | WAIT_AI，不 Release |
| 7 | 模擬時鐘推進；整批完成且無 Defect | A2 REQUEST_RELEASE |
| 8 | Fake MES 確認精確 Hold 已解除 | CLOSED |

本情境應驗證 Hold 修改呼叫一次、未使用 OTHL、至少一次 Hold 查驗、只解除本 Order Hold、保存 Timeout 與成功查驗兩種歷史。

## 13. 測試／驗收矩陣

以下是待執行的測試規格，不代表已在真實 MES 執行。

| Test | 情境 | 預期 | 禁止行為／關聯規則 |
|---|---|---|---|
| T01 | 正常 Hold、25 片全 OK | 建立→查驗→Release→查驗→CLOSED | 未查驗就結案；A1-01/02/03、A2-02/07/11 |
| T02 | ENHL Conflict，OTHL 成功 | 用 OTHL 防守、保存 ENHL 錯誤 | 舊 Error 導致 HOLD_FAILED；A1-04、A2-02 |
| T03 | 三組都明確失敗 | HOLD_FAILED、一次持續 Incident、立即通知 | 靜默等待 30 分鐘；A2-03 |
| T04 | Hold 生效但 Timeout | 查驗成功、不重送 | 換 Code 或重複 Hold；A2-01/02 |
| T05 | Hold Timeout，結果持續未知 | UNKNOWN、查驗與告警 | 單純超時即認定 ABSENT；A2-01/14 |
| T06 | 確認 Hold 成功後 DB 回寫前程式中斷 | 重啟沿已存 Intent 查到既有 Hold | 新建重複 Hold；A2-01/02 |
| T07 | 兩 Worker 同時處理新事件 | 一筆 Order、一個有效邏輯修改 | 只靠先查再新增；I08 |
| T08 | Lease 到期但舊 Request 還在執行 | 新 Worker 先查驗未定命令 | 取得 Lease 就直接重送；I03/I08 |
| T09 | 25 片只有 24 片完成 | WAIT_AI | Release；A2-05 |
| T10 | Log 25 筆但有一片重複、一片缺少 | WAIT_AI、列出缺少 Wafer | 用列數判完成；A2-05 |
| T11 | 空 Roster／Roster 尚未確定 | WAIT_AI／資料異常 | all(empty)=true 被誤用；A2-05 |
| T12 | Completed Time 全有但某片 Result 缺值 | AI_RESULT_INVALID | 當 No Defect；A2-06 |
| T13 | Rework 1 只有 Rework 0 的完成資料 | 等待本輪 AI，建立本輪防守 | 套用舊結果／舊 Hold；I01/I04 |
| T14 | 有 Defect且正式 Future Hold 有效 | 只解除預防性 Hold | 解除正式 Defect Hold；A2-08 |
| T15 | 有 Defect但正式 Hold 未設／錯站／錯輪次 | 保留防守、告警 | 自動 Release；A2-09 |
| T16 | Release 生效但回覆 Timeout | 查驗後 CLOSED | 看到無 Hold 又建立 Hold；A2-10/11 |
| T17 | Release 明確失敗、Hold 仍在 | RELEASE_FAILED、保留防守與告警 | 直接 CLOSED；A2-12 |
| T18 | 他人 ENHL、Memo 不同 | 不視為本 Order Hold | 解除或冒領；I01 |
| T19 | 原有 Hold 未授權消失 | HOLD_MISSING、立即處理 | 推定人工已批准；A2-04 |
| T20 | 合法人工 Release／風險處置 | MANUAL_CLOSED 且附證據 | 標成 AI_OK；A2-13 |
| T21 | 配置站點都已過 | Target 為 Current Station，檢核合法性 | 仍在過去站掛 Future Hold；§6 |
| T22 | 高 Priority 已過、低 Priority 還在前方；或候選正是當前站 | 依有效候選與相等規則選擇 | 全部當已過或比字串；§6 |
| T23 | 無配置站點，Flow 有 Process Tool | 選第一個合法 Process Tool | 捏造站點；§6 |
| T24 | 選完 Target 後 Lot 移動 | 執行前重驗並重選 | 用舊 Position；§6 |
| T25 | Hold Query 錯誤／來源水位落後 | OBSERVATION_UNKNOWN | UNKNOWN 當 ABSENT；A2-14 |
| T26 | 時間為 29:59、30:00、30:01 | 僅 >30 分符合 Watchdog | 把 > 寫成 >=；D-01 |
| T27 | 2 批／3 批超時；同Lot多Hold | 3個不同Lot 才觸發 >2；正確去重 | 將重複Hold當多Lot；D-02 |
| T28 | Disable 後舊 Order AI 變 OK | 既有 Order 可安全 Release；新 Lot 被追蹤但不自動 Hold | 整個 Agent 停住或新Lot無紀錄；A1-08、§11 |
| T29 | 不同 SMM／Hold 集合，但總數相同 | 列出缺少及重複／多餘，告警 | 只看 Count 相等；D-03 |
| T30 | 有本系統 Hold、沒有 Order | ORPHAN_HOLD、人工確認 | 自動解除未知 Hold；D-04 |
| T31 | Order 已 CLOSED 卻仍有 Hold | STATE_CONFLICT | 當正常完成忽略；D-05 |
| T32 | 通知服務故障後恢復 | Incident／Outbox 保留、重送、可觀察送達與Ack | Log 存在即算已通知；D-07 |
| T33 | DEV 沒有 Scenario／嘗試建 Real Adapter | 啟動／呼叫失敗，外部網路請求數=0 | Fallback PROD；I09 |
| T34 | 未經 Sponsor 或健康檢查未通過就 Enable | 拒絕恢復、留審計 | 自動重啟 Default Hold；§11 |
| T35 | Agent／DB／掃描水位停滯 | 外部健康告警、未防守可見 | 依靠故障Agent自己通知；D-06 |
| T36 | Lot Split／Merge／Roster變更 | MANUAL_REVIEW 或核准的正式承接流程 | 靜默用舊Wafer清單；§2/7 |
| T37 | 過期 Event 或 Observation 晚到 | 不覆蓋較新的已確認版本；記錄差異 | 用到達時間任意回退狀態；§3/9 |
| T38 | Permission Error，換 Code也無法改善 | 停止無意義重試、立即通知 | 三Code持續打同錯誤；§9 |

每個 Scenario 都要檢查：State、Rule ID、Action、參數、呼叫次數、禁止呼叫、Order 更新、Action Journal、Incident／Alarm、結果重啟後是否仍可收斂。

安全不變條件測試獨立於程式行覆蓋率。全路徑 Mock 通過不等於 MES 契約正確；正式上線前仍需在核准測試環境做 Adapter Contract／Integration Test。

## 14. 實作順序與最小落地

第一階段先完成 Data Contract、純規則表、Fake World 和 T01–T18 核心案例。第二階段加入併發／重啟、例外通知、Control 與 SMM 對帳。第三階段連接核准測試環境的 Real Adapter、驗證語義與延遲，再做小範圍上線。

Agent 1、Agent 2、Defense 可以先是同一專案內的三個排程入口；不需要一開始就拆微服務。外部心跳監視點須能在該程序停止時仍發出告警。

DB 作為 Order／Intent／Incident 的持久核心。以唯一限制、原子 Claim、動作驗證和 Outbox 達成第一版，不必先引入大型工作流平台。

## 15. 正式整合前待確認契約

| 項目 | 目前處置 |
|---|---|
| 第三組 Hold Code | 待使用者確認；DEV-only 虛擬 Code 不得進 PROD |
| 30 分鐘起算 | V1 提議 MES Hold Created；Active Hold 阻塞另算，需與線上簽定義 |
| MES 冪等／交易查詢／精確 Release | 未證實有能力前不保證 exactly-once，不允許模糊範圍解除 |
| OrderKey 唯一性／Rework Source | 驗證三欄唯一；不足時加 Visit／Start Event ID；輪次不明不填0 |
| Flow 比較／Current Hold 語義 | 確認本輪順序、同站處理、正在加工是否可被Hold阻擋與最晚安全站 |
| 本輪 Expected Wafer 與 AI 完成契約 | 確認權威 Roster、完成時間是否代表結果已提交、Split／Merge規則 |
| 資料新鮮度／重試與期限 | 依 MES 實測及製程容忍時間訂值，非以DEV示例值當正式值 |
| Disable 後人工防守SOP | 明確接手人、處置期限、未防守Lot追蹤、Sponsor復歸要求 |

這些是系統整合契約，不是目前要求使用者逐題補資料才能繼續；核心 State／Action／Mock 可以先依本文實作。

## 16. 設計依據

以下只支持一般軟體設計概念，並不證明使用者內部 MES／SMM 的介面行為。

[R1] Kubernetes 官方 Controllers：觀察實際狀態並反覆調整的控制迴圈；本文不要求部署 Kubernetes。  
`https://kubernetes.io/docs/concepts/architecture/controller/`

[R2] Amazon Builders' Library，Making retries safe with idempotent APIs：回覆遺失後副作用不確定、呼叫者意圖識別與安全重試。  
`https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/`

[R3] PostgreSQL 官方 Constraints：組合唯一限制與 NOT NULL／NULL 行為；實際 DB 非 PostgreSQL 時需用等效機制驗證。  
`https://www.postgresql.org/docs/current/ddl-constraints.html`

[R4] AWS Prescriptive Guidance，Transactional outbox pattern：資料更新與通知的雙寫一致性；不把外部 MES 呼叫變成同一 DB 原子交易。  
`https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html`

[R5] Python 官方 unittest.mock：autospec、spec_set、side_effect 與 call assertions；本文的 Stateful Fake World 仍須自行實作其世界狀態。  
`https://docs.python.org/3/library/unittest.mock.html`
