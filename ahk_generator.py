# -*- coding: utf-8 -*-
"""
PinPanther 🐾 —— AutoHotkey v2 腳本產生器
=========================================

把 PinPanther 的規則（dict 清單）轉成一支「常駐式反應定位」的 AHK v2 腳本。

產生的腳本在開機（隨 shell:startup 的捷徑）啟動後會：
    1. 設定 Per-Monitor-V2 DPI 感知，座標才與 MonitorGet 一致。
    2. 列舉螢幕並依「左→右、上→下」排序，對應 GUI 的螢幕編號（0..N-1）。
    3. 開機初掃：先處理「腳本啟動前就已開著」的視窗。
    4. 掛 Shell window-created 事件：新視窗一建立就立刻定位（比輪詢靈敏）。
    5. 補掃：開機後一段時間內定期再掃，抓慢出現的視窗。
    6. 每個視窗定位後重套幾次，抓「開窗後會自己跳位置」的程式。

設計上「不啟動程式」（拋棄啟動器概念），只負責把出現的視窗搬到定位。
"""

import time


def _esc(s):
    """跳脫成 AHK v2 雙引號字串可安全嵌入的內容。"""
    s = str(s if s is not None else "")
    s = s.replace("`", "``")     # 反引號是 AHK 的跳脫字元，要先處理
    s = s.replace('"', '`"')     # 雙引號
    s = s.replace("\r", "").replace("\n", " ")
    return s


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _rule_literal(rule):
    return (
        'Map("exe", "{exe}", "title", "{title}", "monitor", {mon}, '
        '"mode", "{mode}", "w", {w}, "h", {h}, "x", {x}, "y", {y}, '
        '"enabled", {en})'
    ).format(
        exe=_esc(rule.get("exe", "")),
        title=_esc(rule.get("title_contains", "")),
        mon=_int(rule.get("monitor_index", 0)),
        mode=_esc(rule.get("mode", "maximized")),
        w=_int(rule.get("win_w", 0)),
        h=_int(rule.get("win_h", 0)),
        x=_int(rule.get("win_x", 0)),
        y=_int(rule.get("win_y", 0)),
        en=1 if rule.get("enabled", True) else 0,
    )


# 腳本內「會顯示給使用者」的文字（系統列提示與標頭註解），依語言切換。
# 程式邏輯與其餘註解維持中文（這是自動產生、不需手動編輯的成品）。
_AHK_STRINGS = {
    "zh": {
        "header": "自動產生的視窗定位腳本（請勿手動編輯）",
        "header2": "由 PinPanther GUI 產生，要修改請改 GUI 設定後重新產生並部署。",
        "no_rules": "（目前沒有任何規則）",
        "icon_tip_pre": "PinPanther 🐾 視窗定位中（",
        "icon_tip_post": " 條規則）",
        "tray_started": "視窗定位腳本已啟動",
    },
    "en": {
        "header": "Auto-generated window-positioning script (do not edit by hand)",
        "header2": "Produced by the PinPanther GUI; to change it, edit the GUI settings and re-deploy.",
        "no_rules": "(no rules yet)",
        "icon_tip_pre": "PinPanther 🐾 positioning windows (",
        "icon_tip_post": " rules)",
        "tray_started": "Window positioning script started",
    },
}


def generate_ahk_script(rules, retries=3, retry_ms=400, sweep_ms=15000, lang="zh"):
    """回傳完整的 AHK v2 腳本文字。lang 只影響系統列提示與標頭註解。"""
    s = _AHK_STRINGS.get(lang, _AHK_STRINGS["zh"])
    rule_lines = ",\n".join("    " + _rule_literal(r) for r in rules)
    if not rule_lines:
        rule_lines = "    ; " + s["no_rules"]
    ts = time.strftime("%Y-%m-%d %H:%M:%S")

    return AHK_TEMPLATE.format(
        timestamp=ts,
        rule_lines=rule_lines,
        retries=int(retries),
        retry_ms=int(retry_ms),
        sweep_ms=int(sweep_ms),
        header=s["header"],
        header2=s["header2"],
        icon_tip_pre=s["icon_tip_pre"],
        icon_tip_post=s["icon_tip_post"],
        tray_started=s["tray_started"],
    )


# 注意：模板裡 AHK 本身的大括號都要寫成 {{ }}，只有 .format 的欄位用單一 {} 。
AHK_TEMPLATE = r"""#Requires AutoHotkey v2.0
#SingleInstance Force
; ============================================================================
;  PinPanther 🐾 —— {header}
;  {header2}
;  {timestamp}
; ============================================================================

; Per-Monitor-V2 DPI 感知，座標才會與 MonitorGet 一致（Win10 1703+）
DllCall("SetThreadDpiAwarenessContext", "ptr", -4, "ptr")

; ---- 規則（由 PinPanther 設定產生） ----------------------------------------
global Rules := [
{rule_lines}
]

global RetryCount    := {retries}      ; 每個視窗額外重套次數（抓開窗後自己跳位的程式）
global RetryInterval := {retry_ms}     ; 重套間隔(ms)
global SweepWindow   := {sweep_ms}     ; 開機後持續補掃的毫秒數

global RetryJobs := Map()              ; hwnd -> {{rule, remaining}}
global Handled   := Map()              ; hwnd -> true（已處理過，避免反覆搬動使用者移過的視窗）

; ---- 螢幕清單：左→右、上→下排序，對應 GUI 的螢幕編號（0..N-1） -------------
GetMonitors() {{
    mons := []
    count := MonitorGetCount()
    primary := MonitorGetPrimary()
    Loop count {{
        i := A_Index
        MonitorGet(i, &L, &T, &R, &B)
        MonitorGetWorkArea(i, &wL, &wT, &wR, &wB)
        mons.Push(Map("L", L, "T", T, "R", R, "B", B,
            "wL", wL, "wT", wT, "wR", wR, "wB", wB,
            "primary", (i = primary)))
    }}
    ; 插入排序：先 Left 再 Top
    n := mons.Length
    Loop n - 1 {{
        i := A_Index + 1
        key := mons[i]
        j := i - 1
        while (j >= 1 && (mons[j]["L"] > key["L"]
                || (mons[j]["L"] = key["L"] && mons[j]["T"] > key["T"]))) {{
            mons[j + 1] := mons[j]
            j--
        }}
        mons[j + 1] := key
    }}
    return mons
}}

global Monitors := GetMonitors()

PrimaryIndex() {{
    global Monitors
    for i, m in Monitors
        if (m["primary"])
            return i
    return 1
}}

; ---- 判斷是否為「真正的應用程式主視窗」 ------------------------------------
IsRealWindow(hwnd) {{
    if !WinExist("ahk_id " hwnd)
        return false
    if !DllCall("IsWindowVisible", "ptr", hwnd)
        return false
    if DllCall("GetWindow", "ptr", hwnd, "uint", 4, "ptr")   ; GW_OWNER：有 owner 多為對話框
        return false
    if (WinGetExStyle("ahk_id " hwnd) & 0x80)                ; WS_EX_TOOLWINDOW
        return false
    cloaked := 0
    DllCall("dwmapi\DwmGetWindowAttribute", "ptr", hwnd, "uint", 14, "int*", &cloaked, "uint", 4)
    if (cloaked)                                             ; DWM cloaked（UWP 幽靈視窗）
        return false
    WinGetPos(&x, &y, &w, &h, "ahk_id " hwnd)
    if (w <= 0 || h <= 0)
        return false
    return true
}}

NormExe(name) {{
    name := StrLower(Trim(name))
    if (SubStr(name, -4) = ".exe")
        name := SubStr(name, 1, StrLen(name) - 4)
    return name
}}

MatchRule(hwnd) {{
    global Rules
    try
        exe := WinGetProcessName("ahk_id " hwnd)
    catch
        return 0
    title := ""
    try
        title := WinGetTitle("ahk_id " hwnd)
    exeN := NormExe(exe)
    titleL := StrLower(title)
    for i, rule in Rules {{
        if (!rule["enabled"])
            continue
        if (rule["exe"] = "")
            continue
        if (NormExe(rule["exe"]) != exeN)
            continue
        tc := StrLower(Trim(rule["title"]))
        if (tc != "" && !InStr(titleL, tc))
            continue
        return rule
    }}
    return 0
}}

PositionWindow(hwnd, rule) {{
    global Monitors
    idx := rule["monitor"] + 1          ; GUI 為 0-based
    if (idx < 1 || idx > Monitors.Length)
        idx := PrimaryIndex()
    m := Monitors[idx]
    mode := rule["mode"]
    try {{
        if (mode = "maximized") {{
            WinRestore("ahk_id " hwnd)
            ; 先把視窗移到目標螢幕，再最大化（最大化會貼齊它所在的那個螢幕）
            WinMove(m["wL"], m["wT"], (m["wR"] - m["wL"]) // 2, (m["wB"] - m["wT"]) // 2, "ahk_id " hwnd)
            WinMaximize("ahk_id " hwnd)
        }} else if (mode = "fullscreen") {{
            WinRestore("ahk_id " hwnd)
            WinSetStyle("-0xCF0000", "ahk_id " hwnd)   ; 移除 WS_OVERLAPPEDWINDOW（標題列/邊框）
            WinMove(m["L"], m["T"], m["R"] - m["L"], m["B"] - m["T"], "ahk_id " hwnd)
        }} else {{   ; windowed
            WinRestore("ahk_id " hwnd)
            cw := rule["w"], ch := rule["h"]
            if (cw > 0 && ch > 0) {{
                WinMove(m["wL"] + rule["x"], m["wT"] + rule["y"], cw, ch, "ahk_id " hwnd)
            }} else {{
                aw := m["wR"] - m["wL"], ah := m["wB"] - m["wT"]
                w := aw * 7 // 10, h := ah * 7 // 10
                WinMove(m["wL"] + (aw - w) // 2, m["wT"] + (ah - h) // 2, w, h, "ahk_id " hwnd)
            }}
        }}
    }}
}}

; ---- 處理單一視窗：比對規則並定位（含去重與重套排程） ----------------------
ApplyTo(hwnd) {{
    global Handled, RetryCount
    if Handled.Has(hwnd)
        return
    if !IsRealWindow(hwnd)
        return
    rule := MatchRule(hwnd)
    if (!rule)
        return
    Handled[hwnd] := true
    PositionWindow(hwnd, rule)
    if (RetryCount > 0)
        ScheduleRetry(hwnd, rule, RetryCount)
}}

ScheduleRetry(hwnd, rule, remaining) {{
    global RetryJobs, RetryInterval
    RetryJobs[hwnd] := {{rule: rule, remaining: remaining}}
    SetTimer(RetryTick.Bind(hwnd), -RetryInterval)
}}

RetryTick(hwnd) {{
    global RetryJobs, RetryInterval
    if !RetryJobs.Has(hwnd)
        return
    job := RetryJobs[hwnd]
    if !WinExist("ahk_id " hwnd) {{
        RetryJobs.Delete(hwnd)
        return
    }}
    PositionWindow(hwnd, job.rule)
    job.remaining -= 1
    if (job.remaining <= 0)
        RetryJobs.Delete(hwnd)
    else
        SetTimer(RetryTick.Bind(hwnd), -RetryInterval)
}}

; ---- 開機初掃：腳本啟動前就已存在的視窗 ------------------------------------
InitialSweep() {{
    for i, hwnd in WinGetList()
        ApplyTo(hwnd)
}}

; ---- 補掃：開機後一段時間內定期再掃，抓慢出現的視窗 ------------------------
global SweepDeadline := A_TickCount + SweepWindow
PeriodicSweep() {{
    global SweepDeadline
    if (A_TickCount > SweepDeadline) {{
        SetTimer(PeriodicSweep, 0)
        return
    }}
    for i, hwnd in WinGetList()
        ApplyTo(hwnd)
}}

; ---- Shell hook：新視窗一建立就立刻定位 ------------------------------------
ShellMessage(wParam, lParam, msg, hwnd) {{
    if (wParam = 1) {{       ; HSHELL_WINDOWCREATED
        h := lParam
        SetTimer(ApplyTo.Bind(h), -120)   ; 剛建立可能還沒就緒，稍等再套
    }}
}}

; ============================== 主程式 ======================================
DllCall("RegisterShellHookWindow", "ptr", A_ScriptHwnd)
shellMsg := DllCall("RegisterWindowMessageW", "str", "SHELLHOOK")
OnMessage(shellMsg, ShellMessage)

InitialSweep()
SetTimer(PeriodicSweep, 1000)

A_IconTip := "{icon_tip_pre}" Rules.Length "{icon_tip_post}"
TrayTip("PinPanther 🐾", "{tray_started}", 1)
"""
