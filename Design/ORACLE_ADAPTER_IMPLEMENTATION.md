# 給實作 AI：Oracle persistence adapter

把這份整段當任務說明。先讀 HTML 與 DDL，再改程式。不要重寫 Hold 業務。

**先讀：**

- `Design/ORACLE_TABLES_AND_DAO.html`（表名、PARAM key、DBA 範圍）
- `Design/schema/oracle.sql`（只建兩張表）
- `Design/schema/sqlite.sql`（彩排；`hold_order`／`incident` 欄位必須與 Oracle 那兩張對齊）
- `src/vai_hold/application/ports/persistence.py`（UoW 介面）
- `src/vai_hold/adapters/persistence/sqlite/uow.py`（唯一准許的抄本）
- `src/vai_hold/adapters/persistence/oracle/factory.py`（現在只會丟錯）

---

## 可直接貼給另一個 AI 的指示

```
你在 DefaultHold 專案實作 Oracle persistence adapter。

目標：yaml persistence.backend=oracle 時，App 用 Oracle 當 Order DB，業務管線（SET／CONFIRM／CHECK／RELEASE／Defense）一行都不要為了 Oracle 改邏輯。

必讀：
- Design/ORACLE_TABLES_AND_DAO.html
- Design/ORACLE_ADAPTER_IMPLEMENTATION.md（本檔）
- Design/schema/oracle.sql
- src/vai_hold/adapters/persistence/sqlite/uow.py
- src/vai_hold/application/ports/persistence.py

正式 Oracle 只有：
1. 新建 MV_NXT_DEF_HOLD_ORDER_BT  ← SQLite hold_order
2. 新建 MV_NXT_DEF_HOLD_INCIDENT_BT  ← SQLite incident（含 mail_* 寄信欄）
3. 重用既有 MV_NXT_PARAM_BT（不 CREATE）。key 一律 DEFAULT_HOLD_* 。
   欄位名（PARAM_NAME／PARAM_VALUE 等）若 repo 裡沒有現場 DDL，先做可抽換的 key-value 讀寫，欄名用 settings／常數集中一處，不要散落 SQL。

禁止：
- 新建第四張業務表（SQLite 已是 hold_order／incident／agent_control 三張）
- 改 derive／pipelines／usecases 來遷就 Oracle（禁止 if dialect == "oracle"）
- Python ALTER TABLE
- 編造 MES 沒 FETCH 到的欄位
- 把 DSN／密碼寫進 git 或 app.example.yaml
- 為了 Oracle 重跑／改寫情境業務規則（SMMH 不解 Hold、transferHold 不送、settle 分鐘在 config）

做法：
- 實作 adapters/persistence/oracle/（Factory + UoW）讓 load_oracle_factory(settings) 回傳真正的 UnitOfWorkFactory
- 佔位符 :name；時間 TIMESTAMP WITH TIME ZONE；session TIME_ZONE=UTC
- uow.holds 已是 ORDER 的 dh_* 欄（抄 SQLite）
- uow.outbox 已是 INCIDENT 的 mail_* 欄（抄 SQLite）
- uow.wafers／uow.actions／uow.inbound：正式沒有獨立表，塞進 ORDER 大欄或用訂單 UNIQUE 去重；Snapshot 可空實作
- uow.control／心跳：MV_NXT_PARAM_BT，key 見 HTML

驗收：
- python -m pytest tests -q 全綠（Memory + SQLite 不能壞）
- tests/test_persistence_contract.py 在有 DSN 時對 Oracle 跑同一組（沒 DSN 就 skip，但 factory 不再 raise OracleNotImplemented）
- Design/schema 雙 DDL：hold_order↔ORDER、incident↔INCIDENT 欄位仍對齊
```

---

## 範圍

| 做 | 不做 |
|---|---|
| `adapters/persistence/oracle/` 真正的 UoW | 改 `domain/derive.py`、pipelines、usecases |
| `load_oracle_factory` 回傳 Factory | 建第 3 張業務表 |
| settings 增加 Oracle DSN（環境變數或本機 yaml，不進 example 密碼） | 接真實 MES／AI Port（那是另一案） |
| wafers／actions／inbound 映到 ORDER | 把 SQLite 彩排 6 張表砍掉 |

SQLite／Memory 必須繼續綠。日常測試不連 Oracle。

---

## 表對照

| 應用呼叫 | SQLite | 正式 Oracle |
|---|---|---|
| `uow.orders` | `hold_order` | `MV_NXT_DEF_HOLD_ORDER_BT` |
| `uow.holds` | 同一張的 `dh_*` | 同一張的 `dh_*` |
| `uow.incidents` | `incident` | `MV_NXT_DEF_HOLD_INCIDENT_BT` |
| `uow.outbox` | `incident.mail_*` | 同左 |
| `uow.control` | `agent_control` 一列（含 `resume_evidence_ref`／`health_check_ref`） | `MV_NXT_PARAM_BT`（恢復證據與 health check 也必須持久化） |
| `uow.wafers` | `hold_order.wafers_json` | 同欄 |
| `uow.actions` | `hold_order.actions_json` | 同欄 |
| `uow.inbound` | `agent_control.inbound_json` | PARAM JSON 或等價 |
| `uow.snapshots` | no-op | no-op |
| `uow.cursors`（心跳） | `agent_control.last_heartbeat_at` | `DEFAULT_HOLD_LAST_HEARTBEAT_AT`（可選，廠內有 process Alarm 可不寫） |

`action_type` 只有 `SET_HOLD`／`SET_RELEASE`。不要實作 transferHold。

---

## PARAM key（`MV_NXT_PARAM_BT`）

| key | 值 |
|---|---|
| `DEFAULT_HOLD_MODE` | `ENABLED`／`DISABLED_NEW_HOLD`／`RECOVERY_PENDING` |
| `DEFAULT_HOLD_DISABLE_REASON` | 例如 `overdue_lots=3` |
| `DEFAULT_HOLD_DISABLE_TRIGGER` | `WATCHDOG` |
| `DEFAULT_HOLD_DISABLED_AT` | UTC ISO |
| `DEFAULT_HOLD_SPONSOR_ID` | Resume 批准人 |
| `DEFAULT_HOLD_SPONSOR_APPROVED_AT` | UTC ISO |
| `DEFAULT_HOLD_RESUME_EVIDENCE` | 恢復證據 |
| `DEFAULT_HOLD_CONTROL_VERSION` | 整數；save 時對得上才更新、再 +1 |
| `DEFAULT_HOLD_LAST_HEARTBEAT_AT` | UTC ISO，可選 |

重啟必須讀 PARAM 的 MODE，不准用 yaml 預設 ENABLED 蓋掉「已停用」。

現場表欄位未提供時：集中一個小模組（例如 `param_store.py`）假設 `(key, value)`，用註解標「對現場 DDL 時只改這裡」。

---

## 方言

- 佔位符：`:order_id` 不是 `?`
- 時間：`TIMESTAMP(6) WITH TIME ZONE`；連線後 `ALTER SESSION SET TIME_ZONE = 'UTC'`
- CLOB：`payload`／`error_detail`／若 wafers JSON 也是 CLOB
- 布林：`NUMBER(1)` 0/1
- upsert：`MERGE` 或先 update 再 insert
- `try_claim`：與 SQLite 相同語意（`row_version` + `claim_until`）；兩個 UoW 同時 claim 只能一個成功。必要時 `SELECT FOR UPDATE`，但**不可**在呼叫 MES 期間握著 row lock
- 主鍵 UUID 由應用層產生，不要用 SEQUENCE 當契約
- 先 `commit` 意圖再打 MES

---

## 建議檔案

```
src/vai_hold/adapters/persistence/oracle/
  factory.py          # load_oracle_factory 回傳 OracleUowFactory
  uow.py              # OracleUnitOfWork + 各 DAO
  param_store.py      # MV_NXT_PARAM_BT 讀寫（欄名可設定）
```

`composition/bootstrap.py` 已呼叫 `load_oracle_factory`。PROD 仍禁止 FakeWorld；本任務不接真實 MES。

---

## 驗收指令

```
python -m pytest tests -q
python -m pytest tests/test_schema_dual_ddl.py tests/test_persistence_contract.py -q
```

有 Oracle DSN 時（環境變數，例如 `VAI_HOLD_ORACLE_DSN`）：把 `test_persistence_contract.py` 的 factory 參數加上 `oracle`，跑重複建單、row_version 衝突、雙 claim、incident+mail 同交易 rollback、control 重啟仍 `DISABLED_NEW_HOLD`。

沒 DSN：Oracle 測試 skip，但 `backend=oracle` 必須能建構 factory（連不上是連線錯誤，不是 `OracleNotImplemented`）。

---

## 完成定義

- [ ] `load_oracle_factory` 不再 raise `OracleNotImplemented`
- [ ] UoW 實作 `ports/persistence.py` 全部屬性（wafers／actions／inbound 可映到 ORDER，不可新建表）
- [ ] ORDER／INCIDENT 欄位與 `sqlite.sql` 對應表仍能過 `dual_ddl_diffs`（sqlite-only 僅 `agent_control`）
- [ ] PARAM 只用 `DEFAULT_HOLD_*` key
- [ ] Memory + SQLite 全套 pytest 綠
- [ ] 沒有把密碼、wallet 路徑寫進 `Design/config/app.example.yaml`
