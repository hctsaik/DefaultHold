# Vision AI Preventive Hold Agent — 開發基準

日期：2026-09-18  
狀態：**之後實作只認這份**。V1／V3 規格與架構圖是來源，不是第三套互相競爭的完整規格。  
用途：凍結命名、切第一刀範圍、鎖定 Clean Architecture 與持久化切分。

## 0. 這份文件解決什麼

現有來源：

| 來源 | 角色 |
|---|---|
| `Vision_AI_Hold_Agent_State_Spec_v1.md` | 規則表、動作入口、T01–T38 驗收矩陣 |
| `Vision_AI_Hold_Agent_規格_V3.md` | 觀察契約、狀態面向、待確認 MES 契約 |
| `Design/*.png` | 架構示意；狀態名較舊，不得當程式識別字 |

本文件只做三件事：選邊、對照、切面。細節仍回 V1／V3，不在這裡重寫一遍系統。

---

## 1. 凍結決定

| 主題 | 採用 | 理由 |
|---|---|---|
| 語言 | **Python 3.11+** | 已確認 |
| 顯示／工作狀態、Rule ID、驗收案例 | **V1**（`NEED_HOLD`、`A1-xx`／`A2-xx`／`D-xx`、T01–T38） | 可直接寫測試 |
| 觀察契約 | **V3** `FOUND / NOT_FOUND / UNKNOWN / STALE` | 比 PRESENT／ABSENT 更能表達過期 |
| OrderKey | **`lot_id + ope_no + rework_count`** | 已確認三欄唯一；`ope_no` = 觸發 Operation Start 的站 |
| Hold / Release API | LotId, RouteId, OpeNo, Memo, HoldCode, HoldUser | **沒有** Hold Record ID；見 §1.1 |
| Ownership | MES Hold 列 + 標準 Memo + 本系統訂單狀態 對起來 | 見 §1.2 |
| Hold Code 順序 | YAML 清單，預設 ENHL → OTHL | 不是寫死在程式裡 |
| SmmHold | YAML `smm_hold`：HoldCode=`SMMH`、HoldUser=`AOA`、站點 `DefaultHoldStep` 或 `NextProcessStep` | 不是「Memo 不像我們」 |
| NextProcessStep | **從目前加工站往後、不含目前站**的第一個 Process Tool | 目前 OP100 → 不含 OP100；**不是**從 Default Hold（OP200）再往後找 |
| `SMM_EXCEPTION_DEFENSE` 通知 | YAML 的 Email 名單 | 不是寫死收件人 |
| 持久化 | 第一階段 Memory + SQLite；Oracle 只留 Protocol + 切換點 | 接環境時再寫 Oracle adapter |
| 程式入口 | 主路徑四支 + `SMM_EXCEPTION_DEFENSE` | 見 `ENTRY_PIPELINE.md` |

### Hold Memo（設 Default Hold 時寫入 MES 的原文，亦寫在 YAML）

```text
SMM Default Hold : SMM will auto release this hold, if this hold not auto release > 30 mins , please contact LIT onduty to manual release it.
```

### 1.1 MES Hold / Release 欄位（已確認）

| API | 欄位 |
|---|---|
| Hold | `LotId`, `RouteId`, `OpeNo`, `HoldMemo`, `HoldCode`, `HoldUser` |
| Release | `LotId`, `RouteId`, `OpeNo`, `ReleaseMemo`, `HoldCode`, `HoldUser` |

`HoldUser` 預設 `ABO`（YAML）。  
Hold 的 `OpeNo`／`RouteId` 是**選到的防守站**（可能是未來量測站），不必等於訂單的觸發 `ope_no`。  
Release 必須用**當初設下去的那一組** LotId + RouteId + OpeNo + HoldCode + HoldUser。

查詢：依 LotId 列出該批現有 Hold，再在本機用 §1.2 過濾。Fake MES 必須提供同等 list。

### 1.2 如何確認「這筆 Hold 是哪一張訂單的」

Memo 全文每批相同、User 共用，**單看 Memo 或 User 不夠**。要三邊對上才算本系統的 Default Hold：

```text
MES 上的一筆 Hold
  LotId, RouteId, OpeNo, HoldCode, HoldUser, HoldMemo

本系統 Order
  lot_id + origin ope_no + rework_count
  lifecycle 仍是這輪防守（OPEN，且我們送過對應 Intent／Binding）

本系統 HoldBinding（當初送出時記下的實際參數）
  同一 LotId / RouteId / 防守 OpeNo / HoldCode / HoldUser
```

判定為「我們的」當且僅當：

1. `HoldMemo` **全文等於** YAML 的標準 Default Hold Memo  
2. `HoldUser` 等於 YAML 的 hold user（ABO）  
3. `HoldCode` 是這張訂單 Binding 裡實際送出的那一個（ENHL 或備援後的 OTHL）  
4. `LotId + RouteId + 防守 OpeNo` 與 Binding 一致  
5. 對得到唯一一張 OPEN Order：`lot_id + 觸發 ope_no + rework_count`，且該 Order 的 Binding／Intent 就是這組參數  

**Release 前必須再查一次，且符合條件的 MES Hold 恰好 1 筆。** 0 筆 → 不解除（VERIFY／MISSING）。2 筆以上 → 不解除、告警（避免同一 Lot+站+Code+User 解到別人的 ENHL）。

程式不發明 Hold Record ID。Binding 存的是這六個 API 欄位，不是 MES 內部序號。

### 1.3 HoldPort（Python Protocol，Fake 與 Real 同一簽名）

```python
class HoldCommand:
    lot_id: str
    route_id: str
    ope_no: str          # 防守站，不一定等於訂單觸發站
    memo: str
    hold_code: str
    hold_user: str

class HoldPort(Protocol):
    def set_hold(self, cmd: HoldCommand) -> TransportReceipt: ...
    def release_hold(self, cmd: HoldCommand) -> TransportReceipt: ...  # memo = ReleaseMemo
    def transfer_hold(self, cmd: HoldCommand, new_memo: str) -> TransportReceipt: ...
    def list_holds(self, lot_id: str) -> SourceResult[list[HoldCommand]]: ...
```

`transfer_hold`：同一 LotId/RouteId/OpeNo/HoldCode/HoldUser，只改 Memo。用於 wafer-based SmmHold：`Please check #1` → `Please check #1,#2`。片號從 MES wafer id 解析：`A123456.01` → `#1`（小數點後段）。AI 設第一筆；本 Agent 在已知 Defect slot 超出 memo 時 concile。同一 logical action（同一 idempotency_key）含第 1 次最多送 **3** 次；換 Code／換 memo 是新動作。Timeout 先 `list_holds` 再重送，不准無止盡 retry。

掃完有 Defect、現場還沒 SMM Hold（C09）：**不解** Default Hold。`hold_order.data_error = NO_SMM_HOLD_AFTER_SCAN`，incident 維持 OPEN。現場沒有結案 GUI：**Hold 解掉就當結案**。

狀態沒變的 Cron 不准重寫 Order、不准重印 `eval.cycle`／`incident.opened`。SET 只處理尚未設上的單。

設定（Hold Code 順序、Memo、User、Defense Email）見 `config/app.example.yaml`。程式讀 YAML，不把 ENHL／信箱寫死。

V3 Rule ID（A01、B01、G01）僅作閱讀對照，程式與測試使用 V1 ID。

---

## 2. 名稱對照

### 2.1 圖 → 規格（程式用右欄）

| 圖上舊名 | 程式／DB 使用 |
|---|---|
| HELD | `PROTECTION_CONFIRMED` |
| AI_PROCESSING | `WAIT_AI` |
| AI_COMPLETED | `READY_RELEASE_OK` 或 `READY_RELEASE_HANDOFF`（看 Defect） |
| HOLD_STATE_MISMATCH | `HOLD_MISSING` 或 `STATE_CONFLICT`（依證據） |
| FUTURE_HOLD_FAILED | `DEFECT_HOLD_UNCONFIRMED` |
| HOLD_TIMEOUT | incident `AI_TIMEOUT`／Watchdog `HOLD_OVERDUE`，不是單一主狀態 |
| HOLD_VERIRY_PENDING（圖上拼字） | `HOLD_VERIFY_PENDING` |

### 2.2 V3 Rule → V1 Rule

| V3 | V1 |
|---|---|
| A01 | A1-01 |
| A02 | A1-02 + A1-03 |
| A03 | A2-01 |
| A04 | A1-04 |
| A05 | A1-05 / A2-02 |
| A06 | A2-03 |
| A07 | A1-08 |
| A08 | §9 暫時拒絕重試 |
| B01–B09 | A2-05–A2-13 |
| G01 | A2-14 |
| G06 | A2-04 |

### 2.3 觀察結果

| 值 | 意義 | 禁止解讀 |
|---|---|---|
| `FOUND` | 成功查到目標資料 | — |
| `NOT_FOUND` | 查詢成功、夠新鮮、涵蓋範圍足夠，確認沒有 | 不可用於失敗或過期查詢 |
| `UNKNOWN` | 讀取失敗、逾時、權限、格式錯 | 不可當成沒有 Hold |
| `STALE` | 讀到了但不符合該動作 freshness | 不可當成最新現況 |

Receipt（對外呼叫，不是觀察）：`NOT_SENT` / `ACCEPTED` / `REJECTED` / `UNKNOWN`。  
`ACCEPTED` 只表示對方受理，必須再 `verify_*`。

---

## 3. 必須維持的不變條件

實作與測試直接引用這些 ID。完整敘述以 V1 §1.2／V3 §1 為準。

| ID | 一句話 |
|---|---|
| I01 | 不解除無法證明屬於本 Order 的 Hold |
| I02 | 查詢失敗／過舊 ≠ 沒有 Hold |
| I03 | Timeout ≠ 沒發生；未明前不重送、不換 Code |
| I04 | 未證明本輪整批有效完成，不自動 Release |
| I05 | 有 Defect 且正式異常 Hold 未確認接手，不自動 Release |
| I06 | API 受理 ≠ 實際完成 |
| I07 | 跨 Rework 不共用完成證據／Hold／命令 |
| I08 | 同一 Order 未確定修改命令不並行 |
| I09 | DEV 不連正式外部服務；缺 Mock／Scenario 立即失敗 |
| I10 | 關閉新 Hold ≠ 停止觀察、對帳、符合條件的 Release |
| I11 | 停用期間未防守 Lot 必須可見 |
| I12 | 每個決策可追到 Rule ID、Facts、Policy Version、Action |
| I13 | 持久化 Intent 失敗則不准呼叫會改 MES 的 API |
| I14 | AI 不可讀阻止 Release，不阻止條件已齊的首次預防性 Hold |

---

## 4. Clean Architecture：DB 只是可替換適配器

理解確認：領域與判斷**不知道**自己跑在 Memory、SQLite 還是 Oracle 上。正式環境用 Oracle，DEV／測試用 SQLite 或 Memory。切換點是 **DAO Port**，不是 `if mode == "PROD"` 散落在規則裡。

這與規格原本的 Gateway 切分同一精神，只是把「我們自己的資料」與「MES／AI」分成兩組 Port：

| Port 種類 | 例子 | DEV | PROD |
|---|---|---|---|
| 持久化 DAO | `HoldOrderDao`、`ActionJournalDao`、`UnitOfWork` | Memory 或 SQLite | Oracle |
| 外部 Gateway | `HoldPort`、`AiPort`、`SmmPort`、`NotifierPort` | Fake World | Real Adapter |
| 時鐘 | `Clock` | `ManualClock` | `SystemClock` |

**Fake World ≠ Memory DAO。**  
Fake World 模擬 MES／AI／通知。DAO 保存本系統的 Order／Intent／Incident。Agent 1 與 Agent 2 必須共用同一套 DAO 與同一套 Fake World。

### 4.1 依賴方向

```text
adapters (sqlite/oracle/memory, fake/real MES)
        implements
application ports  (DAO / Gateway / Clock / UnitOfWork)
        used by
application use cases  (request_hold, verify_hold, agent ticks)
        used by
domain  (Order, Facts, derive_state, plan_action, choose_hold_target)
```

domain 與 application **禁止** import `sqlite3`、`oracledb`、SQL 字串、連線字串。  
adapter **禁止**實作業務規則（不在 DAO 裡判斷 NEED_HOLD）。

啟動時只組裝一次（composition root）。`runtime.mode` 缺省或未知 → 啟動失敗，不得預設 PROD。

### 4.2 建議套件切分

```text
src/vai_hold/
  domain/                 # 純資料與純函式
  application/
    ports/                # Protocol：DAO + Gateway + Clock + UoW
    usecases/             # Action 入口與 Agent tick
  adapters/
    persistence/
      memory/             # Mock DAO
      sqlite/             # DEV／整合測試
      oracle/             # PROD
    mes/
    ai/
    notification/
    clock/
  composition/            # 依設定組裝，唯一知道要用哪個 adapter 的地方
```

持久化細節、DDL、方言差異見 `PERSISTENCE_DAO.md` 與 `schema/`。

### 4.3 為何是 DAO 而不是「一個大 Repository 裡寫 SQL」

- 一個 Port 對應一個資料群（Order、Wafer、HoldBinding、Action、Incident、Control）。
- Memory／SQLite／Oracle 三套實作同一介面。
- **契約測試**對 Memory 與 SQLite 必跑；Oracle 在有測試 DSN 時跑同一套。
- Memory 必須實作與 SQL 相同的 UNIQUE／版本衝突語意，避免「Mock 綠、SQLite 紅」。

ORM 不是必須。若日後在 adapter 內使用 SQLAlchemy，也只能停在 adapter，不得滲進 domain。

---

## 5. 核心執行迴圈（程式骨架）

對外入口不是 Agent 常駐迴圈，而是：

```text
run(function_code, params) → 一條高層 Biz Pipeline → 對每筆做 Pipeline 內的 Atomic 步驟 → 結束
```

主路徑 function code：

- `SET_DEFAULT_HOLD_BY_Operation_Start`（建單 + 條件允許則送 Default Hold）
- `CONFIRM_DEFAULT_HOLD_EXISTS`
- `CHECK_AI_SCAN_COMPLETE`（AI 完成且 Guard 通過則同輪申請解除）
- `CONFIRM_DEFAULT_HOLD_RELEASED`
- `SMM_EXCEPTION_DEFENSE`（整廠對帳／超時／停用，並送出已列隊告警）

Cron 錯開約一分鐘。細節與 Atomic 清單見 `ENTRY_PIPELINE.md`。

每一筆 Order 在一個 Atomic 單元內：

1. 取得執行權（UoW + `row_version`／claim）
2. 觀察 Facts（Gateway → `SourceResult`）
3. `derive_state(snapshot, policy, now)`（純函式）
4. `plan_action(assessment, actor, control)`（純函式）
5. 若決策與**本 Pipeline 負責的動作**不符 → no-op（function code 不是強制命令）
6. 同一 DB transaction 寫 Intent／必要 Order 更新；**commit 後**才呼叫 MES
7. 記錄 Receipt；**查驗留給下一個 function code／下一分鐘**

同一 Order 每輪最多一個會改 MES Hold 的動作。告警走 Outbox，可並行。

---

## 6. 第一階段切面（先做這些）

只做能在 DEV 證明迴圈成立的最小垂直切片：

1. Domain 模型 + `SourceResult` + 狀態 enum  
2. DAO Protocol + Memory DAO + SQLite DAO + 契約測試  
3. `derive_state` / `plan_action` / `choose_hold_target`（無 I/O）  
4. Fake World（MES Hold／AI／Clock／Notifier）  
5. `run(function_code)` + 主路徑四支 Pipeline  
6. Action 入口外殼：Intent → Gateway → Receipt；查驗走下一條 CONFIRM code  
7. 驗收：**T01–T18**（V1 §13），用 `ManualClock` + 依序呼叫 function code，不真睡 60 秒

第一階段明確不做：

- Oracle adapter **實作**（只留 Protocol、`oracle.sql`、以及會 fail-fast 的 stub；切換機制要先做好）
- 真實 MES／SMM 連線
- 第三組正式 Hold Code
- Power BI

第二階段（接環境時）：由你實作 `OracleUnitOfWork`；`SMM_EXCEPTION_DEFENSE` 的對帳／Watchdog／送信；T19–T38。  
第三階段：核准測試環境 Real MES Adapter。

---

## 7. DEV 組裝規則

| 設定 | 第一階段 |
|---|---|
| `runtime.mode` | `DEV`（缺省禁止當成 PROD） |
| 語言 | Python 3.11+ |
| `persistence.backend` | `memory`（日常單測）／`sqlite`（**當 Oracle 彩排**：同一 DAO／DDL）／`oracle`（PROD；未實作 → 啟動失敗） |
| mes / ai / notifier | 全套 Fake World |
| clock | `ManualClock` |
| 網路 | 禁止正式端點；缺 Scenario 立即失敗 |
| Hold Code | ENHL、OTHL；第三組僅明確 DEV-only，不得進 PROD 組態 |
| Hold Memo / codes / emails | `config/app.example.yaml` |
| `scope.lot_ids` | 空＝不限制。有名單則只進站／建單／Hold／Defense 這些 Lot；不在名單的事件不消費。不限 wafer |
| 部署 | **多 Worker 並行**；claim 租約有效時他人不可改同一張單 |
| MES 冪等 | 同一 `idempotency_key` 只執行一次；重試送凍結 payload |
| 結案 | 日常只處理 OPEN；結案後不進每分鐘 SET／CHECK／CONFIRM |

Scenario 指定的是 Fake World 的初始事實與副作用，**不得**直接指定 `derive_state` 的輸出。

兩層不要混：

- **現場**仍是 FakeWorld（MOCK MES／AI）。接真 MES 是另一件事。
- **Order DB**：單測 Memory；彩排與可檢查樣本用 SQLite（`hold_order` 等，DDL 與 `oracle.sql` 對齊）。加欄位必須改兩份 SQL，禁止 Python `ALTER`。
- **題庫** `Design/generated/scenario_catalog.sqlite` 不是 Order DB。

題庫：DAO 撈 Given Facts → 判斷／Action → 比對 Expect。種子 `tools/seed_scenario_catalog.py`。`python -m vai_hold run-scenarios` 預設 Order DB＝SQLite。pytest 要求 Memory 與 SQLite **每一列都過**。雙 Worker（T07／T08）與 Oracle stub（T33）仍走原單測。

---

## 8. 仍待確認／沒 FETCH 到（程式禁止假裝已有）

接正式 MES 前，下列欄位**沒有來源**。EVAL／snapshot／DB **不准發明**這些值，也不准把 UNKNOWN 寫成空。

| 項目 | 未確認前（程式現況） |
|---|---|
| ReleaseMemo 原文 | YAML 可改；第一階段用 `SMM auto release Default Hold.` |
| 列出 Lot 現有 Hold 的查詢 API 欄位 | Fake 先依 Hold 同欄位回傳；接 MES 時對契約 |
| Expected Wafer 權威來源 | 名單未定不得 Release |
| YAML 裡 Email 實際名單 | 設定檔提供，程式不寫死 |
| MES Hold Created／Active 時間 | Watchdog 用本機 `requested_at`／`first_confirmed_at`，**標 ESTIMATED**；不得假裝是 MES Created |
| 權威 Expected Wafer Manifest **port** | 僅建單時 inbound payload；不得用 AI Log 反推；EVAL 不印 MES FirstWaferId |
| Timeout 後 request／transaction status | HoldPort **無此 API**；維持 UNKNOWN，先 `list_holds` 查驗；log 不假裝有 RequestStatus |
| Hold Record ID | 契約無此欄；精確解除靠六欄恰好 1 筆；不寫 `mes_hold_record_id` 當已接 MES |
| 正式 Defect Hold 契約 | 以 YAML `smm_hold` 的 SMMH＋AOA＋站點選項認定，不是 Memo 不像我們 |
| MES 單片 Operation Start／Complete | 建單只寫 inbound `event_time` 當本輪 Operation Start；沒 FETCH 到的 wafer 時間保持空 |

收口順序（先修說謊，再接正式 MES；不是再加 log 能假裝）：

1. 寫入 MES 後再 snapshot／再印 EVAL
2. 建單寫入真正的 Operation Start 時間（inbound `event_time`，不用建單牆鐘假裝）
3. Snapshot 保留 AI／Hold 的 QueryStatus；**UNKNOWN 不准當空**
4. Watchdog 時間標「本機估計」，直到 MES 有 Created
5. 之後才談 roster port／request status（正式 MES 契約）

---

## 9. 開發時讀檔順序

1. 本文件  
2. `ENTRY_PIPELINE.md`（入口、function code、Atomic 邊界、Cron）  
3. `LOG_CODE_MAP.md`（log event／rule_id → 檔案）  
4. `config/app.example.yaml`（Hold Code 順序、Memo、Defense Email）  
5. `PERSISTENCE_DAO.md` + `schema/sqlite.sql`  
6. 實作某規則時對 V1 該列；觀察／新鮮度對 V3 §3  
7. 圖只幫助溝通，不以圖上的狀態字串寫 code

## 10. 關鍵決定摘要

1. 實作單一真相是本文件，不是再合併一本 V4 長文。  
2. 判斷純函式化；I/O 只在 adapter。  
3. 持久化切在 DAO：Memory／SQLite／Oracle 可替換；PROD = Oracle。  
4. Fake World 與 DAO 分開。  
5. 第一刀用 SQLite 當 schema 真實來源，Oracle DDL 同步欄位與約束，實作可晚一階段。  
6. 主鍵由應用層發 UUID，不用各資料庫的 identity／sequence 當跨 adapter 契約。  
7. 上層是 function code 驅動的 Biz Pipeline；進站建單與送 Hold 合併；AI 完成與申請解除合併；Defense 與送信合併為 `SMM_EXCEPTION_DEFENSE`。  
8. Python；Oracle 只留 Interface + `persistence.backend` 切換，實作接環境時再寫。  
9. Ownership = 標準 Hold Memo + Hold API 六欄 + 本系統 Order／Binding 狀態對帳；Release 前必須恰好一筆。  
10. Hold Code 順序與 Defense Email 來自 YAML，不是硬編碼。
