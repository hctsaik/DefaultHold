# 驗收單位：狀態機的一格，不是一條做到完

日期：2026-09-19  
狀態：驗收契約。之後情境庫、HTML、測試都依這份切。

## 為什麼 T01 看起來「一次做完」是錯的呈現

現場不是一支程式把進站到結案跑完。

- **狀態在 Order DB**，不在行程記憶體。
- **每一支 Cron／function code 只准推一格。**
- 錯開約一分鐘是排程，不是正確性來源。任一格單獨重跑必須安全。

主路徑格號與測試 ID 相同（C01–C06）：

| 格 | Given | When | Then |
|---|---|---|---|
| **C01** | Lot 進站，還沒本系統 Hold | SET | `HOLD_VERIFY_PENDING` |
| **C02** | C01 已送出 | CONFIRM | `WAIT_AI`／CONFIRMED |
| **C03** | 已設 Default Hold，尚有 Wafer 無 `ScanCompletedTime` | CHECK | 仍 `WAIT_AI` |
| **C04** | 所有 Wafer 已掃完且滿 settle 分鐘（OK／NG 同一條） | CHECK | `RELEASE_SENT`；`close_reason=SCAN_COMPLETED` |
| **C05** | 已送解除，MES 可能 Delay | CONFIRM_RELEASE | `RELEASE_VERIFY_PENDING` |
| **C06** | 自己的 Hold 沒了 | CONFIRM_RELEASE | `CLOSED`／SCAN_COMPLETED |
| **C07** | ENHL 衝突 | SET OTHL | 已送 OTHL |
| **C08** | 線上代解 | CONFIRM | `LINE_RELEASED` |
| **C09** | Defect，掃完已滿 settle 分鐘 | CHECK | 申請解除 Default Hold；`close_reason=SCAN_COMPLETED`；不留 data_error／告警 |
| **C10** | Defect 掃完且滿 settle 分鐘（不查 SMM Hold） | CHECK | `RELEASE_SENT`；`close_reason=SCAN_COMPLETED` |
| **C11** | 自己的 Hold 沒了（不查 SMM Hold） | CONFIRM_RELEASE | `CLOSED`／SCAN_COMPLETED |

原來的 **T01** 只保留當「四格串起來的走完證明」，不當唯一驗收單位。

## 之後每題都要能填這張卡

```
Given  訂單狀態 + MES 上有什麼（可觀察）
When   哪一支 function code（一次一格）
Then   新的 work_state／protection／MES 副作用
Don't  這一格不准做的事
```

規格原文仍放三欄。Given／When／Then 對不上規格 → **停下來問**，不准自己選一種寫進測試。

## 分支也是邊上的一格，不是另一條長劇本

例子：

- T02：Given＝去 SET ENHL，When＝MES 衝突 + 下一輪 SET，Then＝改送 OTHL
- T18：Given＝別人 ENHL（Memo 不同），When＝SET，Then＝仍送自己的 ENHL
- T19：Given＝曾 CONFIRMED，MES 上沒了，When＝CONFIRM／CHECK，Then＝`LINE_RELEASED` 結案

長 script 只是為了把 Given 鋪到那一格；**斷言只打在 When 之後的 Then**。

## 改完了什麼、還沒改什麼

**已改成單格（When＝最後一支 Cron）**

**C01–C11**（圖上編號＝測試 ID）。

**仍是長串、收在總覽 `v1` 摺疊裡當對照**

T01、T02、T14 原編號，以及尚未拆邊的 T03–T13、T16–T18b、T20+、retry／xfer。內部 script 最後一個 `run` 會標成 When（青底），前面的 Cron 標 Given。

**不要猜的拆法（先問再改測試）**

| 題 | 為什麼一拆就換題 |
|---|---|
| T06 | 規格是崩潰點；現測已確認不重送 |
| T19 | When 應只 CONFIRM（已改）；V1 仍寫 HOLD_MISSING |
| T24 | V1 重選 vs 已確認不重選；script 還沒移站 |
| T02／T18b／T03／T38 | FAILED／換碼落在 CONFIRM 還是下一輪 SET |
| T16／T17／Release retry | CHECK 與 RELEASE 綁在同一條 Then |
| Hold retry | 暫時拒要不要先查再送 |
| T13 | 現在沒 CHECK，測不到「不用舊 AI」 |
| T25 | UNKNOWN 時 SET 准不准送 |
| T27 | 「同 Lot 多 Hold」還沒鋪進 Given |
| XFER_* | 現行只作「不得送 transferHold／不得改 SMM Memo」的負向保證 |

## 不做的事

- 不把整廠 Watchdog、人工結案、停用 backlog 塞進 T01 那條直線。
- 不要求 HTML「通過」代表 V1 每一句都已在真實 MES 驗證（見 SCENARIO_DISCUSSION D12）。
