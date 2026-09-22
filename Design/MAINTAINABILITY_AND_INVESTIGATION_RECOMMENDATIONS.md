# 可維護性與日後查案能力改善建議

日期：2026-09-20  
範圍：本機程式碼、查案工具、持久化介面、情境產物與相關測試的靜態檢視。  
狀態：建議稿；2026-09-23 已落地部分規則修正與回歸測試，但仍未驗證正式 MES。現行規則見 [DEV_BASELINE.md](DEV_BASELINE.md)。

> 2026-09-23 更新：Result 空值不再正規化成 `OK`；SMM Hold 不參與掃片完成、Release 或結案，且 transfer writer 已移除。下文提到 Result 正規化或 transfer 的內容只保留為原始檢視紀錄。

## 我的判斷

專案已具備值得保留的基礎：Domain／Application／Adapter 分層、DAO 與 UnitOfWork、純判斷函式、可控 Fake World、Rule ID、結構化 Log、查案 CLI、程式定位及 SQLite 情境證據。最新的 [單格驗收契約](ACCEPTANCE_STATE_MACHINE.md) 又把 C01–C11 定義成可獨立檢驗的步驟，這是很好的維護單位。

最大的改善空間，是讓 **「當時讀到什麼 → 為何這樣判斷 → 實際做了什麼 → 最後確認了什麼」形成可核對的證據鏈**。這會同時降低修改規則與處理現場問題的成本。

目前已有部分資料欄位，不能把「模型有欄位」直接等同於「執行時已完整填寫」。建議優先接通現有欄位，避免再建立一套重複追蹤機制。

業務邊界仍參考 [SCENARIO_DISCUSSION.md](SCENARIO_DISCUSSION.md)；本文件著重維護方法。兩份文件的觀察日期不同，實作已有持續變更，不能把前次觀察當成今天所有檔案的現況。

## 建議優先順序

| 項目 | 優先度 | 對日後維護的直接幫助 | 改動規模估計 |
|---|---|---|---|
| M01 判斷前／動作後證據分開 | 高 | 避免拿動作後資料解釋動作前的決策 | 中 |
| M02 完整查案識別與事件契約 | 高 | 能精確追到一輪訂單、一次命令與一次嘗試 | 小至中 |
| M03 查案工具揭露缺漏與限制 | 高 | 不把混單、漏行或截斷報告當成完整結論 | 小至中 |
| M04 執行與情境版本綁定 | 高 | 舊 Log／舊測試可回到當時程式與預期 | 中 |
| M05 規則說明與真實判斷路徑 | 中高 | 改規則時不必同步多套容易漂移的說明 | 中 |
| M06 觀察與資料更新分開 | 中高 | 查詢、Log、重放不會意外寫入業務資料 | 中 |
| M07 收斂動作生命週期與狀態更新 | 中高 | 少改漏一種 retry／verify／結案路徑 | 中至大 |
| M08 查案資料包與離線重放 | 中 | 用保存的證據重現判斷，不依賴現場當下 | 中 |
| M09 Incident 的恢復證據與通知關聯 | 中高 | 看得懂何時出事、何時恢复、通知到哪一步 | 中 |
| M10 測試隔離與真正的查案驗收 | 高 | 測試不污染既有證據，失敗更容易定位 | 小至中 |
| M11 DAO、Schema 與部署資源管理 | 中 | 降低 SQLite／Oracle 與安裝環境的差異 | 中 |
| M12 維護手冊與穩定檢查門檻 | 中 | 新工程師有固定入口，例行修改有清楚完成條件 | 小至中 |

規模是相對估計，不是工時承諾。我的建議是先做 M01–M04、M10，再逐步整理內部結構。

## M01 — 把決策輸入、動作與結果分成不同時間點

**目前觀察**

[check_ai.py](../src/vai_hold/application/pipelines/check_ai.py) 先用 Snapshot 產生 Decision；送出 Release／transfer 後可重新 snapshot，再把新的 Snapshot 與原 Decision 一起交給 `emit_decision`。[log.py](../src/vai_hold/application/log.py) 又把傳入 Snapshot 與 Decision 組成 STATE。

這可以呈現「寫入後 MES 現況」，但沒有明確分開時，很容易讓查案者誤讀為「這些 Facts 就是剛才判斷的輸入」。另外 Snapshot 中包含可變 Order 物件，單純保留同一個物件參照也不一定保得住 before 狀態。

**建議**

保留目前要求的寫入後 EVAL，同時建立不可變的決策證據：

| 記錄 | 必要內容 |
|---|---|
| observation.before | 決策前 Snapshot ID、各來源查詢狀態／時間、Order version |
| decision.evaluated | Decision ID、輸入 Snapshot ID、Rule／Reason、Guard 結果、建議動作 |
| action.dispatched／receipt | Command ID、Attempt ID、參數摘要、傳輸結果 |
| observation.after | 寫入後另一次觀察；明確表示不是原決策輸入 |
| state.persisted／action.verified | 實際落庫狀態與完成查驗的證據 |

名稱是建議，不要求一次替换現有事件。即使當輪沒有 after 觀察，也應標示未取得，不以 before 資料冒充。

**驗收方式**：設定 Hold 前是 0 筆、設定後是 1 筆時，報告能同時展示兩者，且 SET_HOLD 決策只連到 before。重試、Timeout、no-op 也有相同語意。

## M02 — 建立完整的事件關聯與穩定 Log 契約

**目前觀察**

已有 `run_id`、OrderKey、Command ID，模型也有 Attempt、Snapshot 與版本欄位。但 `emit()` 沒有統一加入每筆事件的時間；`record_receipt()` 的 Log 有 attempt_no，未一併輸出 attempt_id、provider_request_id、normalized_error 等已存在於 Attempt 的資料。

`pipeline_run()` 發出 start 並重設 context；end 分散在各 Pipeline。發生例外時，不能只靠找到 start、找不到 end 推定究竟怎麼失敗。

**建議**

- 共用事件欄位：`event_id`、`log_schema_version`、`recorded_at_utc`、`run_id`、`worker_id`、`function_code`、結果與耗時。
- 訂單事件：`order_id`、Lot／Origin Operation／Rework；若適用，含 site／scope。不要用會移動的 current operation 代替訂單識別。
- 動作事件：`decision_id`、`command_id`、`attempt_id`、`attempt_no`、`provider_request_id`、穩定 error category、參數指紋。
- 告警事件：`incident_id`、`episode_id`、`outbox_id`，讓寄信結果能接回原始異常。
- 排程結束由共用外殼保證紀錄 `success / partial_failure / failure`，包含處理、跳過與失敗數；保留例外堆疊與具體訂單 context。
- `source_event_time`、注入的業務 Clock、真正 Log 記錄時間、耗時分開命名；來源沒有提供的值保持未知。

先定義每種事件必填欄位，避免要求沒有 Order 的系統事件也填假 Order ID。紀錄應保留原始錯誤碼與正規化分類，遮罩 credentials；不是把所有原始回應無限制寫入 INFO。

**驗收方式**：只憑一次失敗 Attempt ID，可找回決策、請求參數、回覆、下一次查驗及其 Incident。

## M03 — 查案工具要能說「資料不足」，也能選對案件

**目前觀察**

[investigate.py](../src/vai_hold/investigate.py) 的 `for_lot()` 按 Lot 過濾；`render_case()` 選最後一筆 EVAL／Decision。相同 Lot 的不同 Operation／Rework 或重複執行可能混在一起。`mermaid_sequence()` 只呈現前 80 筆，而焦點卻可能是最後一筆，圖與結論可能不是同一段時間。

`parse_records()` 對不符合格式或 JSON 壞掉的行直接略過，尚未回報有多少疑似事件被漏掉。一般非 JSON 文字可以忽略，但損壞的結構化事件應可見。

**建議**

- 支援 order_id、完整 OrderKey、command_id、run_id、時間範圍；只輸入 Lot 且找到多張 Order 時，先分組列出。
- 支援選「最後狀態」「首次異常」「指定命令」「最後一次狀態變化」，不要讓最後一個 no-op 掩蓋故障起點。
- 報告附解析摘要：有效事件、損壞事件、缺必填欄位、未知 schema 版本、重複 event_id、時間範圍與缺口。
- 大型圖採分頁或故障前後視窗，顯示省略數與完整 JSONL 的位置；不默默截斷。
- 多 Worker 的 timestamp 不代表全域因果順序；以 Command／Attempt／Decision 關聯為主，同時保留原始檔案行號。
- 診斷結論分成「已有證據」「推測」「尚缺資料」，找不到 receipt 不直接宣稱 MES 未執行。

**驗收方式**：混入同 Lot 兩個 Rework、100 筆以上事件、破損 JSON 與缺失 receipt，工具仍能選對案件並明示限制。

## M04 — 保存當時版本，讓舊證據保持可解釋

**目前觀察**

[locator.py](../src/vai_hold/locator.py) 掃描目前原始碼找行號，查舊 Log 時可能指向新版位置。規則同一 ID 的意義也可能演進，例如 T19／A2-04。

[scenario_catalog.py](../src/vai_hold/adapters/persistence/sqlite/scenario_catalog.py) 可以更新 scenario 定義，run 主要保存 scenario_id、時間、passed、actual、diff；沒有把當次完整定義版本綁到結果。`latest_run` 只以秒級 `ran_at` 排序，同秒多筆結果的選擇也不夠明確。

**建議**

- 每次 Run 保存 build ID、程式／套件版本、規則版本、設定指紋、Schema 版本、Adapter 類型。若沒有 Git，也能用發行包 manifest／內容雜湊識別。
- 情境執行保存 scenario revision／hash，並凍結當次 Given、When、Expect、規格版本及 Order DB 證據位置。
- 頁面区分「該次版本通過」「當前版本尚未執行」「當前版本失敗」。新定義搭配舊 Run 時不得直接顯示當前通過。
- 每批測試用 execution_batch_id 串起 catalog、Order DB、Log、HTML；同秒排序用明確序號或確定性 tie-breaker。
- Source locator 以 build 為單位產生並保存；查舊 Log 找不到相符版本時，明示目前顯示的是新版參考位置。

ActionAttempt 已有 `program_version`、`before_snapshot_ref`、`after_snapshot_ref` 等欄位，優先檢查與補齊實際寫入路徑。

**驗收方式**：修改某情境 Expect 但尚未重跑時，頁面顯示過期；修改程式行號後，旧 Run 仍可回到對應版本。

## M05 — 規則登錄與真實判斷軌跡，減少多份說明漂移

**目前觀察**

除了 `derive.py`，還有 [decision_tree.py](../src/vai_hold/decision_tree.py) 的 `DERIVE_LEAVES`／`LEAF_FACT`、查案工具的標題映射、Log 的執行位置映射與 Markdown 說明。`path_spine()` 由人工排列的葉節點推導前面都「不是」，這是說明性重建，不是執行時真的紀錄每個 Guard 的結果。

**建議**

- 建立小型 RuleCatalog：穩定 Rule ID、Reason ID、說明、規則版本、程式 symbol、適用 action、相關 C／T 案例。
- Domain 保持明確純函式，將長判斷依 lifecycle、in-flight、protection、AI、retry、target 拆成具名區段；固定優先序並測試，不急著引入通用規則引擎。
- Decision 可攜帶精簡 `guard_results`：pass／fail／unknown／not_evaluated 及證據參照。未執行的分支不可畫成已檢查失敗。
- 共用目錄產生標題、規則索引與查案連結；測試比對 evaluator 實際可回傳的 Rule／Reason 是否都有登錄。
- 圖上的業務順序、程式呼叫位置與真正 Python exception stack 分開標示；目前「Call stack」較接近業務事件路徑。

**驗收方式**：新增一個 reason 時，缺少對應說明會被檢查抓到；圖能明示哪個 Guard 阻止 Release，不憑規則清單猜測。

## M06 — 讓 snapshot 真正只有觀察，資料轉換有自己的名字

**目前觀察**

[services.py](../src/vai_hold/application/services.py) 同時負責觀察、AI 結果寫入、狀態投影、Incident、Outbox、Receipt、scope 與 heartbeat。`snapshot()` 在讀 AI 時也更新 OrderWafer，並做缺 Alarm Type 等資料處理。

這表示為了 Log 或查驗而多呼叫一次 snapshot，也可能造成持久化副作用；函式名沒有揭露這件事。

**建議**

以職責逐步拆出 `observe_order`、`normalize_ai_evidence`、`persist_ai_evidence`、`project_order`、`incident_service`、`action_journal`。觀察回傳不可變資料；更新由 Pipeline 明確安排。

若業務政策將某種缺值正規化為 OK，應同時保留 `raw_result`、`normalized_result`、`normalization_reason`、policy version。這不是要求改動既有判定，而是讓查案能區分「來源真的回 OK」與「依政策轉成 OK」。

**驗收方式**：只呼叫觀察與報表生成不增加 Order／Wafer version；原始缺值與正規化後結果都能追溯。

## M07 — 共用動作外殼，明確呈現狀態更新與交易邊界

**目前觀察**

Hold／Release／transfer 各自處理 Intent、重試、Binding、Receipt 與查驗；狀態又在 `apply_projection`、`persist_projection`、usecase 內直接賦值等位置更新。這些不同路徑增加日後新增欄位時漏寫 Rule、時間、結案原因的機會。

部分 Pipeline 的 UoW 包住多筆 Order，usecase 內另有 commit。維護者要跨檔案才能看懂「此處失敗，哪些資料已提交」。

**建議**

- 以具型別的 Transition／ActionOutcome 表示舊狀態、新狀態、Reason、close_reason、Binding 變化與必要時間；明確 close_reason 由業務決策帶入，減少各層再猜一次。
- 將 prepare intent、記 attempt、保存 receipt、驗證完成等共通生命週期收斂；Hold／Release／transfer 的 Guard 保持具名且各自測試。
- 每張訂單的交易、claim、外部呼叫與重啟恢復點做成簡短可核對的契約。網路呼叫不能被文件誤稱為 DB 原子交易。
- 不把所有例外硬塞進一個龐大的通用 ActionExecutor；先抽最穩定的 Journal／Transition 部分。
- `params: dict`、動態 `**fields`、穩定 reason／incident type 可逐步改為 dataclass／TypedDict／Enum；有意保留擴充欄位時另設容器。

**驗收方式**：一筆失敗不意外回滾另一筆已完成的 DB 工作；同一命令每個 attempt 的前後狀態一致可查；修改共通欄位有測試涵蓋三類動作。

## M08 — 做成可攜的唯讀查案資料包，支援離線重放

**目前基礎**

已有 Order DB 匯出、Scenario SQLite、Markdown／HTML 證據與 `investigate` CLI。可以把這些組成同一份案件資料包，不必另建大型平台。

**建議資料包**

```text
case-<order-id>/
  manifest.json       # build／policy／schema／時間範圍／檔案 hash／缺漏
  timeline.jsonl      # 關聯完整、經遮罩的事件
  order.json          # 訂單、Binding、Command／Attempt、Incident／Outbox
  snapshots/          # 決策當時的來源證據與品質資訊
  report.md           # 結論、時間序、未知部分與下一步
```

診斷資料讀取使用專門唯讀入口；避免以會建目錄、執行 schema 或初始化資料的 runtime constructor 開啟證據庫。匯出應記錄一致性邊界，不能假稱不同來源是同一原子 Snapshot。

離線 replay 第一階段只重跑純 evaluator，以保存的 Clock、policy、Snapshot 比較原 Decision。明確禁止 MES 寫入；證據不足時顯示無法重放。需要模擬完整流程時，再將最小案件轉為 Fake World 回歸案例。

資料包仍須具備存取限制、保留期限與原始／遮罩版區分；完整 wafer 明細適合放證據檔，以摘要與 ID 連到日常 Log。

**驗收方式**：在無 MES 連線的環境，另一位工程師能復現指定 Decision，並知道哪些資料未被保存。

## M09 — Incident 的「發生、恢復、通知」各自留下證據

**目前觀察**

`maybe_resolve_order_incidents()` 以 AI／SMM 條件搭配排除清單處理多種 Incident；`open_incident()` 預設 episode 為固定字串。通知有 Outbox ID，但 Log 的關聯欄位尚未完全串回訂單與原始 Incident。

**建議**

- 每種 Incident 明訂 open、touch、resolve 條件、責任人及恢復所需證據；集中放入 IncidentPolicy，避免用越來越長的排除清單表達所有規則。
- 同一次持續異常更新 occurrence；已恢復後再次發生建立新 episode，並記錄恢復／重開時間序。
- 加入 `incident.resolved`／`incident.reopened` 等事件，包含 actor、reason、evidence_ref。
- 依目前業務契約明確界定「通知送出就結束」與「異常已恢復」；若無人工 ACK 功能，報告不要顯示成已認領。
- 告警重試耗盡需可查出 terminal reason、最後嘗試與接手方式。MES action 與通知的重試設定分開命名，避免修改其中一項無意影響另一項。

**驗收方式**：同種異常發生、恢復、再發生，能看到兩個 episode；寄信成功不會抹掉原始異常與恢復依據。

## M10 — 測試驗證維護能力，並隔離產物

**目前觀察**

[test_living_doc.py](../tests/test_living_doc.py) 的 golden 測試先生成檔案，再拿生成內容與同一 generator 比對，較能證明生成一致，不能有效抓到事先存在的產物漂移。部分測試還會更新 `Design/generated` 的共享情境庫／文件。

**建議**

- 一般 pytest 使用 tmp_path；發佈證據由明確的產物生成命令執行。測試開始前後共享證據目錄应不變。
- Golden comparison 先讀受維護基準，在暫存位置生成再比較；更新基準是独立且可 review 的操作。
- 保留最新 C01–C11 單格契約，每個 When 驗證 before、after、外部呼叫增量與禁止動作；T 系列保留長流程、恢復與組合證據。
- 加入查案驗收：只給 Log／資料包，能否回答「為什麼沒 Release」「重送幾次」「哪一次 Timeout」「是不是不同 Rework」？不能只 assert 報告包含某個字串。
- 查案測試加入缺行、壞 JSON、多 Worker、同秒事件、舊 schema、未知 Rule／Reason、截斷與版本不符。
- DAO 契約保留 Memory／SQLite 同題測試；真正並行、當機重啟與交易 rollback 另做具體故障注入。

**驗收方式**：測試失败能報出 scenario ID、When、欄位差異與證據路徑；日常測試不改寫人工正在閱讀的情境報告。

## M11 — 持久化與部署：維持替換性，也保護歷史證據

**目前觀察**

SQLite UoW 集中多個 DAO；已有雙 DDL 同步檢查，明定不在 Python 偷做 ALTER。部分 schema／查案文件路徑從 source tree 往上尋找 `Design`；`pyproject.toml` 目前列出的 package data 主要是 `py.typed`。

**建議**

- 隨實際修改把大型 UoW 拆成 Order／Action／Incident 等 DAO 模組，共用連線與交易，業務規則留在 Application／Domain。
- 保留 SQLite／Oracle 欄位與約束對齊檢查；補 round-trip、UTC、NULL、CHECK／FK 與衝突錯誤語意測試。DDL 名称相同不能取代真正 Oracle 契約測試。
- 區分可重建 DEV 情境庫與需要保留的案件／業務庫。舊版本不相容時，先唯讀識別與匯出，不把刪库重建當成所有資料的標準處理。
- 未來正式 schema 升級採版本化、可 review 的獨立 SQL／部署流程，遵守既有不在 runtime Python 自動 ALTER 的方向。
- 釐清 schema 與查案資源要隨 package 發佈，還是由部署路徑明確配置；用安裝 wheel 到乾淨目錄的 smoke test 驗證，不只依賴 editable install。
- `iter_scoped_open_orders()` 現在先取 limit 再套 scope；補分頁及穩定排序契約，避免前面都是範圍外訂單時，後面的合法訂單持續取不到。檢查範圍限制可留在 Application，DAO 提供分頁能力即可。

**驗收方式**：乾淨安裝能找到必要資源；舊案件可唯讀檢視；超過一頁且大部分不在 scope 時，合法訂單仍會被處理。

## M12 — 建立工程師可以直接使用的維護入口

建議由 README 連到一份簡短的 `OPERATIONS_AND_INVESTIGATION.md`，內容包括：

1. 如何用 OrderKey／Incident／Command 定位案件，以及資料來源與時區。
2. 問題分類：資料來源、規則、動作、持久化、排程、通知；每類對應入口檔案。
3. 常見查案問句：沒 Hold、沒 Release、重試耗盡、UNKNOWN、停用、結案殘留，各要哪些證據。
4. 明確區分唯讀查詢、重放判斷、產生模擬證據與真實業務動作；查案命令不應隱含修復。
5. 每個 Rule／Reason 的變更紀錄與適用版本，尤其是語意變更卻沿用 ID 的情況。
6. 資料保留、Log rotation、資料包匯出與清理方式，清理不得讓尚未結案的證據參照失效。

工具檢查建議逐步加入 formatter／lint／type checking；目前 pyproject 的 dev dependency 主要是 pytest。先鎖穩定模組與新增程式，避免一次引入大量無關格式差異。另加分層檢查，防止 Domain import DB／Gateway／Log。

完成標準不是文件數量，而是新工程師可以用一個案件 ID 找到證據，知道結論、未知部分與下一步。

## 建議實作分期與驗收

| 階段 | 範圍 | 可 review 的交付物 | 驗收重點 |
|---|---|---|---|
| 第一階段：證據可信 | M01–M04、M10 的隔離部分 | 事件契約、before／after 證據、完整查案鍵、版本欄位、解析摘要 | 能正確解釋一個 Timeout 案件；新規格不沿用舊通過結果 |
| 第二階段：修改容易 | M05–M07、M09 | 規則目錄、具名 Guard、純觀察、Transition／Journal、Incident policy | 同一規則修改不需手改多套敘述；三類動作狀態一致 |
| 第三階段：交接與長期維護 | M08、M11、M12 | 案件資料包、純判斷重放、安裝／Schema 流程、查案手冊 | 離線可復現；乾淨部署可使用；新工程師可獨立查案 |

第一個值得落地的垂直切片：選一個「Hold Timeout → 查驗 → 下一步」案例，同時做到完整識別、before／after、Command／Attempt 連結、build／policy 版本與唯讀報告。用這個案例建立模式，再套用到 Release、transfer 與 Defense。

## 主要檢視來源

- [單格驗收契約](ACCEPTANCE_STATE_MACHINE.md)、[開發基準](DEV_BASELINE.md)、[Log 對照](LOG_CODE_MAP.md)、[DAO 契約](PERSISTENCE_DAO.md)
- [Log](../src/vai_hold/application/log.py)、[共用服務](../src/vai_hold/application/services.py)、[App 入口](../src/vai_hold/application/engine.py)、[CLI](../src/vai_hold/composition/cli.py)
- [查案工具](../src/vai_hold/investigate.py)、[程式定位](../src/vai_hold/locator.py)、[決策圖](../src/vai_hold/decision_tree.py)
- [資料模型](../src/vai_hold/domain/models.py)、[情境庫 DAO](../src/vai_hold/adapters/persistence/sqlite/scenario_catalog.py)、[雙 DDL 檢查](../src/vai_hold/adapters/persistence/schema_sync.py)
- [查案演練測試](../tests/test_investigation_drills.py)、[living document 測試](../tests/test_living_doc.py)、[情境庫測試](../tests/test_sqlite_scenario_catalog.py)
