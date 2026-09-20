# Persistence DAO — Mock / SQLite / Oracle

日期：2026-09-18  
配合：`DEV_BASELINE.md`  
狀態：開發契約。SQLite DDL 是 DEV 可執行的 schema 真實來源；Oracle DDL 與之對齊欄位與約束，供 PROD adapter 使用。

## 1. 目標

本系統的資料庫**不是**領域模型。領域看到的是物件與 Port。

正式環境是 **Oracle**。接 Oracle 之前，**SQLite 就是 Oracle 彩排**：同一套 DAO、同一張表、同一組 UNIQUE／CHECK，只差方言。Memory 只給日常單測圖快，沒有 SQL 約束。現場（MES／AI）仍是 FakeWorld，跟 Order DB 後端無關。

```text
Use case  →  UnitOfWork + *Dao (Protocol)
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
    MemoryDao   SqliteDao   OracleDao
    (Mock)      (DEV)       (PROD)
```

切換只發生在 composition root。domain／usecase 不得出現 `sqlite3`、`oracledb`、連線字串、方言 SQL。

---

## 2. 與外部 Gateway 的界線

| 存的是什麼 | 用什麼 | 誰實作 |
|---|---|---|
| 本系統 Order、Intent、Incident、Control | DAO + UnitOfWork | Memory / SQLite / Oracle |
| MES Hold／Release 的實際效果 | `HoldPort` | Fake MES / Real MES |
| AI 掃片結果 | `AiPort` | Fake AI / Real AI |
| SMM 進站事件 | `SmmPort` | Fake SMM / Real SMM |
| 通知送達 | `NotifierPort` + `AlarmOutboxDao` | Fake Notifier / Real；Outbox 仍在 DAO |

規格要求：Intent 先落庫並 commit，**然後**才呼叫 MES。MES 與 DB **不是**同一筆分散式交易。

---

## 3. 單位工作（Unit of Work）

DAO 方法不各自隱式 commit。由 UoW 劃交易邊界。

```python
class UnitOfWork(Protocol):
    def __enter__(self) -> "UnitOfWork": ...
    def __exit__(self, exc_type, exc, tb) -> None: ...

    orders: HoldOrderDao
    wafers: OrderWaferDao
    holds: HoldBindingDao
    actions: ActionJournalDao
    incidents: IncidentDao
    outbox: AlarmOutboxDao
    control: SystemControlDao
    snapshots: SnapshotDao
    cursors: DiscoveryCursorDao
    inbound: InboundEventDao

    def commit(self) -> None: ...
    def rollback(self) -> None: ...
```

規則：

1. 讀 Snapshot 可以在短交易或自動提交讀取；寫 Intent／Claim／Incident+Outbox 必須在同一交易。
2. `Incident` 與 `AlarmOutbox` 同交易寫入（transactional outbox）。
3. commit 成功後才呼叫 `HoldPort`。網路呼叫期間不准長時間持有 DB row lock。
4. Memory UoW 用 deep-copy snapshot + 成功才替換；rollback 丟棄工作副本。約束失敗丟與 SQL 相同類型的例外（見 §7）。

Factory：

```python
class UnitOfWorkFactory(Protocol):
    def new(self) -> UnitOfWork: ...
```

Composition 注入 `MemoryUowFactory` / `SqliteUowFactory` / `OracleUowFactory`。

---

## 4. DAO API（領域看到的形狀）

以下是 Port，不是 SQL。參數與回傳皆為 domain dataclass。找不到回 `None`；查詢失敗丟 `PersistenceError`（與「資料不存在」分開，對應觀察層的 UNKNOWN）。

### 4.1 HoldOrderDao

```python
class HoldOrderDao(Protocol):
    def get(self, order_id: str) -> HoldOrder | None: ...
    def get_by_key(self, key: OrderKey) -> HoldOrder | None: ...
    def insert(self, order: HoldOrder) -> None: ...
    def update(self, order: HoldOrder, expected_version: int) -> None: ...
    def list_open(self, now: datetime, limit: int) -> list[HoldOrder]: ...
    def list_due(self, now: datetime, limit: int) -> list[HoldOrder]: ...
    def try_claim(self, order_id: str, worker_id: str, until: datetime, expected_version: int) -> bool: ...
    def release_claim(self, order_id: str, worker_id: str) -> None: ...
```

- `insert` 撞到 UNIQUE(site, lot, origin_op, rework) → `DuplicateOrderError`（I08）。
- `update`／`try_claim` 的 `expected_version` 不符 → `ConcurrencyError`；成功則 `row_version += 1`。
- `origin_operation_id` 寫入後不可改。DAO 若偵測到變更應拒絕。
- `rework_count` 不得以 NULL 或「未知當 0」寫入。未知輪次走 Incident／inbound，不建 Order。

### 4.2 OrderWaferDao

```python
class OrderWaferDao(Protocol):
    def replace_roster(self, order_id: str, roster_version: int, wafers: list[OrderWafer]) -> None: ...
    def list_by_order(self, order_id: str) -> list[OrderWafer]: ...
    def upsert_ai_result(self, order_id: str, wafer_id: str, result: WaferAiResult, roster_version: int) -> None: ...
```

Roster 以版本替換，不靜默縮小 expected set。Split／Merge 不自動沿用舊集合（I07）。

### 4.3 HoldBindingDao

```python
class HoldBindingDao(Protocol):
    def add(self, binding: HoldBinding) -> None: ...
    def update(self, binding: HoldBinding) -> None: ...
    def list_by_order(self, order_id: str) -> list[HoldBinding]: ...
    def find_by_mes_tuple(
        self, lot_id: str, route_id: str, ope_no: str, hold_code: str, hold_user: str
    ) -> list[HoldBinding]: ...
    def list_orphans(self) -> list[HoldBinding]: ...  # 有 token 對不到 OPEN order 的查詢由 usecase 組合
```

`role`：`PREVENTIVE` | `DEFECT_REFERENCE`。解除只能針對本 Order 的 PREVENTIVE。

### 4.4 ActionJournalDao

```python
class ActionJournalDao(Protocol):
    def get_command(self, command_id: str) -> ActionCommand | None: ...
    def get_in_flight(self, order_id: str) -> ActionCommand | None: ...
    def insert_prepared(self, command: ActionCommand) -> None: ...
    def save_receipt(self, command_id: str, attempt: ActionAttempt) -> None: ...
    def mark_confirmed(self, command_id: str, evidence_ref: str, at: datetime) -> None: ...
    def list_history(self, order_id: str) -> list[ActionAttempt]: ...
```

- `action_history` **只追加**。訂單摘要可改，歷史列不可 UPDATE／DELETE（測試 reset 除外）。
- 同一 `idempotency_key` 重送不新增邏輯命令。換 Code／換站是新 `logical_action_key`。
- 不可把 retry count 編進 idempotency key。

### 4.5 IncidentDao / AlarmOutboxDao

```python
class IncidentDao(Protocol):
    def open_or_touch(self, incident: Incident) -> Incident: ...
    def get_open(self, subject_key: str, incident_type: str) -> Incident | None: ...
    def ack(self, incident_id: str, actor: str, at: datetime) -> None: ...
    def resolve(self, incident_id: str, actor: str, at: datetime) -> None: ...
    def list_open(self, limit: int) -> list[Incident]: ...

class AlarmOutboxDao(Protocol):
    def enqueue(self, row: OutboxRow) -> None: ...
    def list_pending(self, now: datetime, limit: int) -> list[OutboxRow]: ...
    def mark_sent(self, outbox_id: str, at: datetime, provider_msg_id: str | None) -> None: ...
    def mark_failed(self, outbox_id: str, at: datetime, error: str, next_retry_at: datetime) -> None: ...
    def mark_acked(self, outbox_id: str, at: datetime) -> None: ...
```

尚無 Order 時仍要記異常：`subject_kind=DISCOVERY`，`subject_key=source_event_id`，並保存 lot／operation／來源時間。ACK 與 RESOLVED 分開。

去重鍵：`subject_key + incident_type + episode_id`。

### 4.6 其餘

```python
class SystemControlDao(Protocol):
    def get(self, scope: str) -> SystemControl: ...
    def save(self, control: SystemControl, expected_version: int) -> None: ...
    # 重啟不得用設定檔的 ENABLED 覆蓋已停用列

class SnapshotDao(Protocol):
    def put(self, snap: ObservationSnapshot) -> None: ...
    def get(self, snapshot_id: str) -> ObservationSnapshot | None: ...

class DiscoveryCursorDao(Protocol):
    def get(self, name: str) -> DiscoveryCursor | None: ...
    def advance(self, name: str, last_event_id: str, last_event_time: datetime) -> None: ...

class InboundEventDao(Protocol):
    def try_record(self, event: InboundEvent) -> bool: ...  # False = 已存在，冪等
    def list_unconsumed(self, limit: int) -> list[InboundEvent]: ...
    def mark_consumed(self, source_event_id: str, order_id: str | None) -> None: ...
```

---

## 5. 邏輯資料群 → 表

表名避開 Oracle 保留字（不用 `ORDER`）。

| 表 | 資料群 | 備註 |
|---|---|---|
| `hold_order` | 訂單主檔與狀態投影 | `row_version` 樂觀鎖 |
| `order_wafer` | 本輪 expected roster + AI 結果 | 依 `roster_version` |
| `hold_binding` | 預防性／正式異常 Hold 綁定 | 含 MES id、token、時間品質 |
| `action_command` | 目前邏輯命令 | 一 Order 同時最多一筆 in-flight MES 寫入 |
| `action_history` | 每次 attempt 追加 | 不可改寫 |
| `incident` | 異常 episode | 可無 order_id |
| `alarm_outbox` | 待送通知 | 與 incident 同交易 |
| `system_control` | 啟停與 Sponsor 恢復 | 重啟後仍在 |
| `observation_snapshot` | 決策用證據摘要 | 原始大資料可只存 hash／ref |
| `discovery_cursor` | Agent 1 游標 | 可重播 |
| `inbound_event` | 進站事件去重 | UNIQUE source_event_id |
| `schema_migration` | DDL 版本 | adapter 內部 |

主鍵一律由應用層產生 **UUID 字串**（建議 UUIDv4 或 UUIDv7）。不把 SQLite `AUTOINCREMENT` 或 Oracle `SEQUENCE` 當成跨 adapter 契約。Oracle 若另有內部 sequence，僅限 adapter 私有，不出現在 DAO 簽名。

時間：domain 用 timezone-aware UTC。畫面轉 Asia/Taipei。SQLite 存 ISO-8601 文字（`2026-09-18T15:04:05.123Z`）；Oracle 存 `TIMESTAMP(6) WITH TIME ZONE`。DAO 負責轉換。

---

## 6. 型別對照

| 邏輯型別 | SQLite | Oracle | 說明 |
|---|---|---|---|
| UUID／ID | `TEXT` | `VARCHAR2(36)` | 應用層生成 |
| 短字串 | `TEXT` | `VARCHAR2(n)` | n 見 DDL |
| 長 JSON／證據 | `TEXT` | `CLOB` | 不在 DB 內查 JSON 當契約 |
| 整數／版本 | `INTEGER` | `NUMBER(10)` | `row_version`、`rework_count` |
| 0/1 旗標 | `INTEGER` | `NUMBER(1)` | 不用 BOOLEAN（舊 Oracle 無） |
| 時間 | `TEXT` ISO-8601 UTC | `TIMESTAMP(6) WITH TIME ZONE` | |
| enum | `TEXT` + CHECK | `VARCHAR2` + CHECK | 應用層仍要驗證 |

SQLite 開啟 `PRAGMA foreign_keys = ON`。  
Oracle session：`ALTER SESSION SET TIME_ZONE = 'UTC'`（或連線字串對等設定）。

---

## 7. 必須對齊的語意（三套實作同一測驗）

契約測試（Memory + SQLite 必跑；Oracle 有 DSN 再跑）至少包含：

| 案例 | 期望 |
|---|---|
| 同一 OrderKey 插入兩次 | 第二次 `DuplicateOrderError`，不是先查再插的競態窗口 |
| `update` 帶錯 `row_version` | `ConcurrencyError`，列不變 |
| 兩個 UoW 同時 `try_claim` | 只有一個 True |
| Intent + Incident + Outbox 同交易，commit 前丟例外 | 三張表都沒有該列 |
| `action_history` 寫入後嘗試改內容 | 拒絕或契約測試不提供 update API |
| `rework_count` 缺值 | 無法插入 Order |
| 無 Order 的 discovery incident | 可插入，且 `subject_key` NOT NULL |
| `system_control` 已 DISABLED 後重開 process | 讀到的仍是 DISABLED，不被預設 ENABLED 覆蓋 |
| Memory 與 SQLite 跑同一檔測試 | 行為一致 |

例外階層（domain／application 捕捉這些，不捕捉 `sqlite3.IntegrityError`）：

```text
PersistenceError
  DuplicateOrderError
  ConcurrencyError
  NotFoundError          # 更新對象不存在
  ConstraintError        # 其他 CHECK／FK
```

---

## 8. Memory Mock 規則

- 資料結構用 dict，key 與 UNIQUE 對齊。
- 交易 = 進入 UoW 時 copy-on-write；commit 才替換 store；rollback 丟棄。
- 不模擬 SQL 字串，**要**模擬約束與 version。
- `list_due`／`list_open` 排序穩定（`next_check_at`, `order_id`），避免測試閃爍。
- 測試 reset：`factory.reset()` 清空 store，不提供給 production usecase。

Memory 用來測 usecase 與純規則的快速迴圈。凡涉及「UNIQUE 在 DB 層擋住雙 worker」的案例，必須再在 SQLite 跑一次。

---

## 9. SQL 方言只准留在 adapter

| 差異 | SQLite adapter | Oracle adapter |
|---|---|---|
| 佔位符 | `?` | `:name` |
| upsert | `INSERT ... ON CONFLICT` | `MERGE` 或先 update 再 insert |
| 現在時間（僅 migration／管理） | 不用 DB now；寫入值由 Clock 注入 | 同左 |
| 布林 | 0/1 integer | 0/1 number |
| 大欄位 | TEXT | CLOB 讀寫 streaming |
| 連線 | 檔案或 `:memory:`（契約測試可用檔案或 shared cache） | DSN／wallet；PROD 憑證不得進 DEV |

**禁止**在 usecase 寫 `if dialect == "oracle"`。  
**禁止** DEV 載入正式 Oracle 憑證。  
**禁止** schema 用 `ORDER`、`NUMBER`、`COMMENT`、`SIZE` 當表名。

`:memory:` 在多連線不共享。Agent 1／Agent 2 若分連線，DEV 用檔案型 SQLite（例如 `var/dev.db`）或單一共享連線。契約測試可用一個 UoW factory 對一個檔案。

---

## 10. 切換機制（第一階段就要有，Oracle 實作可空）

只在 composition root 讀設定，Use Case 只拿 `UnitOfWorkFactory`。

```text
persistence.backend = memory | sqlite | oracle
```

```python
def build_uow_factory(settings: Settings) -> UnitOfWorkFactory:
    b = settings.persistence.backend
    if b == "memory":
        return MemoryUowFactory()
    if b == "sqlite":
        return SqliteUowFactory(settings.persistence.sqlite_path)
    if b == "oracle":
        return load_oracle_factory(settings)  # 未實作則啟動失敗
    raise UnknownPersistenceBackend(b)
```

第一階段套件位置：

```text
application/ports/persistence.py     # Protocol：UnitOfWork、*Dao、UnitOfWorkFactory
adapters/persistence/memory/
adapters/persistence/sqlite/
adapters/persistence/oracle/
    __init__.py
    factory.py                       # 必須存在
```

`adapters/persistence/oracle/factory.py` 第一階段只做 **fail-fast stub**，讓你接環境時改這一個檔即可：

```python
class OracleNotImplemented(PersistenceError):
    """接正式環境時在此模組實作 OracleUnitOfWork。"""

def load_oracle_factory(settings) -> UnitOfWorkFactory:
    raise OracleNotImplemented(
        "persistence.backend=oracle 但 Oracle adapter 尚未實作。"
        "請實作 adapters.persistence.oracle 的 UnitOfWorkFactory。"
    )
```

接環境時你要補的：

1. `OracleUnitOfWork` 實作全部 DAO Protocol（簽名不得改）
2. 用 `schema/oracle.sql` 建表
3. 連線／wallet 只放 PROD 設定，DEV 組態不得出現正式憑證
4. 跑與 Memory／SQLite **同一套**契約測試（有測試 DSN 時）

`runtime.mode=PROD` 且 `persistence.backend!=oracle` → 啟動失敗。  
`runtime.mode=DEV` 且 `backend=oracle` 但 stub 未換成實作 → 啟動失敗。  
未知 backend → 啟動失敗，不得默認 SQLite 或 PROD。

---

## 11. 與第一階段的關係

| 項目 | 第一階段 | 接環境時 |
|---|---|---|
| DAO Protocol + Memory + SQLite | 做 | — |
| `persistence.backend` 切換 + Oracle stub | 做 | 換成真正 OracleUnitOfWork |
| `schema/oracle.sql` | 欄位對齊先放著 | 在 Oracle 執行 |
| 正式憑證 | 不准進 DEV | 只給 PROD composition |

未接 Oracle 前，不准在程式裡用 SQLite 特有語法冒充「已支援 Oracle」。

---

## 12. 檔案

| 檔 | 用途 |
|---|---|
| `schema/sqlite.sql` | DEV 可執行 DDL |
| `schema/oracle.sql` | PROD DDL（欄位／約束對齊） |
| 本文件 | DAO Port 與切分規則 |

實作時測試應直接執行 `sqlite.sql` 建庫，不要在 Python 裡再維護一份不同的欄位清單。

---

## 13. SQLite ＝ Oracle 彩排（硬約束）

| 規則 | 為什麼 |
|---|---|
| 加欄位／UNIQUE／CHECK 必須同時改 `schema/sqlite.sql` **與** `schema/oracle.sql` | 接 Oracle 時表不能缺欄 |
| **禁止**在 Python 對 SQLite `ALTER TABLE` 補欄 | Oracle 不會自動長出那一欄；舊 DB 檔請刪掉重建 |
| 工廠只 `executescript(sqlite.sql)`，然後核對欄位；對不上就 `SchemaError` | 不把爛 schema 當成功 |
| pytest：Memory 跑題庫（快）＋ **同一題庫再在 SQLite Order DB 跑一輪** | SQL 約束下回歸，不是只綠 Memory |
| `vai_hold run-scenarios` 預設 `--backend sqlite` | 日常彩排走 SQL |
| `scenario_catalog.sqlite` 是題庫，不是 Order DB | 不要拿題庫檔去當 Oracle 彩排 |
| usecase 禁止 `if dialect == "oracle"`／`ON CONFLICT` | 方言只留 adapter |

測：`tests/test_schema_dual_ddl.py`（雙 DDL 對齊、舊檔拒絕 ALTER）、`test_all_catalog_scenarios_on_sqlite_order_db`（C01–C11 含 C09 `data_error`）。
