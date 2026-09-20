# 測試情境待討論清單

日期：2026-09-19  
目的：整理閱讀規格、情境頁與相關程式後，值得一起討論的規則邊界及測試缺口。  
狀態：討論稿；以下建議不代表已決議，也沒有因此修改業務程式或重跑測試。

## 閱讀這份文件的方式

我最在意的是：**同一組可觀察資料，是否可能代表兩種不同的現場狀況，卻被程式當成同一種處理？** 其次才是情境頁是否足以證明需求已完成。

依 [DEV_BASELINE.md](DEV_BASELINE.md) 為主要實作基準，並對照 [情境總覽](scenarios.html)、[情境盤點規則](SCENARIO_REVIEW.md)、V1／V3 及相關測試。舊規格與目前情境不同時，這裡會明列差異，不直接認定必須恢復舊規則。

證據分三類：

- **已確認的差異**：能從文件、測試或程式直接指出。
- **待釐清的契約**：本機資料無法證明 MES／現場實際語意。
- **建議補測**：尚不能從目前閱讀的案例證明該邊界；不等於已重現線上錯誤。

## 建議先討論的順序

| 優先序 | 議題 | 為什麼先談 |
|---|---|---|
| 1 | D01：Hold 消失與 LINE_RELEASED | 直接決定是否結案，以及是否繼續追蹤未完成 AI |
| 2 | D02：Timeout 後查無 Hold | 決定可否重送，涉及晚到的第一次請求 |
| 3 | D03：跨 Rework／外人 Hold 的精確識別 | 決定是否可能認錯或解錯 Hold |
| 4 | D04／D05：Defect 接手、Release 重試與結案 | 決定什麼證據足以解除預防性防守 |
| 5 | D06：Wafer slot 與 memo 更新 | 決定現場看到的缺陷片號是否正確、完整 |
| 6 | D07–D11：移站、人工處置、停復用、資料版本、通知 | 補齊例外流程與責任邊界 |
| 7 | D12：測試與報告的可信範圍 | 避免「通過」被理解成比實際更廣的保證 |

## D01 — T19：Hold 消失，何時可以直接視為線上解除？

**目前理解與證據**

目前驗收格是 [C08](generated/evidence/C08.html)（線上代解 → `MANUAL_CLOSED`）。[舊 T19.html](T19.html) 與 [generated/evidence/T19.html](generated/evidence/T19.html) 仍可能寫 `HOLD_MISSING`，**不要當現行契約**。`derive.py` A2-04 與 C08 題庫才是現況。

**我不確定的地方**

「確認查不到原來的 Hold」可以證明它不在，卻不一定能證明是線上人員解除。例如 Memo 被修改、系統識別設定改變、Hold 移到另一站，可能使原比對條件失效。

具體例子：25 片只完成 10 片，Hold 消失。若直接關閉 Order，剩下 15 片後來產生 Defect，誰繼續追蹤？

**需要討論**

- 現場是否明確接受「曾確認存在，後來權威查詢確認消失」就足以結案，不要求解除人或操作紀錄？
- `LINE_RELEASED` 代表防守任務結束，還是連 AI 結果追蹤也結束？
- Memo 改變、站點改變、查詢 UNKNOWN，是否都應與真正消失分開？

**我的建議**

保留目前「不自動補 Hold、不標 AI_OK」的方向；先定義可認定消失的證據及結案後追蹤責任。若現場採無解除人證據也可結案的政策，文件應明載這是處置規則，而非程式已證明誰解除了 Hold。

**建議補測**：AI 未齊時線上解除、AI 已有 Defect 時解除、僅 Memo 改變、查詢 UNKNOWN／STALE、Release 失敗後線上解除。

## D02 — T04／T05／HOLD_TIMEOUT_RETRY3：查不到，是否真的可以重送？

**已確認的差異**

[verify_hold.py](../src/vai_hold/application/usecases/verify_hold.py) 在命令 UNKNOWN、查詢成功且沒有匹配 Hold 時，可轉成 `RETRY_WAIT`。目前 Timeout 重試情境模擬的是「沒有落地」，不是「稍後才落地」。V3 則明確要求考慮延遲提交。

具體例子：第一次 Hold Timeout → 查詢暫時沒有 → 送第二次 → 第一次稍後成功。三次上限能限制次數，但不能排除重複副作用。

**需要討論**

- MES 的成功列表查詢，是否保證排除仍在途／稍後提交的請求？
- 若沒有這項保證，還有哪些證據能允許重送？目前 HoldPort 沒有 request-status API。
- API 已 ACCEPTED，但一直查不到 Hold，何時告警、由誰處理？
- 暫時拒絕的三次重試，要隔多久？只限制次數，仍可能在來源故障期間很快耗盡。

**我的建議**

把「明確拒絕且無副作用」「Timeout 但可證明不會再提交」「仍可能晚到」拆成不同情境。第三種維持查驗與升級處理；等待固定秒數本身不能證明請求已失效。實際重送門檻以 MES 契約決定。

**建議補測**：late commit、建立成功但列表延遲可見、ACCEPTED 長期未可見、同一命令依退避時間重試。

## D03 — T13／T18／T18b：資料庫隔離 Rework，是否足以隔離 MES Hold？

**待釐清的契約**

OrderKey 含 Rework，但 MES 命令沒有 Rework／Hold Record ID；標準 Memo 又相同。基準要求唯一 OPEN Order 對帳，而 [ownership.py](../src/vai_hold/domain/ownership.py) 的單筆匹配函式主要比較當前 Order 的 Binding 與 MES 欄位；該函式本身沒有跨 Order 唯一性檢查。

具體例子：同一 Lot 的 Rework 0 尚有 OP200／ENHL／ABO Hold，Rework 1 也要在 OP200 防守。兩輪可能得到同樣的 MES 識別欄位。

另一個例子：T18 允許自己的 ENHL 與他人的 ENHL 並存，但 Release 傳的是 ReleaseMemo，不是原 HoldMemo。若 MES 以 Lot／Route／站／Code／User 批次解除，僅本機確認「自己的 Memo 恰好一筆」仍不足以證明不影響另一筆。

**需要討論**

- 現場是否允許同 Lot 多個 Rework Order 同時 OPEN？上一輪未完成時，新輪次怎麼處理？
- MES 對相同 Lot／Route／站／Code／User 是否允許多筆不同 Memo？
- Release 究竟刪除哪一筆、還是所有匹配列？ReleaseMemo 是否只是操作註記？

**我的建議**

維持已確認的 T18 規則：不冒領、不解除別人的 Hold，ENHL 明確衝突後可試 OTHL。補清楚 MES 的唯一性與解除範圍；若兩輪无法唯一分辨，先標示歸屬衝突，不讓同一筆實體 Hold 同時證明兩輪已受保護。

**建議補測**：同 Lot 兩輪相同站與碼、兩張 OPEN Order 對到同一實體 Hold、外人相同 Code／User 不同 Memo 並存後執行 Release。

## D04 — T14／T15：正式 Defect Hold 什麼時候算接手成功？

**目前證據**

[is_smm_hold](../src/vai_hold/domain/ownership.py) 檢查 Lot、Code、User、站點；這個函式沒有比對 Route、Rework 或缺陷片涵蓋證據。T14 測試證明正常交接會保留 SMMH，T15 主要驗證沒有正式 Hold 時不解除。

**我不確定的地方**

同一站上的 SMMH／AOA，可能是上一輪、另一 Route，或只涵蓋部分 Defect 的舊 Hold。另一方面，現場也可能把 SMMH 定義為整批防守，因此不要求逐片對應；這需要明確說明。

**需要討論**

- SMMH／AOA／指定站就足夠，還是一定要證明屬於本輪及涵蓋本次 Defect？
- `DefaultHoldStep` 與 `NextProcessStep` 的正式 Hold，如果 Lot 已經跨過該站，還算有效嗎？
- `SMM AI DEFECT HOLD` 這種不含片號的 Memo，是否代表整批接手？

**我的建議**

把「存在」「屬於本次異常」「位置仍可防守」分別定義；MES 若只提供其中一部分，就明載哪些是已確認的業務假設。

**建議補測**：錯 Route、舊 Rework、錯站、已過防守站、只涵蓋部分缺陷片、正式 Hold 查詢 UNKNOWN。

## D05 — T14／T16／REL_RETRY3：重試與最後結案時，Guard 要不要再跑？

**已確認的程式觀察**

[request_release.py](../src/vai_hold/application/usecases/request_release.py) 的首次解除路徑有「匹配恰好一筆」檢查；retry 分支沒有重複同一檢查。[verify_release.py](../src/vai_hold/application/usecases/verify_release.py) 的結案分支以命令與自有 Hold 消失為主，使用 Order 的 AI 狀態決定結案原因，沒有在該分支重新確認 Defect Hold 接手仍有效。這些是局部程式觀察，尚未以新增測試重現完整端到端結果。

具體例子：第一次 Release 被拒後，出現第二筆相同識別 Hold；或送出 Release 後，正式 SMMH 在最後查驗前消失。

另有一個值得核對的組合：Release Timeout，但 Default Hold 已消失、SMMH 還在。列表可能回 `FOUND`；目前 UNKNOWN 命令結案路徑卻要求 `NOT_FOUND`。這與「整張列表為空」和「指定 Default Hold 不在」是否混用有關。

**需要討論**

- 每次重送 Release 是否與第一次一樣，重新驗證 Ownership、唯一性、AI 與交接？
- Default Hold 已解除、但正式 Hold 也消失，Order 應如何記錄與升級？不能再假裝預防性 Hold 還在。
- 查驗的 NOT_FOUND 是整批沒有任何 Hold，還是指定的 Default Hold 沒有？

**我的建議**

把每次 Release 都視為需要最新證據的動作；結案時區分「Default Hold 確實解除」與「品質交接仍成立」。補上 Timeout 加 Defect 交接的組合測試。

## D06 — XFER_ACCUM／XFER_RETRY3：Memo 的 #1 真的是實體 slot 1 嗎？

**已確認的程式觀察**

[smm_memo.py](../src/vai_hold/domain/smm_memo.py) 的 `defect_slots` 用 expected wafer 清單的 1-based 位置產生片號；目前測試 W01、W02 的排列剛好與 slot 相同。

具體例子：名單只有 W03、W17，實體 slot 是 3、17。如果以清單位置輸出，就會是 `#1,#2`。

**需要討論**

- Memo 的數字是 cassette slot、Wafer ID 尾碼，還是名單序號？權威 mapping 從哪裡來？
- AI 同時把 Memo 從 #1 更新成 #1,#3，而 Agent 正在加 #2，如何避免覆蓋 #3？
- 三次 transfer 失敗後，新增 #3 是否可建立新的 logical action？原失敗如何追蹤？
- 全片完成但 memo 更新失敗時，是否仍禁止 Release？非片號格式的正式 Memo 如何處理？

**我的建議**

slot 使用明確來源，不依賴列表排序；更新以最新 Memo 合併並查驗結果。MES 是否提供條件式更新尚待確認，不能只靠本機 union 宣稱已消除並行覆蓋。

**建議補測**：稀疏 slot、名單換序、AI／Agent 並行更新、transfer Timeout 已成功、重試耗盡後新增 Defect。

## D07 — T21–T24：已确认 Hold 不重選，與防守位置失效要怎麼區分？

**已確認決定**

T24 已確認「Hold 已確認就不重選、不重送」，不應重新把這個決定當成未決。`NextProcessStep` 也已明訂從目前站往後、不含目前站。

**需要補清楚的邊界**

- 選點後、尚未送出就移站：應重驗位置。
- 已送出但尚未確認時移站：先查原命令，不直接換站再送。
- 已確認後移站：不重送；但若跨過原防守站或 Route 改變，是否仍算有效防守？
- T23 無配置站時的「第一個 Process Tool」是否包含目前正在加工的站？現有純函式測試包含目前站；它與 NextProcessStep 是不同概念。

**我的建議**

保留「不重送」，另外定義位置失效時是否告警與人工接管。站點順序用 Route occurrence，不用 OP 字串排序。

**測試證據缺口**：目前 catalog T24 沒有實際移站步驟；單測在送出後、確認前改位置，也尚未覆蓋「確認後再移站」這個精確時序。

## D08 — T20／T34：人工結案與恢復，是填名字還是驗證處置完成？

**已確認的程式觀察**

[control.py](../src/vai_hold/application/pipelines/control.py) 的人工結案要求 order_id、actor、approver；該分支沒有查驗 MES 是否解除，也沒有獨立處置證據欄位。Resume 主要要求 sponsor 與 evidence 非空，health_check 缺少時可以 evidence 代入。

**需要討論**

- 人工結案是否允許 Hold 還在，只因已交給現場接管？若允許，後續 Watchdog 由誰接手？
- Sponsor 名字／證據字串是可信上游系統驗證後傳入，還是本程式應驗證？
- Resume 是否必須真的通過健康檢查？`evidence="fixed"` 的 DEV 範例不能自動等同正式契約。

**我的建議**

分清楚「人工接管」「Hold 已解除」「風險已處置」的記錄；如果驗證責任在上游，記錄其可信證據參照。補負例：有名字但無有效核准、健康失敗、Hold 仍在時結案。

## D09 — T26–T28／T34b：停用之後，新進批次與恢復 backlog 怎麼處理？

**已確認決定**

超過 30 分鐘、超時不同 Lot 數 >2 才停用；停用仍可觀察與安全 Release。這兩個數學門檻不需要重新猜。

**需要討論**

- 超時是從 requested_at、first_confirmed_at，還是真正卡貨開始？目前 MES Created 未接，必須標 ESTIMATED。
- 停用期間進站的 Lot，只記錄未防守，還是有現場派工／人工防守承接？
- Resume 後，是只允許新事件，還是把停用期間所有 OPEN Order 都補 Hold？若 Lot 已移站／AI 已完成，怎麼重評估？
- 停用前已寫 Intent、尚未送 MES 的動作，是否會在送出前重查控制版本？

**我的建議**

先把停用期間的負責人與恢復 backlog 規則寫清楚，再補「停用—新批進站—移站—恢復」完整時間序。門檻測試也要涵蓋兩個 Lot 與同 Lot 多 Hold，而不只三個 Lot 的成功觸發。

## D10 — T09–T13／T25／T36／T37：AI 結果版本與資料新鮮度

**目前已有的基礎**

少片、重複片、空名單、結果缺值、Rework 隔離、UNKNOWN 都有對應案例。尚需釐清的是這些資料之間的版本關係。

**需要討論**

- 同一 wafer 同輪先 OK 後 DEFECT，或舊結果晚到，以什麼權威版本決定最新有效結果？
- 有完成時間但來源尚未定稿，是否可以 Release？
- roster 成員相同、順序改變，是單純排序差異還是 slot mapping 改變？
- SourceStatus=FOUND 但 watermark 過舊，哪一層負責轉成 STALE？Hold、AI、Roster 各自容許多久？

**我的建議**

資料集齊與結果定稿分開判斷。補 AI 舊版本晚到、OK 改判 DEFECT、多項 scan 任務只完成一項、來源成功但過舊等情境。T37 目前主要是進站事件晚到，不能直接代表所有 Observation 都有版本保護。

## D11 — T29／T30／T31／T32／T35：對帳、告警與獨立監控

**需要討論**

- T29 要找同數量不同 Key：預期 A/B，實際 A/C。現有 catalog 與同名測試加入 C 後，主要形成數量也不同的缺口，尚未證明「數量相等仍能抓錯」。
- T30／T31 的 Orphan／結案殘留要由誰認領，修正後如何解除 Incident？標記異常不等於流程已完成。
- T32 通知 provider 受理、現場收到、有人 ACK，是不同階段；哪一個是本系統要保證的終點？持續失敗多久要升級？
- T35 是呼叫 Defense 檢查主路徑心跳；若整個程式／主機／DB 都停了，誰在外部發現？

**我的建議**

保留現有 Defense 作為內部對帳，再定義外部監控與告警承接責任。測試分開驗證來源 UNKNOWN、通知失敗重試、持續事件去重、恢復後再發生，以及真正同數量不同 Key。

## D12 — 哪些測試現在「名稱比證據廣」？

以下是目前閱讀到的差距，不是本次測試失敗清單。

| 情境 | 目前證據／限制 | 建議補強 |
|---|---|---|
| T06 | 文件已承認 catalog 重跑與原規格當機時點不同；單測沒有真正重建 process／持久化恢復 | 在 MES 已成功但 Receipt／確認尚未落庫處注入故障，再從 SQLite 重建 App |
| T07 | 兩個 App 依序呼叫，不是同時競爭 | 用同步屏障讓兩 Worker 競爭建單與動作 claim |
| T08 | 測第二 Worker 不重送，但未實際模擬 lease 到期、舊 Worker 恢復及 late commit | 補完整租約與晚到副作用時間序 |
| T19 | 新 Expect／測試與舊 actual／舊文件不同步 | 規則邊界定案後重跑，將結果與情境版本一起保存 |
| T21 | OP400 在預設 Flow 中仍是配置的 CDSEM 目前站，不是所有配置站都在過去 | 加真正位於最後量測站之後的目前站 |
| T22 | catalog OP100→OP200 未呈現高優先站已過；另有純函式單測補部分選點 | 加高優先已過、低優先仍在前方的實際 Flow |
| T24 | catalog 無移站；單測移站時點不同 | 保留已確認規則，補真正確認後移站 |
| T26／T27 | catalog 主要涵蓋 >30 與三批；單測有部分邊界 | 清楚標示哪個入口測邊界，另補同 Lot 多 Hold 去重 |
| T28 | catalog 只看舊單 Release；單測另有新批被阻止 | 整理成可閱讀的完整停用時間序 |
| T29 | 不是嚴格的同數量不同 Key 反例 | 預期 A/B、實際 A/C，總數固定相同 |
| T33 | 有設定／stub 拒絕測試，不等於已證明所有外部網路請求為零 | 另驗缺 Scenario fail-fast 與禁止外部連線的隔離測試 |
| T35 | Defense 看心跳，不代表整個執行環境故障也能告警 | 外部監控契約與故障演練分開驗證 |

另外，T07、T08、T23、T32、T33 未列入目前 HTML catalog，不代表完全沒有單測。相反地，HTML 列出通過也只表示當時選定的 Expect 通過，不代表完整原規格、真實 MES 或並行邊界都已驗證。

部分頁面的劇本寫「設 Default Hold 第 4／5 次」，實際是在呼叫 Pipeline，MES 次數仍應只有三次。建議顯示成「第 N 次呼叫 Pipeline；實際動作／no-op 另列」，避免工程師誤讀。

## 討論紀錄

每次先選一題，以現場例子確認再定案。決議後才同步規格、案例、Expect 與證據；不要只修改測試讓它變綠。

| 議題 | 決議 | 適用前提／例外 | 待補測試／證據 |
|---|---|---|---|
| D01 | 線上解掉 Default Hold 後，未掃完的片由 **AI 自己再 Hold Lot**；本系統只是沒有 Default Hold。可 `LINE_RELEASED`／Manual 結案，不代追剩餘片。 | 查不到＝Hold 沒了（見 D08） | C08 |
| D02 | **現場不會雙 Hold**，Timeout 後查無 Hold 的晚到風險不用考慮。 | | 不改契約 |
| D03 | 撈 Hold／解除必須 **Hold Memo + Hold User + Hold Code** 一致才算同一筆。 | 另用 Binding 的 Lot／Route／Ope | match_our_holds |
| D04 | **Default Hold 站上有 SMM Hold 就算接手**。 | 不另驗錯輪／錯 Route／已過站／部分片 | C10／C11 |
| D05 | **結案必須再確認 SMM Hold 仍在**（Defect 交接）。 | AI_OK 無 SMM Hold 不適用 | verify_release |
| D06 | `#1`＝**Wafer #1**（晶圓編號），不是 roster 第幾片。現場 id `A123456.01`，片號是 `.` 後面的 `01`。 | `A123456.01` → `#1`（`W03` 仍當後備） | smm_memo.wafer_number |
| D07 | Lot 移動後，原 Future Hold **不會失效、不用告警**。 | 已確認就不重選（T24） | 不新增移站告警 |
| D08 | Default Hold **不見** → 當做 **Manual 結案**，寫進訂單表。 | Hold 還在則不走這條 | C08 MANUAL_CLOSED |
| D09 | Resume／進站：先看有無 SMM Hold；**已有就不用 Default Hold**，但 **Order DB 要留紀錄**。 | | SET skip + state_reason |
| D10 | 資料版本／STALE 水位與重查 **不用管**。 | | 不實作 watermark |
| D11 | **告警結案**：比到 Default Hold 站有 SMM Hold，或所有 wafer 已掃完 → `incident` RESOLVED。**寄信成功（outbox SENT）即通知結束**，不等人 ACK。process／主機死了由**你另外的 Alarm 系統**監，本 Agent 不管。 | 不結 STATE_CONFLICT／ORPHAN／AGENT_STALL | maybe_resolve_order_incidents |
| D12 | 現在 catalog／pytest 只做 **offline 邏輯**；實際上線再用程式對 MES 確認。通過 ≠ 真實 MES 已驗證。 | | 總覽加註 |
| T25 | **MES 一定能準確回答有沒有 Hold**，UNKNOWN／問不到 **不用考慮**。 | 程式仍可防呆，但不當驗收 | 不適用 |
| T06 | MES 上 Hold 還在時，下一輪 **CONFIRM 會再對上並確認成功**，不會重送。規格「DB 回寫前中斷」與「重跑不重送」同一結果：以 MES 為準再查一次。 | | T06.html |
| C09 | 掃完有 Defect、現場還沒 SMM Hold：**不解** Default Hold。Order DB 寫 `data_error=NO_SMM_HOLD_AFTER_SCAN`，incident 維持 OPEN，事後能查「該 Hold 卻沒 Hold」。 | 不當成功、不冒充設 SMM Hold | C09.html、`order_db.sqlite` |
| 人工結案 | 現場沒有結案 GUI。**Hold 解掉就當結案**（`MANUAL_CLOSED`／`close_reason=MANUAL`）。 | Hold 還在則不走這條 | C08 |
| 防無限寫 | 狀態沒變就不 UPDATE Order、不重印 `eval.cycle`／`incident.opened`、不累加 incident count。SET 只處理 `NEED_HOLD`／`NEED_TARGET`／`NEED_BACKUP_HOLD`。 | Cron 心跳 `discovery_cursor` 仍每輪一筆（不是每張單） | tests/test_order_db_export.py |
| 多台 | **正式會有多台同時跑**。改單／送 MES 前必須搶到 claim；別人租約還沒到期就不能搶。 | 不是靠 Cron 錯開一分鐘 | try_claim + claim_order |
| 進站來源 | 進站紀錄會留很久；**不做**完整 Inbox／補掃水位。掛機不會久到清單消失。 | | 不擴充 A01 Inbox |
| MES 鑰匙 | MES **同一把鑰匙只執行一次**。本機 `idempotency_key` 要帶去 MES。不能只靠本機說 exactly-once。 | 原則上如此 | FakeWorld.seen_idempotency |
| 重試同一包 | 重試必須送 **Intent 當下凍結的 Memo／站／人／Code**，不可改用新 YAML。 | 認舊 Hold 仍用 Binding 六欄 | payload_json |
| 結案名單 | 結案＝這張單從**日常** SET／CHECK／CONFIRM 名單拿掉（`list_open`）。不是每分鐘掃全歷史。 | | list_open lifecycle=OPEN |
