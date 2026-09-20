# 入口層：Function Code × Biz Pipeline

日期：2026-09-18  
配合：`DEV_BASELINE.md`  
狀態：開發契約。上層只暴露業務流程；Cron 用參數呼叫不同流程；狀態機存在 DB，不存在行程記憶體。

## 1. 理解確認

要的不是「一支常駐程式在記憶體裡把狀態機跑完」，而是：

1. **程式入口是高層 Pipeline**，步驟名稱是業務語言，不是 `insert_order` / `call_mes`。
2. **用 function code 當參數**，同一個執行檔走不同 Biz 流程。
3. **有些動作是 Atomic**：必須在**同一輪、同一個 function code 裡一次做完**，不能拆成兩個 Cron。
4. **Cron 彼此錯開約一分鐘**，每支 job 只推自己負責的那一步。訂單被寫進新狀態後，下一支 job 下一分鐘自然接著做。

因此：**Cron 順序是加速 happy path 的排程，不是正確性來源。**  
任何一支 job 單獨重跑都必須安全（冪等）。`CHECK_AI_SCAN_COMPLETE` 先跑、`SET_DEFAULT_HOLD_BY_Operation_Start` 後跑，只是前者這輪找不到可解除的單，不會把系統做壞。

```text
Cron ─(function_code, params)─► 單一入口 run()
                                   │
                                   ▼
                            選對 Pipeline
                                   │
                                   ▼
                     撈該流程該處理的訂單／事件（批次）
                                   │
                     每一筆：Pipeline 內的 Atomic 步驟
                                   │
                                   ▼
                              寫回 DB 後結束
```

---

## 2. 唯一入口

```text
vai_hold run --function-code <CODE> [--site FAB1] [--scope DEFAULT] [--limit 50] [--order-id ...]
```

| 參數 | 必填 | 說明 |
|---|---|---|
| `function_code` | 是 | 選哪一條 Biz Pipeline；未知 code **立即失敗**，不准落到預設 PROD 流程 |
| `lot_id` / `ope_no` / `rework_count` | 否 | 除錯時可指定；訂單唯一鍵是這三欄 |
| `scope` | 否 | SystemControl 範圍，預設 `DEFAULT` |
| `limit` | 否 | 本輪最多處理幾筆，防止單次 Cron 拖太久 |
| `order_id` | 否 | 只跑指定訂單（人工重放／除錯） |
| `dry_run` | 否 | 只觀察與決策，不寫 MES、不 commit 變更 |

Composition root 依設定組裝 DAO／Gateway 後，**只**依 `function_code` 分派。禁止在 Pipeline 裡再 `if DEV`。

未知、拼錯的 function code：exit ≠ 0，且不碰 MES。

---

## 3. Function Code（已依業務語意合併／改名）

Lot 主路徑四支；整廠例外與送信合併為 `SMM_EXCEPTION_DEFENSE`（見 §3.1）。

| Function Code | 業務意義 | 本輪會做 | 本輪刻意不做 |
|---|---|---|---|
| `SET_DEFAULT_HOLD_BY_Operation_Start` | 第一片 Operation Start → 建單並送出預防性 Default Hold | 讀進站事件、唯一建單、選站、送 Hold（含備援換 Code）。系統停用時仍建單／留未防守紀錄，**不**送新 Hold | 不把 API 成功當 Hold 已生效；不看 AI |
| `CONFIRM_DEFAULT_HOLD_EXISTS` | 確認本系統 Default Hold 真的在 MES | 查實際 Hold、綁定、失敗立即列隊告警 | 結果未明時不重送、不換 Code |
| `CHECK_AI_SCAN_COMPLETE` | 本輪 AI 是否整批完成；完成且 Guard 通過則**同輪申請解除** Default Hold | 對帳 Wafer 集合與結果；無 Defect 或正式異常 Hold 已接手 → 送精確 Release | 不結案；不碰正式 Defect Hold；AI 未完成則只更新進度 |
| `CONFIRM_DEFAULT_HOLD_RELEASED` | 確認 Default Hold 已解除後才結案 | 權威來源確認本系統 Hold 已消失，且交接條件仍成立 → CLOSED | 曾確認後 Hold 被線上解掉 → `MANUAL_CLOSED`（C08）。不准再去設 Hold |
| `SMM_EXCEPTION_DEFENSE` | 整廠例外監看，並把已列隊告警送出 | Watchdog、覆蓋缺口、停用新 Hold、掃 Outbox 送信 | 不代替主路徑去設／解 Hold |

人工／例外（不進每分鐘 Cron）：

| Function Code | 何時 |
|---|---|
| `VAI_RESUME` | SMM Sponsor 核准恢復「允許新 Default Hold」 |
| `VAI_MANUAL_CLOSE` | 已有授權證據的人工結案 |

舊名對照（程式與 Cron 只用新名）：

| 舊 | 新 |
|---|---|
| `VAI_DISCOVER` + `VAI_PROTECT` | `SET_DEFAULT_HOLD_BY_Operation_Start` |
| `VAI_CONFIRM_HOLD` | `CONFIRM_DEFAULT_HOLD_EXISTS` |
| `VAI_CHECK_AI` + `VAI_RELEASE` | `CHECK_AI_SCAN_COMPLETE` |
| `VAI_CONFIRM_RELEASE` | `CONFIRM_DEFAULT_HOLD_RELEASED` |
| `VAI_DEFENSE` + `VAI_NOTIFY` | `SMM_EXCEPTION_DEFENSE` |

### 3.1 `SMM_EXCEPTION_DEFENSE`（不是單張 Lot 的下一步）

主路徑四支把一張 Lot 從進站推到解除。這支看的是**整廠**：該守的有沒有守到、有沒有超時、要不要停用新 Hold，並且把**已列隊的告警送出去**。

Hold Memo 已告訴現場：超過 30 分鐘沒自動解除，找 **LIT onduty** 人工解除。這支 job 就是把那件事變成系統行為。

| 它在找／做什麼 | 例子 | 之後 |
|---|---|---|
| 超時仍未結束的 Default Hold | Hold 已 > 30 分鐘 | Incident + 通知 LIT onduty |
| 該防守卻沒守到 | SMM 有進站、沒有效 Hold；或設 Hold 失敗 | 列缺口；達門檻則停用新 Default Hold |
| 不該存在的 Hold | 已 CLOSED 還有本系統 Hold | 告警，不自動亂解 |
| 資料說不清楚 | 查詢失敗／過舊 | UNKNOWN，不准當成健康 |
| 送出告警 | 主路徑或本支寫入的 Outbox | 寄信／Teams，記 SENT／FAILED／Ack |

**不做：** 代替主路徑 SET／RELEASE Hold。  
停用後，`SET_DEFAULT_HOLD_BY_Operation_Start` 仍建單、不送新 Hold；本支讓缺口可見並送信。

內部順序（同一 function code，兩段）：

1. **監看／對帳／必要時停用**（Incident 與 Outbox 同交易）
2. **掃全部到期 Outbox 並送出**（含主路徑稍早列隊的 Hold 失敗告警）

送信失敗只更新 Outbox，下一分鐘同一支再試。主路徑不負責寄信，避免 Teams 掛了連 Default Hold 都停。

---

## 4. 每條 Pipeline 的上層長相

入口層只准出現這種粒度。DAO、SQL、MES SDK 不准出現在這一層。

```text
SET_DEFAULT_HOLD_BY_Operation_Start
  1. 從游標讀尚未處理的 Operation Start 事件
  2. 對每一筆事件：
       識別本輪 OrderKey
       身分不足 → Discovery Incident（列隊告警）
       訂單不存在 → 唯一建單（系統停用也要建單，留下未防守）
  3. 對 OPEN 且仍需防守的訂單（含剛建的、上次沒送成的、可換備援 Code 的）：
       鎖定 → 重新觀察
       若允許新 Hold → 選站 + 送出 Default Hold + 記 Receipt
       若系統停用 → 不送 Hold，標未防守／人工接管
  4. 推進游標。查驗留給 CONFIRM_DEFAULT_HOLD_EXISTS

CONFIRM_DEFAULT_HOLD_EXISTS
  1. 找出 HOLD_VERIFY_PENDING，以及已送出但結果未明的命令
  2. 對每一筆：查 MES 實際 Hold → 確認／失敗／仍 UNKNOWN
  3. 未明不得換 Code、不得重送

CHECK_AI_SCAN_COMPLETE
  1. 找出已確認 Default Hold、尚未結案的訂單
  2. 對每一筆：
       核對本輪 Expected Wafer 與 Scan／結果
       未完成 → 只更新缺片，結束（Watchdog 由 DEFENSE 計時）
       結果無效 → 保留 Hold、列隊告警
       有 Defect 且正式異常 Hold 未接手 → 保留 Hold、列隊告警
       已有 SmmHold 但 memo 未涵蓋已知 Defect slot
         → transferHold 累積 Please check #1,#2（同 Code/User，只改 Memo）
       無 Defect，或 Defect 且正式 Hold 已接手且 memo 已齊
         → 同輪重跑 Release Guard → 送出精確解除 Default Hold
  3. 不 CLOSED；不解除正式 Defect Hold
  4. 同一命令含第 1 次最多 3 次；timeout 先查驗再重送

CONFIRM_DEFAULT_HOLD_RELEASED
  1. 找出 RELEASE_VERIFY_PENDING
  2. 對每一筆：確認本系統 Hold 已消失且交接仍成立 → CLOSED
  3. 曾確認後 Hold 沒了 → MANUAL_CLOSED（C08），不是 HOLD_MISSING，也不是再去 SET HOLD

SMM_EXCEPTION_DEFENSE
  1. 比對「應防守」與「實際有效 Default Hold」（含漏建單）
  2. 標出超時（>30 分）、缺口、多餘、UNKNOWN
  3. 達門檻則原子停用新 Hold + 列隊告警（通知 LIT onduty）
  4. 掃到期 Outbox：送出並記錄 SENT／FAILED／Ack
  5. 不呼叫 SET／RELEASE HOLD
```

實作時這些編號應是具名函式；Pipeline 只做編排。禁止在 `run()` 裡攤開 SQL。

`SET_DEFAULT_HOLD_BY_Operation_Start` 與 `CHECK_AI_SCAN_COMPLETE` 內部可以有「先判斷、再視條件做一個 MES 寫入」。仍遵守：同一訂單、同一輪、最多一個會改 MES Hold 的動作。

---

## 5. 哪些是 Atomic（不准拆成兩個 function code／兩次 Cron）

「Atomic」＝同一個訂單（或同一控制動作）、同一輪 Pipeline 呼叫內必須完成的業務步驟。  
不是指 MES 與 DB 變成一筆分散式交易。

| Atomic 單元 | 必須一起做完 | 若拆到下一分鐘會怎樣 |
|---|---|---|
| A. 建單 | 依 OrderKey 唯一插入（或取得已存在列） | 先查再插入會雙單 |
| B. 送出 Default Hold | 鎖定 → **重新觀察** → 重選／重驗站點 → Intent commit → MES → Receipt | 用過期站點；或送了沒紀錄（I13） |
| C. 換備援 Code | 舊命令已確定沒有副作用後，才送新 logical command | Timeout 未明就換 Code，可能雙 Hold |
| D. 查驗 Hold | 查 MES + 寫 Binding／確認／失敗 Incident | 查到沒落庫，下一輪誤重送 |
| E. 檢查 AI | Roster 集合核對 + 寫入每片結果（含缺片） | 用筆數當完成 |
| F. 送出 Release | 重新跑完全部 Release Guard → Intent → MES → Receipt | Guard 過期仍解除；或解到別人 |
| G. 確認結案 | 權威證據 + close_reason + 時間一起寫 | API 成功直接 CLOSED |
| H. 開立告警 | Incident 與 Outbox **同一 DB 交易** | 有異常沒列隊 |
| I. 停用新 Hold | overdue 判定 + control_version + Incident + Outbox | 兩個 job 各停一次 |
| J. 游標推進 | 只推進已持久化接收的事件 | 漏事件或跳號 |

同一訂單、同一輪、最多 **一個** MES Hold 寫入（B 或 C 或 F）。  
`SET_DEFAULT_HOLD_BY_Operation_Start`：同一輪可做 A，再視情況做 B（建單不是 MES 寫入）。  
`CHECK_AI_SCAN_COMPLETE`：同一輪做 E，僅當 Guard 通過才接著做 F。

告警（H）可附在同輪寫出，不佔 MES 寫入名額。真正寄出由 `SMM_EXCEPTION_DEFENSE` 的第二段執行。

### 5.1 不要拆

- Intent 與這次 MES 呼叫（B／F）
- 選站與送 Hold（必須在送出前同一輪重觀察）
- 超時判定與停用（I）
- 查到 Hold 與寫 Binding（D）
- AI 完成判定與（條件成立時的）申請解除 — **已併進** `CHECK_AI_SCAN_COMPLETE`
- Operation Start 建單與（條件成立時的）送 Default Hold — **已併進** `SET_DEFAULT_HOLD_BY_Operation_Start`

### 5.2 仍應分開的 function code

| 拆開 | 原因 |
|---|---|
| 送 Hold vs `CONFIRM_DEFAULT_HOLD_EXISTS` | API 受理／Timeout ≠ Hold 已存在 |
| 申請解除 vs `CONFIRM_DEFAULT_HOLD_RELEASED` | 同一模式：先送出、下一輪證實才結案 |
| 主路徑 vs `SMM_EXCEPTION_DEFENSE` | 對帳／停用／送信看的是整廠與 Outbox，不是「這張單的下一步」 |

系統停用時：`SET_DEFAULT_HOLD_BY_Operation_Start` **仍建單、不送 Hold**；這是同一支 Pipeline 內的分支，不是兩支 Cron。

---

## 6. Cron 怎麼排（建議）

| 分:秒（例） | Function Code | 說明 |
|---|---|---|
| :00 | `SET_DEFAULT_HOLD_BY_Operation_Start` | 進站建單並送 Default Hold |
| :01 | `CONFIRM_DEFAULT_HOLD_EXISTS` | 查上一分鐘送出的 Hold 是否真的在 |
| :02 | `CHECK_AI_SCAN_COMPLETE` | AI 完成且可解除則同輪送 Release |
| :03 | `CONFIRM_DEFAULT_HOLD_RELEASED` | 查解除結果後才 CLOSED |
| :04 | `SMM_EXCEPTION_DEFENSE` | 整廠超時／缺口／停用，並送出告警 |

每支都可每分鐘跑，用起始偏移錯開。單次跑不完靠 `limit` + `next_check_at`。

**正確性不依賴時刻表。** 測試必須能以任意順序呼叫。DEV 用 `ManualClock` 依序 `run(...)`，不真睡 60 秒。

---

## 7. 一批裡的每一筆

1. 每一筆 Order 自己一個 UnitOfWork／claim，失敗不回滾整批。
2. 一筆最多一個 MES Hold 寫入。
3. 搶不到 claim 就跳過。
4. 撈單只是優化，進門仍要 `derive_state`。狀態已變必須 no-op，不准因 function code 名稱強行 Hold／Release。

```text
run(SET_DEFAULT_HOLD_BY_Operation_Start):
    consume operation-start events → ensure_order
    for order in open and still needs protection:
        claim
        snapshot = observe()
        decision = derive + plan
        if decision.business_action != SET_HOLD:
            skip          # 例如已停用、已有 Hold、結果未明
        else:
            atomic_protect(decision)
```

「呼叫了 SET_DEFAULT_HOLD…」≠「這一筆一定會對 MES SET HOLD」。

---

## 8. Happy path 狀態怎麼被 Cron 推著走

新 Lot、無 Defect：

| 時間 | Job | 訂單工作狀態 |
|---|---|---|
| :00 | `SET_DEFAULT_HOLD_BY_Operation_Start` | 建單並送 Hold → `HOLD_VERIFY_PENDING` |
| :01 | `CONFIRM_DEFAULT_HOLD_EXISTS` | → `PROTECTION_CONFIRMED` |
| :02 | `CHECK_AI_SCAN_COMPLETE` | 未掃完 → `WAIT_AI`；掃完無 Defect → 同輪送 Release → `RELEASE_VERIFY_PENDING` |
| :03 | `CONFIRM_DEFAULT_HOLD_RELEASED` | → `CLOSED` |

Timeout：停在 `*_VERIFY_PENDING`，下一分鐘**同一支 CONFIRM** 再查，不重送 Hold。

---

## 9. 與套件切分的關係

```text
composition/cli.py          # 解析 function_code → 選 Pipeline
application/pipelines/      # 高層 Biz 編排
application/usecases/       # Atomic 單元（ensure_order, request_hold, ...）
application/ports/
domain/                     # derive_state, plan_action
adapters/                   # DAO / Fake / Oracle / Real MES
```

---

## 10. 第一階段要先通的 code

`SET_DEFAULT_HOLD_BY_Operation_Start`  
`CONFIRM_DEFAULT_HOLD_EXISTS`  
`CHECK_AI_SCAN_COMPLETE`  
`CONFIRM_DEFAULT_HOLD_RELEASED`

第二階段：`SMM_EXCEPTION_DEFENSE`、`VAI_RESUME`、`VAI_MANUAL_CLOSE`。
