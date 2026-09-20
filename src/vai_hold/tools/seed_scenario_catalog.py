from __future__ import annotations

from vai_hold.domain.scenario import ScenarioCase

HAPPY = [
    {"op": "add_lot", "lot_id": "LOT1"},
    {"op": "run", "fn": "set"},
    {"op": "run", "fn": "confirm"},
]

# 查案頁用 V1 §13 的寫法：情境 / 預期 / 禁止。不要自行改寫成「必須做／通過條件」。
SPEC = {
    "T01": {
        "situation": "正常 Hold、25 片全 OK",
        "expected": "建立→查驗→Release→查驗→CLOSED",
        "forbidden": "未查驗就結案",
    },
    "T02": {"situation": "ENHL Conflict，OTHL 成功", "expected": "用 OTHL 防守、保存 ENHL 錯誤", "forbidden": "舊 Error 導致 HOLD_FAILED"},
    "T03": {"situation": "三組都明確失敗", "expected": "HOLD_FAILED、一次持續 Incident、立即通知", "forbidden": "靜默等待 30 分鐘"},
    "T04": {"situation": "Hold 生效但 Timeout", "expected": "查驗成功、不重送", "forbidden": "換 Code 或重複 Hold"},
    "T05": {"situation": "Hold Timeout，結果持續未知", "expected": "UNKNOWN、查驗與告警", "forbidden": "單純超時即認定 ABSENT"},
    "T06": {"situation": "確認 Hold 成功後 DB 回寫前程式中斷", "expected": "重啟沿已存 Intent 查到既有 Hold", "forbidden": "新建重複 Hold"},
    "T09": {"situation": "25 片只有 24 片完成", "expected": "WAIT_AI", "forbidden": "Release"},
    "T10": {"situation": "Log 25 筆但有一片重複、一片缺少", "expected": "WAIT_AI、列出缺少 Wafer", "forbidden": "用列數判完成"},
    "T11": {"situation": "空 Roster／Roster 尚未確定", "expected": "WAIT_AI／資料異常", "forbidden": "誤把空名單當完成"},
    "T12": {"situation": "Completed Time 全有但某片 Result 缺值", "expected": "AI_RESULT_INVALID", "forbidden": "當 No Defect"},
    "T13": {"situation": "Rework 1 只有 Rework 0 的完成資料", "expected": "等待本輪 AI，建立本輪防守", "forbidden": "套用舊結果／舊 Hold"},
    "T14": {"situation": "有 Defect 且正式 Future Hold 有效", "expected": "只解除預防性 Hold", "forbidden": "解除正式 Defect Hold"},
    "T15": {"situation": "有 Defect 但正式 Hold 未設，掃完已滿 2 分鐘", "expected": "解除 Default Hold，SCAN_COMPLETED", "forbidden": "data_error 告警；冒充設 SMM"},
    "T16": {"situation": "Release 生效但回覆 Timeout", "expected": "查驗後 CLOSED", "forbidden": "看到無 Hold 又建立 Hold"},
    "T17": {"situation": "Release 明確失敗、Hold 仍在", "expected": "RELEASE_FAILED、保留防守與告警", "forbidden": "直接 CLOSED"},
    "T18": {
        "situation": "他人 ENHL、Memo 不同",
        "expected": "不視為本 Order Hold",
        "forbidden": "解除或冒領",
    },
    "T19": {
        "situation": "原有 Hold 未授權消失",
        "expected": "曾確認設上後被線上解掉 → 視為解除成功",
        "forbidden": "當成事故補設 Hold；或標 AI_OK",
    },
    "T20": {"situation": "合法人工 Release／風險處置", "expected": "MANUAL_CLOSED 且附證據", "forbidden": "標成 AI_OK"},
    "T21": {"situation": "配置站點都已過", "expected": "Target 為 Current Station", "forbidden": "仍在過去站掛 Future Hold"},
    "T22": {"situation": "高 Priority 已過、低 Priority 還在前方", "expected": "依有效候選選擇（August）", "forbidden": "全部當已過"},
    "T24": {"situation": "選完 Target 後 Lot 移動", "expected": "已保護則不重送", "forbidden": "用舊 Position 再設一筆"},
    "T25": {"situation": "Hold Query 錯誤／來源水位落後", "expected": "OBSERVATION_UNKNOWN", "forbidden": "UNKNOWN 當 ABSENT"},
    "T26": {"situation": "時間為 29:59、30:00、30:01", "expected": "僅 >30 分符合 Watchdog", "forbidden": "把 > 寫成 >="},
    "T27": {"situation": "2 批／3 批超時；同 Lot 多 Hold", "expected": "3 個不同 Lot 才觸發停用", "forbidden": "將重複 Hold 當多 Lot"},
    "T28": {"situation": "Disable 後舊 Order AI 變 OK", "expected": "既有 Order 可安全 Release", "forbidden": "整個 Agent 停住"},
    "T29": {"situation": "不同 SMM／Hold 集合，但總數相同", "expected": "列出缺少及多餘，告警", "forbidden": "只看 Count 相等"},
    "T30": {"situation": "有本系統 Hold、沒有 Order", "expected": "ORPHAN_HOLD、人工確認", "forbidden": "自動解除未知 Hold"},
    "T31": {"situation": "Order 已 CLOSED 卻仍有 Hold", "expected": "STATE_CONFLICT", "forbidden": "當正常完成忽略"},
    "T34": {"situation": "未經 Sponsor 就 Enable", "expected": "拒絕恢復、留審計", "forbidden": "自動重啟 Default Hold"},
    "T34b": {"situation": "有 Sponsor 與健康證據", "expected": "恢復 ENABLED", "forbidden": "沒證據就恢復"},
    "T35": {"situation": "Agent／心跳停滯", "expected": "外部健康告警 AGENT_STALL", "forbidden": "依靠故障 Agent 自己通知"},
    "T36": {"situation": "Lot Split／Merge／Roster 變更", "expected": "MANUAL_REVIEW", "forbidden": "靜默用舊 Wafer 清單"},
    "T37": {"situation": "過期 Event 或 Observation 晚到", "expected": "不覆蓋較新的已確認版本", "forbidden": "用到達時間任意回退狀態"},
    "T38": {"situation": "Permission 拒絕 Hold", "expected": "立即 HOLD_FAILED", "forbidden": "耗完備援 Code 才發現共通問題"},
    "AI_UNKNOWN": {"situation": "AI 查詢 UNKNOWN", "expected": "WAIT_AI，不當空、不當掃完", "forbidden": "UNKNOWN 當 0 片而 Release"},
    "HOLD_RETRY3": {"situation": "同一 SET_HOLD 暫時拒絕", "expected": "同一命令最多 3 次後 HOLD_FAILED", "forbidden": "無止盡 retry"},
    "HOLD_TIMEOUT_RETRY3": {"situation": "Timeout 且查驗沒落地", "expected": "先查再重送，最多 3 次", "forbidden": "UNKNOWN 就重送或換 Code"},
    "HOLD_UNKNOWN_NO_RESEND": {"situation": "Timeout 後 Hold 查詢仍 UNKNOWN", "expected": "保持查驗、不重送", "forbidden": "UNKNOWN 當 ABSENT 再送一次"},
    "REL_RETRY3": {"situation": "同一 Release 暫時拒絕", "expected": "同一命令最多 3 次、Hold 仍在", "forbidden": "直接 CLOSED"},
    "REL_TIMEOUT_RETRY3": {"situation": "Release Timeout 且 Hold 還在", "expected": "先查再重送，最多 3 次", "forbidden": "暫時看不到 Hold 就當已解除"},
    "XFER_ACCUM": {"situation": "第一片 Defect 已有 Lot Hold #1，第二片再 Defect", "expected": "transferHold 把 Memo 改成 Please check #1,#2；Default Hold 不解", "forbidden": "再 SET 一筆 SmmHold 或解 Default Hold"},
    "XFER_RETRY3": {"situation": "transferHold 暫時拒絕", "expected": "同一命令最多 3 次，Memo 仍 #1", "forbidden": "無止盡 retry 或當成已改 Memo"},
}

# 工程師對題：現場／這輪要做／做完應看到／禁止。規格只有三句、這裡有兩種解 → 標 open，停下來問，不准自己選。
ENG = {
    "T01": {
        "given": "Lot 進站，MES 上還沒有本系統 Default Hold。",
        "do": "這題只是把 C01～C06 串起來的走完證明。真正驗收看 C01–C06。",
        "then": "訂單 CLOSED（AI_OK）；MES 上本系統 Hold 已沒有。",
        "dont": "AI 還沒查完就結案；也不要把四支 Cron 當成同一輪。",
    },
    "C01": {
        "given": "Lot 進站，還沒訂單、MES 上也還沒有本系統 Default Hold。",
        "do": "建立訂單，並向 MES 設 Default Hold（Hold Code ENHL）。",
        "then": "Default Hold 已送出，但還沒去 MES 確認它真的在；還不算已生效。",
        "dont": "不查 AI、不解除 Hold；也不要把「MES 回成功」當成 Hold 已經在現場。",
    },
    "C02": {
        "given": "Default Hold（ENHL）已送出，還沒確認 MES 上真的有。",
        "do": "向 MES 查本系統 Default Hold（對標準 Memo／User／Code）。有就當成已設上。",
        "then": "確認 Default Hold 存在；開始等所有 wafer 掃完。",
        "dont": "還沒查清楚就再設一次，或換另一個 Hold Code。",
    },
    "C03": {
        "given": "Default Hold 已確認存在，但不是所有 wafer 都掃完。",
        "do": "看 AI 掃片進度。還沒掃完就繼續等。",
        "then": "Default Hold 仍在；不解除。",
        "dont": "還沒掃完就申請解除 Default Hold。",
    },
    "C04": {
        "given": "Default Hold 已確認存在；所有 wafer 掃完且都 OK。",
        "do": "向 MES 申請解除 Default Hold。",
        "then": "解除已送出；MES 可能還沒寫完；這張單還沒結案。",
        "dont": "這一輪就把單結案。",
    },
    "C05": {
        "given": "已申請解除 Default Hold，MES 上可能還沒跟上，Hold 還看得到。",
        "do": "再向 MES 查自己的 Default Hold 還在不在。還在就當延遲，等下一輪。",
        "then": "不重送解除、不當失敗、不結案。",
        "dont": "看到 Delay 又送一次解除，或當成已經解除。",
    },
    "C06": {
        "given": "已申請解除，MES 上自己的 Default Hold 已經沒有。",
        "do": "確認 Default Hold 已解除，這張單結案。",
        "then": "單結案（全數 OK）。",
        "dont": "Hold 還在就結案。",
    },
    "T02": {
        "given": "去設 ENHL，MES 明確回 Code 衝突，Hold 沒設上。",
        "do": "【串接】對照用。驗收看 T02-OTHL 那一格。",
        "then": "用 OTHL 防守成功；留下 ENHL 衝突紀錄。",
        "dont": "因為 ENHL 失敗就整單 HOLD_FAILED。",
    },
    "C07": {
        "given": "第一個 Hold Code（ENHL）被 MES 明確拒絕（Code 衝突），Default Hold 還沒設上。",
        "do": "同一輪立刻改送下一個 Hold Code（OTHL）；必要時再送第三碼。不等下一分鐘。",
        "then": "OTHL 的 Default Hold 已送出（同一輪已試過 ENHL）。",
        "dont": "再送一次已經被拒的 ENHL；也不要等下一輪 Cron 才改碼。",
    },
    "C08": {
        "given": "本系統已確認 Default Hold 設上。後來現場把這筆 Hold 解掉了。",
        "do": "向 MES 再查一次：找不到自己的 Default Hold，就當線上代解成功並結案。",
        "then": "這張單結案（線上代解）；訂單表留紀錄。",
        "dont": "當成事故再設一筆 Hold；也不要標成「全數 OK 結案」。",
    },
    "C09": {
        "given": "所有 wafer 已掃完，有 Defect，現場還沒有 SMM Hold。最後一片掃完已滿 2 分鐘。",
        "do": "不等 SMM Hold，向 MES 申請解除 Default Hold。保護空窗由另一隻程式處理。",
        "then": "解除已送出；結案原因 SCAN_COMPLETED。不留 data_error、不開告警。",
        "dont": "冒充去設 SMM Hold。全 OK 或已有 SMM Hold 不要再等 2 分鐘。",
    },
    "C10": {
        "given": "Default Hold 已在；有 Defect；MES 上已有 SMM Hold。",
        "do": "確認 SMM Hold 已接手後，向 MES 申請解除 Default Hold。不解 SMM Hold。",
        "then": "解除 Default Hold 已送出；SMM Hold 還在；這張單還沒結案。",
        "dont": "把 SMM Hold 一起解掉；這一輪就把單結案。",
    },
    "C11": {
        "given": "已申請解除 Default Hold；SMM Hold 還在。",
        "do": "確認自己的 Default Hold 已解除，這張單結案。SMM Hold 必須還在。",
        "then": "單結案（已交給 SMM Hold）；SMM Hold 仍在。",
        "dont": "把 SMM Hold 一起解掉。",
    },
    "T03": {
        "given": "ENHL、OTHL、第三碼都被 MES 明確衝突拒絕。",
        "do": "試完清單就停，開 HOLD_FAILED 告警。",
        "then": "沒有本系統 Hold；有 HOLD_FAILED。",
        "dont": "再空等 30 分鐘。",
    },
    "T04": {
        "given": "送 Hold 回 Timeout，但再查 MES，本系統 Hold 已經在。",
        "do": "只查驗、確認；不要再送。",
        "then": "已保護；Hold 只送過 1 次。",
        "dont": "Timeout 就換 Code 或再 Hold 一次。",
    },
    "T05": {
        "given": "送 Hold 回 Timeout，Hold 沒落地，list_holds 也 UNKNOWN。",
        "do": "維持查驗／UNKNOWN。",
        "then": "不是 HOLD_FAILED。",
        "dont": "把 Timeout 或 UNKNOWN 當成沒有 Hold。",
    },
    "T06": {
        "given": "Hold 已在 MES（送出成功）。中斷後下一輪程式再起來。",
        "do": "SET 看到已有 in-flight／已有 Hold 就不重送；CONFIRM 再 list_holds，Memo+User+Code 對上就確認成功。",
        "then": "同一筆 Hold 確認成功（WAIT_AI／CONFIRMED）；set_hold 仍 1 次。",
        "dont": "再新建一筆 Hold。",
    },
    "T09": {
        "given": "25 片只掃完 24 片。",
        "do": "繼續等。",
        "then": "WAIT_AI。",
        "dont": "Release。",
    },
    "T10": {
        "given": "Log 有 25 筆，但其實缺一片、另一片重複。",
        "do": "當未齊，列出缺的 wafer。",
        "then": "WAIT_AI。",
        "dont": "用筆數=25 就當完成。",
    },
    "T11": {
        "given": "Expected wafer 名單還是空的。",
        "do": "繼續等。",
        "then": "WAIT_AI。",
        "dont": "空名單當成全部完成而 Release。",
    },
    "T12": {
        "given": "Default Hold 已設上。有片有 ScanCompletedTime，但沒有 Alarm Type。",
        "do": "先當掃完（可繼續判斷／解除）。同時在 order_wafer.missing_alarm_type 留下紀錄，事後可查。",
        "then": "不當 AI_RESULT_INVALID；W03 等片在 Order DB 有 missing_alarm_type=1。",
        "dont": "沒有 Alarm Type 就卡住不解，又不留紀錄。",
    },
    "T13": {
        "given": "同一 Lot 出現 Rework 1；Rework 0 的 AI 已經有了。",
        "do": "Rework 1 自己建單、自己 Hold、等自己的 AI。",
        "then": "兩張單都在；Rework 1 仍在等。",
        "dont": "拿 Rework 0 的結果或 Hold 給 Rework 1 用。",
    },
    "T14": {
        "given": "AI 有 Defect，MES 上已有正式 SmmHold。",
        "do": "只解除本系統 Default Hold。",
        "then": "Default Hold 沒了；SmmHold 還在；結案 TRANSFERRED。",
        "dont": "把正式 Defect Hold 一起解掉。",
    },
    "T15": {
        "given": "AI 有 Defect，正式 SmmHold 不在。掃完已滿 2 分鐘。",
        "do": "申請解除 Default Hold；結案 SCAN_COMPLETED。",
        "then": "RELEASE_SENT；close_reason=SCAN_COMPLETED。",
        "dont": "留 data_error／C09 告警；冒充設 SMM Hold。",
    },
    "T16": {
        "given": "Release 回 Timeout，再查 MES 上自己的 Hold 已經沒了。",
        "do": "以查驗為準，CLOSED。",
        "then": "訂單結束；沒有再 SET Hold。",
        "dont": "看到沒 Hold 又建一筆。",
    },
    "T17": {
        "given": "Release 被明確拒絕，Hold 還在。",
        "do": "RELEASE_FAILED，Hold 留著，告警。",
        "then": "訂單仍 OPEN。",
        "dont": "直接 CLOSED。",
    },
    "T18": {
        "given": "MES 上已有別人的 ENHL，Memo 不是我們的標準 Memo。",
        "do": "仍用自己的 Memo 送 ENHL。查驗只認我們的 Memo。若自己的 ENHL 設不上（明確衝突／已確認沒設上），依清單再試 OTHL。",
        "then": "本單有自己的 Default Hold（ENHL 或備援 OTHL）；別人的 Hold 還在。",
        "dont": "把別人的當成已保護，或去解別人的 Hold。",
    },
    "T18b": {
        "situation": "他人 ENHL、Memo 不同，且自己的 ENHL 設不上",
        "expected": "不視為本 Order Hold；改送 OTHL 防守",
        "forbidden": "解除或冒領別人的 Hold",
        "given": "別人的 ENHL（不同 Memo）還在；我們送 ENHL 被 MES 衝突拒絕、沒設上。",
        "do": "不把那筆當自己的；依備援清單送 OTHL，再查驗 OTHL。",
        "then": "本單用 OTHL 保護；別人的 ENHL 還在。",
        "dont": "解掉別人的 ENHL，或把那筆 ENHL 標成已確認。",
    },
    "T19": {
        "given": "本系統已經確認 Default Hold 設上。後來 MES 上沒了（線上幫忙解；包含我們自己 Release 掛掉請線上解）。",
        "do": "當成解除成功，訂單 CLOSED（LINE_RELEASED）。",
        "then": "不再 SET Hold；不開 HOLD_MISSING 告警。",
        "dont": "當成事故補防守；也不要標成 AI_OK。",
    },
    "T20": {
        "given": "人工要結案，有人。",
        "do": "MANUAL_CLOSED，留下是誰核的。",
        "then": "不是 AI_OK。",
        "dont": "標成自動 AI 完成。",
    },
    "T21": {
        "given": "YAML 那些量測站都已經走過，Lot 在 OP400。",
        "do": "Target 設在目前站 OP400。",
        "then": "Hold 在 OP400。",
        "dont": "還去已經過的 August 掛 Future Hold。",
    },
    "T22": {
        "given": "Lot 在 OP100，August OP200 還在後面。",
        "do": "選還在前方的優先站 August。",
        "then": "Target = OP200。",
        "dont": "用字串排序或當成全部已過。",
    },
    "T24": {
        "given": "Target 已選、Hold 已確認之後，Lot 又往前走。",
        "do": "已確認就不重選、不重送。（已跟你確認：不是每次執行都重選）",
        "then": "仍是原來那一筆 Hold。",
        "dont": "用移動前的站再建一筆。",
    },
    "T25": {
        "given": "（現場不適用）MES 一定能準確回答這批有沒有 Hold。",
        "do": "不用為 UNKNOWN／問不到寫契約。list_holds 會回有或沒有。",
        "then": "此題不列入驗收。",
        "dont": "不要把「問不到」當成現場會發生的情境。",
    },
    "T26": {
        "given": "Default Hold 掛著，時間走到 29:59／30:00／30:01。",
        "do": "只有超過 30 分才 Watchdog。",
        "then": "30:01 才 HOLD_OVERDUE；時間標「本機估計」。",
        "dont": "30:00 就告警。",
    },
    "T27": {
        "given": "超時的 Hold 可能同一 Lot 有兩筆。",
        "do": "按不同 Lot 計數，滿 3 個 Lot 才停用新 Hold。",
        "then": "DISABLED_NEW_HOLD。",
        "dont": "同一 Lot 兩筆 Hold 當成兩個 Lot。",
    },
    "T28": {
        "given": "已停用新 Hold；舊單 AI 變 OK。",
        "do": "舊單仍可 Release。",
        "then": "舊單 CLOSED。",
        "dont": "整個 Agent 停住、連解除都不做。",
    },
    "T29": {
        "given": "SMM 進站名單與本系統防守名單張數一樣，但 Lot 不一樣。",
        "do": "列出缺的、多的，告警。",
        "then": "COVERAGE_MISMATCH。",
        "dont": "只看張數相等就當覆蓋完成。",
    },
    "T30": {
        "given": "MES 有本系統 Memo 的 Hold，沒有對應訂單。",
        "do": "ORPHAN_HOLD 告警，等人。",
        "then": "Hold 還在。",
        "dont": "自動解掉不明 Hold。",
    },
    "T31": {
        "given": "訂單已 CLOSED，MES 又出現本系統 Memo 的 Hold。",
        "do": "STATE_CONFLICT。",
        "then": "有告警。",
        "dont": "當成正常完成忽略。",
    },
    "T34": {
        "given": "新 Hold 已停，Resume 沒有 sponsor。",
        "do": "拒絕。",
        "then": "仍停用。",
        "dont": "自動又開始 Default Hold。",
    },
    "T34b": {
        "given": "Resume 有 sponsor 和證據。",
        "do": "恢復 ENABLED。",
        "then": "可以再設新 Hold。",
        "dont": "沒證據也恢復。",
    },
    "T35": {
        "given": "主路徑心跳超過 5 分鐘沒動。",
        "do": "AGENT_STALL 告警。",
        "then": "外面看得到未防守。",
        "dont": "等故障程式自己通報。",
    },
    "T36": {
        "given": "進站 wafer 名單變了。",
        "do": "MANUAL_REVIEW。",
        "then": "停自動。",
        "dont": "默默改用新名單繼續解。",
    },
    "T37": {
        "given": "一筆過期的進站事件晚到。",
        "do": "不拿它覆蓋已確認的訂單。",
        "then": "原單不變。",
        "dont": "用到達時間把狀態倒回去。",
    },
    "T38": {
        "given": "MES 權限拒絕 Hold。",
        "do": "立刻停，HOLD_FAILED。",
        "then": "只送過 1 次。",
        "dont": "再拿 OTHL、第三碼去打同一個權限錯誤。",
    },
    "AI_UNKNOWN": {
        "given": "AI 查詢回 UNKNOWN，不是 0 片。",
        "do": "WAIT_AI，狀態 UNKNOWN。",
        "then": "不解 Hold。",
        "dont": "當成掃完或當成空。",
    },
    "HOLD_RETRY3": {
        "given": "同一筆 SET_HOLD 暫時被拒。",
        "do": "同一命令最多送 3 次（含第 1 次）。",
        "then": "第 4 次不起；HOLD_FAILED。",
        "dont": "無止盡重試，或每次重試建成新命令。",
    },
    "HOLD_TIMEOUT_RETRY3": {
        "given": "Timeout，查驗證實沒落地。",
        "do": "先查再重送同一筆，最多 3 次。",
        "then": "HOLD_FAILED。",
        "dont": "查詢還 UNKNOWN 就重送或換 Code。",
    },
    "HOLD_UNKNOWN_NO_RESEND": {
        "given": "Timeout 後 list_holds 仍 UNKNOWN。",
        "do": "停在查驗。",
        "then": "set_hold 仍 1 次。",
        "dont": "UNKNOWN 當沒有 Hold 再送一次。",
    },
    "REL_RETRY3": {
        "given": "同一筆 Release 暫時被拒。",
        "do": "同一命令最多 3 次。",
        "then": "RELEASE_FAILED，Hold 還在。",
        "dont": "直接 CLOSED。",
    },
    "REL_TIMEOUT_RETRY3": {
        "given": "已送解除，Timeout，MES 上自己的 Hold 還看得到。",
        "do": "當成 DB Delay：進入查驗格，不重送、不當失敗。",
        "then": "RELEASE_VERIFY_PENDING；release 仍 1 次。",
        "dont": "Delay 就重送或當已解除而 CLOSED。",
    },
    "XFER_ACCUM": {
        "given": "第一片 Defect 已有 Lot Hold「Please check #1」；第二片又 Defect。",
        "do": "transferHold 把 Memo 改成 Please check #1,#2；Default Hold 先不解。",
        "then": "仍一筆 SmmHold；Memo 已累積。",
        "dont": "再 SET 一筆 SmmHold，或把 Default Hold 解掉。",
    },
    "XFER_RETRY3": {
        "given": "transferHold 暫時被拒。",
        "do": "同一命令最多 3 次。",
        "then": "Memo 仍 #1；Default Hold 不解。",
        "dont": "無止盡重試，或當成 Memo 已改。",
    },
}

def _s(sid: str, group: str, title: str, script: list, expect: dict, given=None, settings=None, n=0, enabled=True) -> ScenarioCase:
    return ScenarioCase(
        scenario_id=sid,
        group_name=group,
        title=title,
        script=script,
        expect=expect,
        given=given or {},
        settings=settings or {},
        spec={**(SPEC.get(sid) or {}), **(ENG.get(sid) or {})},
        sort_order=n,
        enabled=enabled,
    )


def seed_cases() -> list[ScenarioCase]:
    cases = [
        _s("T01", "v1", "【串接】進站到結案（對照用，驗收看 C01～C06）", HAPPY + [
            {"op": "complete_ai", "lot_id": "LOT1"},
            {"op": "run", "fn": "check"},
            {"op": "run", "fn": "release"},
        ], {
            "lifecycle": "CLOSED",
            "close_reason": "AI_OK",
            "last_rule_id": "A2-11",
            "actions": {"set_hold": 1, "release": 1, "transfer": 0},
            "facts": {
                "Lot": {"LotId": "LOT1", "OpeNo": "OP100"},
                "DefaultHold": {"QueryStatus": "NOT_FOUND"},
            },
        }, n=1),
        _s("C01", "stage", "C01 送 Hold（原 T01-SET）", [
            {"op": "add_lot", "lot_id": "LOT1"},
            {"op": "run", "fn": "set"},
        ], {
            "work_state": "HOLD_VERIFY_PENDING",
            "protection_state": "SET_PENDING",
            "lifecycle": "OPEN",
            "actions": {"set_hold": 1, "release": 0},
        }, n=1),
        _s("C02", "stage", "C02 查 Hold 存在（原 T01-CONFIRM）", HAPPY, {
            "work_state": "WAIT_AI",
            "protection_state": "CONFIRMED",
            "lifecycle": "OPEN",
            "actions": {"set_hold": 1, "release": 0},
        }, n=2),
        _s("C03", "stage", "C03 等所有 Wafer 判斷完 SMM（原 T01-WAIT）", HAPPY + [
            {"op": "run", "fn": "check"},
        ], {
            "work_state": "WAIT_AI",
            "actions": {"release": 0},
        }, n=3),
        _s("C04", "stage", "C04 申請解除 Default Hold（原 T01-CHECK）", HAPPY + [
            {"op": "complete_ai", "lot_id": "LOT1"},
            {"op": "run", "fn": "check"},
        ], {
            "work_state": "RELEASE_SENT",
            "actions": {"release": 1},
            "lifecycle": "OPEN",
        }, n=4),
        _s("C05", "stage", "C05 查驗解除（允許 DB Delay）", HAPPY + [
            {"op": "complete_ai", "lot_id": "LOT1"},
            {"op": "set_world", "release_response": {"LOT1": "timeout"}, "set_effect": {"release:LOT1": "none"}},
            {"op": "run", "fn": "check"},
            {"op": "run", "fn": "release"},
        ], {
            "work_state": "RELEASE_VERIFY_PENDING",
            "lifecycle": "OPEN",
            "actions": {"release": 1},
        }, n=5),
        _s("C06", "stage", "C06 確認已解除才結案（原 T01-RELEASE）", HAPPY + [
            {"op": "complete_ai", "lot_id": "LOT1"},
            {"op": "run", "fn": "check"},
            {"op": "run", "fn": "release"},
        ], {
            "lifecycle": "CLOSED",
            "close_reason": "AI_OK",
            "work_state": "CLOSED",
        }, n=6),
        _s("T02", "v1", "【串接】ENHL 衝突後改 OTHL", [
            {"op": "add_lot", "lot_id": "LOT1"},
            {"op": "set_world", "set_response": {"LOT1": ["rejected_conflict", "accepted"]}},
            {"op": "run", "fn": "set"},
            {"op": "run", "fn": "confirm"},
        ], {
            "protection_state": "CONFIRMED",
            "work_state": "WAIT_AI",
            "actions": {"set_hold": 2},
            "command_count": {"SET_HOLD": 2},
        }, n=2),
        _s("C07", "stage", "C07 ENHL 衝突後同一輪改送 OTHL（原 T02）", [
            {"op": "add_lot", "lot_id": "LOT1"},
            {"op": "set_world", "set_response": {"LOT1": ["rejected_conflict", "accepted"]}},
            {"op": "run", "fn": "set"},
        ], {
            "actions": {"set_hold": 2},
            "command_count": {"SET_HOLD": 2},
            "lifecycle": "OPEN",
        }, n=7),
        _s("T03", "hold", "所有 Hold Code 失敗", [
            {"op": "add_lot", "lot_id": "LOT1"},
            {"op": "set_world", "set_response": {"LOT1": "rejected_conflict"}},
            {"op": "run", "fn": "set"},
        ], {
            "work_state": "HOLD_FAILED",
            "incidents": ["HOLD_FAILED"],
        }, settings={"hold": {"codes": ["ENHL", "OTHL", "HOLD3"]}}, n=3),
        _s("T04", "hold", "Timeout 但 MES 已有 Hold，不重送", [
            {"op": "add_lot", "lot_id": "LOT1"},
            {"op": "set_world", "set_response": {"LOT1": "timeout"}},
            {"op": "run", "fn": "set"},
            {"op": "run", "fn": "confirm"},
            {"op": "run", "fn": "set"},
        ], {
            "protection_state": "CONFIRMED",
            "actions": {"set_hold": 1},
        }, n=4),
        _s("T05", "hold", "Timeout 且查詢 UNKNOWN，不當失敗", [
            {"op": "add_lot", "lot_id": "LOT1"},
            {"op": "set_world", "set_response": {"LOT1": "timeout"}, "set_effect": {"LOT1": "none"}},
            {"op": "run", "fn": "set"},
            {"op": "set_world", "list_status": {"LOT1": "unknown"}},
            {"op": "run", "fn": "confirm"},
        ], {
            "work_state": "HOLD_VERIFY_PENDING",
        }, n=5),
        _s("T06", "hold", "送出後重啟只查驗不重送", [
            {"op": "add_lot", "lot_id": "LOT1"},
            {"op": "run", "fn": "set"},
            {"op": "run", "fn": "confirm"},
        ], {
            "protection_state": "CONFIRMED",
            "actions": {"set_hold": 1},
        }, n=6),
        _s("T09", "ai", "缺一片，繼續等", HAPPY + [
            {"op": "complete_ai", "lot_id": "LOT1", "skip": ["W25"]},
            {"op": "run", "fn": "check"},
        ], {
            "work_state": "WAIT_AI",
            "actions": {"release": 0},
            "facts": {"AiScan": {"QueryStatus": "FOUND"}},
        }, n=9),
        _s("T10", "ai", "數量對但缺＋重，繼續等", HAPPY + [
            {"op": "complete_ai", "lot_id": "LOT1", "skip": ["W25"], "extra_duplicate": "W01"},
            {"op": "run", "fn": "check"},
        ], {"work_state": "WAIT_AI", "actions": {"release": 0}}, n=10),
        _s("T11", "ai", "空 roster 不解", [
            {"op": "add_lot", "lot_id": "LOT1", "wafers": []},
            {"op": "run", "fn": "set"},
            {"op": "run", "fn": "confirm"},
            {"op": "run", "fn": "check"},
        ], {"work_state": "WAIT_AI", "actions": {"release": 0}}, n=11),
        _s("T12", "ai", "有 ScanCompletedTime 無 Alarm Type → 當完成並留紀錄", HAPPY + [
            {"op": "complete_ai", "lot_id": "LOT1", "missing_result": "W03"},
            {"op": "run", "fn": "check"},
        ], {
            "work_state": "RELEASE_SENT",
            "missing_alarm_wafers": ["W03"],
        }, n=12),
        _s("T13", "order", "Rework 隔離", [
            {"op": "add_lot", "lot_id": "LOT1", "rework_count": 0},
            {"op": "run", "fn": "set"},
            {"op": "run", "fn": "confirm"},
            {"op": "complete_ai", "lot_id": "LOT1", "rework_count": 0},
            {"op": "add_lot", "lot_id": "LOT1", "rework_count": 1, "event_id": "evt-rw1"},
            {"op": "run", "fn": "set"},
            {"op": "run", "fn": "confirm"},
        ], {
            "rw": 1,
            "work_state": "WAIT_AI",
            "lifecycle": "OPEN",
            "open_count": 2,
        }, n=13),
        _s("T14", "v1", "【串接】Defect 交接走到結案", HAPPY + [
            {"op": "complete_ai", "lot_id": "LOT1", "result": "DEFECT"},
            {"op": "add_defect_hold", "lot_id": "LOT1"},
            {"op": "run", "fn": "check"},
            {"op": "run", "fn": "release"},
        ], {
            "lifecycle": "CLOSED",
            "close_reason": "TRANSFERRED",
            "last_rule_id": "A2-11",
            "facts": {"SmmHold": {"Holds": [{"HoldCode": "SMMH", "HoldUser": "AOA"}]}},
        }, n=14),
        _s("C10", "stage", "C10 有 SMM Hold 才申請解除 Default Hold（原 T14-CHECK）", HAPPY + [
            {"op": "complete_ai", "lot_id": "LOT1", "result": "DEFECT"},
            {"op": "add_defect_hold", "lot_id": "LOT1"},
            {"op": "run", "fn": "check"},
        ], {
            "work_state": "RELEASE_SENT",
            "lifecycle": "OPEN",
            "actions": {"release": 1},
            "facts": {"SmmHold": {"Holds": [{"HoldCode": "SMMH", "HoldUser": "AOA"}]}},
        }, n=10),
        _s("C11", "stage", "C11 確認已解除且 SMM Hold 仍在（原 T14-RELEASE）", HAPPY + [
            {"op": "complete_ai", "lot_id": "LOT1", "result": "DEFECT"},
            {"op": "add_defect_hold", "lot_id": "LOT1"},
            {"op": "run", "fn": "check"},
            {"op": "run", "fn": "release"},
        ], {
            "lifecycle": "CLOSED",
            "close_reason": "TRANSFERRED",
            "facts": {"SmmHold": {"Holds": [{"HoldCode": "SMMH", "HoldUser": "AOA"}]}},
        }, n=11),
        _s("C09", "stage", "C09 有 Defect 無 SMM Hold 逾時解（原 T15）", HAPPY + [
            {"op": "complete_ai", "lot_id": "LOT1", "result": "DEFECT"},
            {"op": "advance", "minutes": 2},
            {"op": "run", "fn": "check"},
        ], {
            "work_state": "RELEASE_SENT",
            "lifecycle": "OPEN",
            "close_reason": "SCAN_COMPLETED",
            "data_error": None,
            "actions": {"release": 1},
            "incidents": [],
        }, n=9),
        _s("T16", "release", "Release timeout 但 Hold 已消失 → CLOSED", HAPPY + [
            {"op": "complete_ai", "lot_id": "LOT1"},
            {"op": "set_world", "release_response": {"LOT1": "timeout"}},
            {"op": "run", "fn": "check"},
            {"op": "run", "fn": "set"},
            {"op": "run", "fn": "release"},
        ], {
            "lifecycle": "CLOSED",
            "actions": {"set_hold": 1, "release": 1},
        }, n=16),
        _s("T17", "release", "Release 被拒，Hold 仍在", HAPPY + [
            {"op": "complete_ai", "lot_id": "LOT1"},
            {"op": "set_world", "release_response": {"LOT1": "rejected_permission"}},
            {"op": "run", "fn": "check"},
            {"op": "run", "fn": "release"},
        ], {
            "work_state": "RELEASE_FAILED",
            "lifecycle": "OPEN",
            "incidents": ["RELEASE_FAILED"],
        }, n=17),
        _s("T18", "hold", "別人的 ENHL 不是我們的", [
            {"op": "add_lot", "lot_id": "LOT1"},
            {"op": "add_foreign_hold", "lot_id": "LOT1", "hold_code": "ENHL", "memo": "SOME OTHER MEMO", "ope_no": "OP200"},
            {"op": "run", "fn": "set"},
            {"op": "run", "fn": "confirm"},
        ], {
            "protection_state": "CONFIRMED",
            "work_state": "WAIT_AI",
            "actions": {"set_hold": 1, "release": 0},
        }, n=18),
        _s("T18b", "hold", "別人的 ENHL 不是我們的，自己的 ENHL 設不上就試 OTHL", [
            {"op": "add_lot", "lot_id": "LOT1"},
            {"op": "add_foreign_hold", "lot_id": "LOT1", "hold_code": "ENHL", "memo": "SOME OTHER MEMO", "ope_no": "OP200"},
            {"op": "set_world", "set_response": {"LOT1": ["rejected_conflict", "accepted"]}},
            {"op": "run", "fn": "set"},
            {"op": "run", "fn": "confirm"},
        ], {
            "protection_state": "CONFIRMED",
            "work_state": "WAIT_AI",
            "actions": {"set_hold": 2, "release": 0},
            "command_count": {"SET_HOLD": 2},
        }, n=181),
        _s("C08", "stage", "C08 線上代解視為成功（原 T19）", HAPPY + [
            {"op": "clear_holds"},
            {"op": "run", "fn": "confirm"},
        ], {
            "lifecycle": "MANUAL_CLOSED",
            "close_reason": "MANUAL",
            "incidents_absent": ["HOLD_MISSING"],
        }, n=8),
        _s("T20", "control", "人工結案", HAPPY + [
            {"op": "run", "fn": "close", "lot_id": "LOT1"},
        ], {
            "lifecycle": "MANUAL_CLOSED",
            "close_reason": "MANUAL",
        }, n=20),
        _s("T21", "target", "配置站都過了 → Hold 目前站", [
            {"op": "add_lot", "lot_id": "LOT1", "current_ope_no": "OP400"},
            {"op": "run", "fn": "set"},
        ], {"target_ope_no": "OP400"}, n=21),
        _s("T22", "target", "目前 OP100 → Future August OP200", [
            {"op": "add_lot", "lot_id": "LOT1", "current_ope_no": "OP100"},
            {"op": "run", "fn": "set"},
        ], {"target_ope_no": "OP200"}, n=22),
        _s("T24", "target", "已保護不因移站重送", [
            {"op": "add_lot", "lot_id": "LOT1", "current_ope_no": "OP100"},
            {"op": "run", "fn": "set"},
            {"op": "run", "fn": "confirm"},
        ], {
            "protection_state": "CONFIRMED",
            "target_ope_no": "OP200",
            "actions": {"set_hold": 1},
        }, n=24),
        _s("T25", "hold", "【現場不適用】Hold 查詢 UNKNOWN", [
            {"op": "add_lot", "lot_id": "LOT1"},
            {"op": "set_world", "list_status": {"LOT1": "unknown"}},
            {"op": "run", "fn": "set"},
            {"op": "run", "fn": "confirm"},
        ], {
            "work_state": "OBSERVATION_UNKNOWN",
        }, n=25, enabled=False),
        _s("T26", "defense", "Watchdog >30 分標 ESTIMATED", HAPPY + [
            {"op": "advance", "minutes": 30, "seconds": 1},
            {"op": "run", "fn": "defense"},
        ], {"incidents": ["HOLD_OVERDUE"]}, n=26),
        _s("T27", "defense", "三批超時停用新 Hold", [
            {"op": "add_lot", "lot_id": "L0"},
            {"op": "run", "fn": "set"},
            {"op": "run", "fn": "confirm"},
            {"op": "add_lot", "lot_id": "L1"},
            {"op": "run", "fn": "set"},
            {"op": "run", "fn": "confirm"},
            {"op": "add_lot", "lot_id": "L2"},
            {"op": "run", "fn": "set"},
            {"op": "run", "fn": "confirm"},
            {"op": "advance", "minutes": 31},
            {"op": "run", "fn": "defense"},
        ], {
            "lot_id": "L0",
            "ope": "OP100",
            "control_mode": "DISABLED_NEW_HOLD",
            "incidents": ["CONTROL_DISABLED"],
        }, n=27),
        _s("T28", "control", "停用新 Hold 仍可解除", HAPPY + [
            {"op": "disable_control"},
            {"op": "complete_ai", "lot_id": "LOT1"},
            {"op": "run", "fn": "check"},
            {"op": "run", "fn": "release"},
        ], {"lifecycle": "CLOSED"}, n=28),
        _s("T29", "defense", "覆蓋率不一致", [
            {"op": "add_lot", "lot_id": "A"},
            {"op": "add_lot", "lot_id": "B"},
            {"op": "run", "fn": "set"},
            {"op": "run", "fn": "confirm"},
            {"op": "add_lot", "lot_id": "C", "event_id": "evt-c"},
            {"op": "run", "fn": "defense"},
        ], {"incidents": ["COVERAGE_MISMATCH"]}, n=29),
        _s("T30", "defense", "Orphan Hold 不自動解", [
            {"op": "add_lot", "lot_id": "ORPH"},
            {"op": "run", "fn": "defense"},
        ], {"incidents": ["ORPHAN_HOLD"]}, given={
            "holds": [{"lot_id": "ORPH", "ope_no": "OP200", "hold_code": "ENHL", "hold_user": "ABO"}],
        }, n=30),
        _s("T31", "defense", "已結案又出現本系統 Hold", HAPPY + [
            {"op": "complete_ai", "lot_id": "LOT1"},
            {"op": "run", "fn": "check"},
            {"op": "run", "fn": "release"},
            {"op": "add_standard_hold", "lot_id": "LOT1", "ope_no": "OP200"},
            {"op": "run", "fn": "defense"},
        ], {"incidents": ["STATE_CONFLICT"]}, n=31),
        _s("T34", "control", "Resume 要 sponsor", [
            {"op": "disable_control"},
            {"op": "run", "fn": "resume"},
        ], {"control_mode": "DISABLED_NEW_HOLD"}, n=34),
        _s("T34b", "control", "Resume 有 sponsor", [
            {"op": "disable_control"},
            {"op": "run", "fn": "resume", "params": {"sponsor": "SP1", "evidence": "fixed"}},
        ], {"control_mode": "ENABLED"}, n=341),
        _s("T35", "defense", "心跳過期 AGENT_STALL", [
            {"op": "add_lot", "lot_id": "LOT1"},
            {"op": "run", "fn": "set"},
            {"op": "advance", "minutes": 6},
            {"op": "run", "fn": "defense"},
        ], {"incidents": ["AGENT_STALL"]}, n=35),
        _s("T36", "order", "Roster 變更 → MANUAL_REVIEW", [
            {"op": "add_lot", "lot_id": "LOT1", "wafers": 25},
            {"op": "run", "fn": "set"},
            {"op": "append_event", "lot_id": "LOT1", "event_id": "evt-split", "payload": "W01,W02"},
            {"op": "run", "fn": "set"},
        ], {
            "work_state": "MANUAL_REVIEW",
            "incidents": ["MANUAL_REVIEW"],
        }, n=36),
        _s("T37", "order", "過期進站事件不重建", HAPPY + [
            {"op": "append_event", "lot_id": "LOT1", "event_id": "evt-late", "stale_hours": 2,
             "payload": ",".join(f"W{i:02d}" for i in range(1, 26))},
            {"op": "run", "fn": "set"},
        ], {"work_state": "WAIT_AI"}, n=37),
        _s("T38", "hold", "Permission 失敗不換備援 Code", [
            {"op": "add_lot", "lot_id": "LOT1"},
            {"op": "set_world", "set_response": {"LOT1": "rejected_permission"}},
            {"op": "run", "fn": "set"},
            {"op": "run", "fn": "confirm"},
            {"op": "run", "fn": "set"},
        ], {
            "work_state": "HOLD_FAILED",
            "actions": {"set_hold": 1},
        }, n=38),
        _s("AI_UNKNOWN", "ai", "AI UNKNOWN 不當空掃完", HAPPY + [
            {"op": "ai_unavailable", "lot_id": "LOT1"},
            {"op": "run", "fn": "check"},
        ], {
            "work_state": "WAIT_AI",
            "ai_state": "UNKNOWN",
            "actions": {"release": 0},
            "facts": {"AiScan": {"QueryStatus": "UNKNOWN"}},
        }, n=50),
        _s("HOLD_RETRY3", "retry", "SET_HOLD 暫時拒絕同一命令 3 次", [
            {"op": "add_lot", "lot_id": "LOT1"},
            {"op": "set_world", "set_response": {"LOT1": "rejected_transient"}},
            {"op": "repeat", "times": 5, "steps": [{"op": "run", "fn": "set"}]},
        ], {
            "work_state": "HOLD_FAILED",
            "actions": {"set_hold": 3},
            "command_count": {"SET_HOLD": 1},
            "attempt_max": 3,
        }, n=51),
        _s("HOLD_TIMEOUT_RETRY3", "retry", "SET_HOLD timeout 查驗後重送 3 次", [
            {"op": "add_lot", "lot_id": "LOT1"},
            {"op": "set_world", "set_response": {"LOT1": "timeout"}, "set_effect": {"LOT1": "none"}},
            {"op": "repeat", "times": 4, "steps": [{"op": "run", "fn": "set"}, {"op": "run", "fn": "confirm"}]},
        ], {
            "work_state": "HOLD_FAILED",
            "actions": {"set_hold": 3},
            "attempt_max": 3,
        }, n=52),
        _s("HOLD_UNKNOWN_NO_RESEND", "retry", "查詢 UNKNOWN 不重送", [
            {"op": "add_lot", "lot_id": "LOT1"},
            {"op": "set_world", "set_response": {"LOT1": "timeout"}, "set_effect": {"LOT1": "none"}},
            {"op": "run", "fn": "set"},
            {"op": "set_world", "list_status": {"LOT1": "unknown"}},
            {"op": "run", "fn": "confirm"},
            {"op": "run", "fn": "set"},
        ], {"actions": {"set_hold": 1}}, n=53),
        _s("REL_RETRY3", "retry", "SET_RELEASE 暫時拒絕同一命令 3 次", HAPPY + [
            {"op": "complete_ai", "lot_id": "LOT1"},
            {"op": "set_world", "release_response": {"LOT1": "rejected_transient"}},
            {"op": "repeat", "times": 5, "steps": [{"op": "run", "fn": "check"}, {"op": "run", "fn": "release"}]},
        ], {
            "work_state": "RELEASE_FAILED",
            "lifecycle": "OPEN",
            "actions": {"release": 3},
            "command_count": {"SET_RELEASE": 1},
            "attempt_max": 3,
        }, n=54),
        _s("REL_TIMEOUT_RETRY3", "retry", "Release timeout 且 Hold 還看得到＝Delay，不重送", HAPPY + [
            {"op": "complete_ai", "lot_id": "LOT1"},
            {"op": "set_world", "release_response": {"LOT1": "timeout"}, "set_effect": {"release:LOT1": "none"}},
            {"op": "run", "fn": "check"},
            {"op": "run", "fn": "release"},
            {"op": "run", "fn": "release"},
        ], {
            "work_state": "RELEASE_VERIFY_PENDING",
            "lifecycle": "OPEN",
            "actions": {"release": 1},
        }, n=55),
        _s("XFER_ACCUM", "smm", "Please check #1 → transferHold #1,#2", HAPPY + [
            {"op": "scan_wafer", "lot_id": "LOT1", "wafer_id": "W01", "result": "DEFECT"},
            {"op": "add_defect_hold", "lot_id": "LOT1", "memo": "Please check #1"},
            {"op": "run", "fn": "check"},
            {"op": "scan_wafer", "lot_id": "LOT1", "wafer_id": "W02", "result": "DEFECT"},
            {"op": "run", "fn": "check"},
        ], {
            "work_state": "WAIT_AI",
            "smm_memo": "Please check #1,#2",
            "actions": {"transfer": 1, "release": 0},
            "facts": {"SmmHold": {"Holds": [{"HoldMemo": "Please check #1,#2"}]}},
        }, n=56),
        _s("XFER_RETRY3", "retry", "transferHold 暫時拒絕同一命令 3 次", HAPPY + [
            {"op": "scan_wafer", "lot_id": "LOT1", "wafer_id": "W01", "result": "DEFECT"},
            {"op": "add_defect_hold", "lot_id": "LOT1", "memo": "Please check #1"},
            {"op": "run", "fn": "check"},
            {"op": "scan_wafer", "lot_id": "LOT1", "wafer_id": "W02", "result": "DEFECT"},
            {"op": "set_world", "transfer_response": {"LOT1": "rejected_transient"}},
            {"op": "repeat", "times": 5, "steps": [{"op": "run", "fn": "check"}]},
        ], {
            "work_state": "WAIT_AI",
            "smm_memo": "Please check #1",
            "actions": {"transfer": 3},
            "command_count": {"TRANSFER_HOLD": 1},
            "attempt_max": 3,
            "lifecycle": "OPEN",
        }, n=57),
    ]
    # T30 given holds use standard memo; apply_given uses hold.get("memo") or settings
    return cases


def seed_catalog(catalog) -> int:
    keep = {c.scenario_id for c in seed_cases()}
    for old in catalog.list_all():
        if old.scenario_id not in keep and hasattr(catalog, "delete"):
            catalog.delete(old.scenario_id)
    for case in seed_cases():
        catalog.upsert(case)
    return catalog.count()
