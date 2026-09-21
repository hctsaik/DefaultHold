# E2E Evidence 索引

每個情境都是 Fake World 跑出來的真實 log。打開 `.md` 看 Facts／Action；`.log` 是完整原始輸出。

| 情境 | 說明 |
|---|---|
| [`t01_happy.md`](t01_happy.md) | 進站 → Default Hold → AI OK → 解除 |
| [`hold_retry_transient.md`](hold_retry_transient.md) | SET_HOLD 暫時拒絕：同一命令最多 3 次 |
| [`hold_retry_timeout.md`](hold_retry_timeout.md) | SET_HOLD timeout：先查驗再重送，最多 3 次 |
| [`hold_unknown_no_resend.md`](hold_unknown_no_resend.md) | Hold 查詢仍 UNKNOWN：不准重送 |
| [`release_retry_transient.md`](release_retry_transient.md) | SET_RELEASE 暫時拒絕：同一命令最多 3 次 |
| [`release_retry_timeout.md`](release_retry_timeout.md) | SET_RELEASE timeout：先查驗再重送，最多 3 次 |
| [`transfer_memo_accumulate.md`](transfer_memo_accumulate.md) | 未掃完：本 Agent 不改 SMM Memo |
| [`transfer_retry_transient.md`](transfer_retry_transient.md) | 本 Agent 不送 transferHold |
| [`t14_defect_handoff.md`](t14_defect_handoff.md) | Defect + 現場 SMM Hold → 只解 Default Hold |
