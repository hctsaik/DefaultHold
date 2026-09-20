# Vision AI Preventive Hold Agent

Python 實作：Cron 以 function code 推動狀態機。DEV 用 Memory／SQLite + Fake MES；Oracle adapter 只留介面。

## 執行

```text
pip install -e ".[dev]"
vai_hold run --function-code SET_DEFAULT_HOLD_BY_Operation_Start --config Design/config/app.example.yaml
```

Function codes：

- `SET_DEFAULT_HOLD_BY_Operation_Start`
- `CONFIRM_DEFAULT_HOLD_EXISTS`
- `CHECK_AI_SCAN_COMPLETE`
- `CONFIRM_DEFAULT_HOLD_RELEASED`
- `SMM_EXCEPTION_DEFENSE`

切換 Order DB：YAML `persistence.backend` = `memory`（單測）／`sqlite`（**當 Oracle 彩排**）／`oracle`（PROD；未實作會啟動失敗）。加欄位改 `Design/schema/sqlite.sql` 與 `oracle.sql`，不要在 Python ALTER。現場 MES 仍是 MOCK，直到接真系統。

Log 與程式對照：`Design/LOG_CODE_MAP.md`。查案入口：`Design/OPERATIONS_AND_INVESTIGATION.md`。skill：`.grok/skills/vai-hold-investigate/`。

```text
python -m vai_hold investigate --lot LOT1 --log path\to.log
```

## 測試

```text
pytest
```
