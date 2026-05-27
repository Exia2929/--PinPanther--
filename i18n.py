# -*- coding: utf-8 -*-
"""
PinPanther 🐾 —— 介面文字多語系（中文 / English）
=================================================

集中管理所有「會顯示給使用者」的字串。每個 key 對應 zh / en 兩種語言。
用法：
    import i18n
    i18n.set_lang("en")          # 切換語言（"zh" / "en"）
    i18n.t("btn_add")            # 取得目前語言的文字
    i18n.t("confirm_delete", exe="discord.exe")   # 含參數的字串用具名欄位
程式碼註解維持中文（開發者面向）；此檔只負責「使用者可見」的文字。
"""

_LANG = "zh"
LANGS = ("zh", "en")

# 語言代碼 ↔ 下拉選單顯示名稱
LANG_DISPLAY = {"zh": "中文", "en": "English"}


def set_lang(lang):
    global _LANG
    _LANG = lang if lang in LANGS else "zh"
    return _LANG


def get_lang():
    return _LANG


def t(key, **kw):
    """取出目前語言的字串；找不到語言時退回中文，再退回 key 本身。"""
    entry = TR.get(key)
    if entry is None:
        return key
    s = entry.get(_LANG) or entry.get("zh") or key
    if kw:
        try:
            s = s.format(**kw)
        except (KeyError, IndexError, ValueError):
            pass
    return s


_MODES = ("windowed", "maximized", "fullscreen")


def mode_label(mode):
    """開啟模式（windowed/maximized/fullscreen）轉成目前語言的標籤。"""
    if mode in _MODES:
        return t("mode_" + mode)
    return mode


# ===========================================================================
#  翻譯表
# ===========================================================================
TR = {
    # ---- 應用程式 / 系統列 ----
    "app_title": {
        "zh": "PinPanther 🐾 — 多螢幕視窗自動定位",
        "en": "PinPanther 🐾 — Multi-Monitor Window Auto-Positioning",
    },
    "tray_tooltip": {
        "zh": "PinPanther — 多螢幕視窗自動定位",
        "en": "PinPanther — Multi-Monitor Window Auto-Positioning",
    },

    # ---- 開啟模式 ----
    "mode_windowed": {"zh": "視窗", "en": "Windowed"},
    "mode_maximized": {"zh": "最大化", "en": "Maximized"},
    "mode_fullscreen": {"zh": "全螢幕(無邊框)", "en": "Fullscreen (borderless)"},

    # ---- 螢幕標籤 ----
    "monitor_label": {
        "zh": "螢幕 {idx} — {w}x{h} @ ({x},{y}){tag}",
        "en": "Monitor {idx} — {w}x{h} @ ({x},{y}){tag}",
    },
    "primary_tag": {"zh": " [主螢幕]", "en": " [Primary]"},
    "monitor_short": {"zh": "螢幕 {idx}", "en": "Monitor {idx}"},
    "monitor_unknown": {"zh": "螢幕?", "en": "Monitor ?"},

    # ---- apply_rule ----
    "log_monitor_missing": {
        "zh": "⚠ 螢幕 {idx} 不存在，改用主螢幕 {prim}",
        "en": "⚠ Monitor {idx} not found; using primary monitor {prim}",
    },
    "log_apply_failed": {
        "zh": "⚠ 套用失敗: {e}",
        "en": "⚠ Apply failed: {e}",
    },

    # ---- Watcher ----
    "log_watch_started": {
        "zh": "👀 監控已啟動，等待新視窗開啟…",
        "en": "👀 Monitoring started; waiting for new windows…",
    },
    "log_watch_loop_err": {
        "zh": "⚠ 監控迴圈錯誤: {e}",
        "en": "⚠ Monitor loop error: {e}",
    },
    "log_watch_stopped": {
        "zh": "⏹ 監控已停止。",
        "en": "⏹ Monitoring stopped.",
    },
    "log_applied_window": {
        "zh": "✔ {exe} → {monitor}｜{mode}｜{title}",
        "en": "✔ {exe} → {monitor} | {mode} | {title}",
    },

    # ---- 系統列選單 ----
    "tray_show": {"zh": "顯示主視窗", "en": "Show main window"},
    "tray_toggle_watch": {"zh": "開始 / 停止監控", "en": "Start / Stop monitoring"},
    "tray_quit": {"zh": "結束程式", "en": "Quit"},

    # ---- 設定檔 ----
    "err_save_title": {"zh": "儲存失敗", "en": "Save failed"},
    "err_save_body": {
        "zh": "無法寫入設定檔：\n{e}",
        "en": "Could not write the config file:\n{e}",
    },

    # ---- 規則編輯對話框 ----
    "dlg_edit_title": {"zh": "編輯規則", "en": "Edit rule"},
    "dlg_add_title": {"zh": "新增規則", "en": "Add rule"},
    "lbl_exe": {
        "zh": "執行檔名稱 (例如 notepad.exe)：",
        "en": "Executable name (e.g. notepad.exe):",
    },
    "lbl_title_contains": {
        "zh": "視窗標題包含 (選填，可留空)：",
        "en": "Window title contains (optional):",
    },
    "lbl_which_monitor": {"zh": "開啟在哪個螢幕：", "en": "Open on which monitor:"},
    "lbl_mode": {"zh": "開啟模式：", "en": "Open mode:"},
    "frm_custom_size": {
        "zh": "視窗模式自訂大小／位置（留空＝自動置中 70%）",
        "en": "Windowed custom size / position (blank = auto-center 70%)",
    },
    "lbl_w": {"zh": "寬", "en": "W"},
    "lbl_h": {"zh": "高", "en": "H"},
    "lbl_rel_x": {"zh": "相對X", "en": "Rel X"},
    "lbl_rel_y": {"zh": "相對Y", "en": "Rel Y"},
    "hint_rel": {
        "zh": "（相對X/Y 為距離目標螢幕工作區左上角的像素，可在主畫面用「擷取目前視窗」自動填入）",
        "en": "(Rel X/Y = pixels from the target monitor's work-area top-left; "
              "use \"Capture selected rule's size/position\" on the main screen to auto-fill)",
    },
    "chk_enable_rule": {"zh": "啟用此規則", "en": "Enable this rule"},
    "btn_ok": {"zh": "確定", "en": "OK"},
    "btn_cancel": {"zh": "取消", "en": "Cancel"},
    "warn_missing_title": {"zh": "缺少資料", "en": "Missing data"},
    "warn_missing_exe": {
        "zh": "請輸入執行檔名稱。",
        "en": "Please enter an executable name.",
    },

    # ---- 共用 ----
    "info_title": {"zh": "提示", "en": "Note"},
    "select_rule_first": {
        "zh": "請先選擇一條規則。",
        "en": "Please select a rule first.",
    },
    "confirm_title": {"zh": "確認", "en": "Confirm"},
    "confirm_delete": {
        "zh": "確定刪除規則「{exe}」？",
        "en": "Delete the rule \"{exe}\"?",
    },

    # ---- 頂部螢幕資訊列 ----
    "btn_rescan": {"zh": "重新偵測螢幕", "en": "Re-detect monitors"},
    "monitors_detected": {
        "zh": "偵測到 {n} 個螢幕（主螢幕 = 螢幕 {prim}）",
        "en": "Detected {n} monitor(s) (primary = monitor {prim})",
    },
    "log_rescanned": {
        "zh": "已重新偵測螢幕：共 {n} 個",
        "en": "Monitors re-detected: {n} total",
    },

    # ---- 步驟 ① 設定規則 ----
    "step1_title": {
        "zh": "① 設定規則　—　每個程式要去哪個螢幕、用什麼模式開啟",
        "en": "① Configure rules — which monitor & mode each app opens with",
    },
    "col_enabled": {"zh": "啟用", "en": "On"},
    "col_exe": {"zh": "執行檔", "en": "Executable"},
    "col_title": {"zh": "標題包含", "en": "Title contains"},
    "col_monitor": {"zh": "螢幕", "en": "Monitor"},
    "col_mode": {"zh": "模式", "en": "Mode"},
    "btn_add": {"zh": "＋ 新增", "en": "＋ Add"},
    "btn_edit": {"zh": "編輯", "en": "Edit"},
    "btn_delete": {"zh": "刪除", "en": "Delete"},
    "btn_toggle": {"zh": "啟用/停用", "en": "Enable/Disable"},
    "btn_capture_layout": {
        "zh": "📸 一鍵擷取目前布局",
        "en": "📸 Capture current layout",
    },
    "btn_capture_size": {
        "zh": "擷取選取規則的大小/位置",
        "en": "Capture selected rule's size/position",
    },

    # ---- 步驟 ② 測試規則 ----
    "step2_title": {
        "zh": "② 測試規則　—　不影響開機，先確認會不會跑到定位",
        "en": "② Test rules — no effect on startup; verify positioning first",
    },
    "btn_apply_now": {
        "zh": "套用到目前開啟的視窗",
        "en": "Apply to currently open windows",
    },
    "btn_start_watch": {"zh": "▶ 開始預覽監控", "en": "▶ Start preview monitoring"},
    "btn_stop_watch": {"zh": "■ 停止預覽監控", "en": "■ Stop preview monitoring"},
    "status_idle": {"zh": "● 未監控", "en": "● Not monitoring"},
    "status_watching": {"zh": "● 預覽監控中", "en": "● Monitoring (preview)"},
    "lbl_interval": {"zh": "掃描間隔(秒)：", "en": "Scan interval (s):"},
    "log_applied_now": {
        "zh": "已套用到目前視窗，共處理 {count} 個。",
        "en": "Applied to current windows; {count} processed.",
    },

    # ---- 日誌區 ----
    "log_frame": {"zh": "日誌", "en": "Log"},

    # ---- 步驟 ③ 部署到開機 ----
    "step3_title": {
        "zh": "③ 部署到開機　—　產生 AHK 腳本並放進開機啟動",
        "en": "③ Deploy to startup — generate the AHK script and add it to startup",
    },
    "btn_install_ahk": {"zh": "安裝 AutoHotkey v2", "en": "Install AutoHotkey v2"},
    "btn_reinstall_ahk": {
        "zh": "重新安裝 AutoHotkey v2",
        "en": "Reinstall AutoHotkey v2",
    },
    "btn_deploy": {
        "zh": "✦ 產生並部署到開機啟動",
        "en": "✦ Generate & deploy to startup",
    },
    "btn_run_once": {"zh": "立即測試執行", "en": "Test-run now"},
    "btn_undeploy": {"zh": "移除開機啟動", "en": "Remove from startup"},
    "btn_open_folder": {"zh": "開啟腳本資料夾", "en": "Open script folder"},

    # ---- AHK 狀態列 ----
    "ahk_installed": {"zh": "✔ 已安裝（{path}）", "en": "✔ Installed ({path})"},
    "ahk_not_found": {
        "zh": "✘ 未偵測到，請先按左下「安裝 AutoHotkey v2」",
        "en": "✘ Not detected; click \"Install AutoHotkey v2\" (below-left) first",
    },
    "script_generated": {"zh": "已產生", "en": "generated"},
    "script_not_generated": {"zh": "尚未產生", "en": "not generated"},
    "deploy_yes": {"zh": "✔ 已部署，開機生效", "en": "✔ Deployed; active at startup"},
    "deploy_no": {"zh": "✘ 尚未部署", "en": "✘ Not deployed"},
    "ahk_status_fmt": {
        "zh": "AutoHotkey：{ahk}\n腳本：{script}　｜　開機部署：{deploy}",
        "en": "AutoHotkey: {ahk}\nScript: {script}  |  Startup deploy: {deploy}",
    },

    # ---- 安裝 AutoHotkey ----
    "installed_title": {"zh": "已安裝", "en": "Already installed"},
    "installed_confirm": {
        "zh": "偵測到已安裝 AutoHotkey v2，仍要重新安裝/更新嗎？",
        "en": "AutoHotkey v2 is already installed. Reinstall/update anyway?",
    },
    "no_winget_title": {"zh": "找不到 winget", "en": "winget not found"},
    "no_winget_body": {
        "zh": "系統沒有 winget，無法自動安裝。\n"
              "是否改用瀏覽器開啟 AutoHotkey 官方下載頁，手動安裝 v2？",
        "en": "winget is not available, so automatic install isn't possible.\n"
              "Open the official AutoHotkey download page to install v2 manually?",
    },
    "log_installing": {
        "zh": "⏳ 用 winget 安裝 AutoHotkey v2…請在彈出的視窗（含 UAC）完成安裝。",
        "en": "⏳ Installing AutoHotkey v2 via winget… finish it in the pop-up window (incl. UAC).",
    },
    "log_winget_failed": {
        "zh": "⚠ 啟動 winget 失敗：{e}",
        "en": "⚠ Failed to start winget: {e}",
    },
    "log_ahk_detected": {
        "zh": "✔ 已偵測到 AutoHotkey，安裝完成。",
        "en": "✔ AutoHotkey detected; installation complete.",
    },
    "log_ahk_timeout": {
        "zh": "（3 分鐘內仍未偵測到；若安裝視窗還開著請等它跑完，或安裝完成後重開本程式。）",
        "en": "(Not detected within 3 minutes; if the installer is still open, wait for it "
              "to finish, or restart this app after installing.)",
    },

    # ---- 部署 ----
    "ahk_missing_title": {"zh": "尚未安裝 AutoHotkey", "en": "AutoHotkey not installed"},
    "ahk_missing_body": {
        "zh": "偵測不到 AutoHotkey v2，無法部署。\n要現在安裝嗎？",
        "en": "AutoHotkey v2 not detected; cannot deploy.\nInstall it now?",
    },
    "no_rules_title": {"zh": "沒有規則", "en": "No rules"},
    "no_rules_body": {
        "zh": "目前沒有任何規則，仍要部署一支空腳本嗎？",
        "en": "There are no rules. Deploy an empty script anyway?",
    },
    "deploy_failed_title": {"zh": "部署失敗", "en": "Deploy failed"},
    "deploy_shortcut_failed": {
        "zh": "建立開機捷徑失敗：\n{err}",
        "en": "Failed to create the startup shortcut:\n{err}",
    },
    "log_deployed": {
        "zh": "✔ 已產生 {name} 並部署到開機啟動。",
        "en": "✔ Generated {name} and deployed it to startup.",
    },
    "deploy_done_title": {"zh": "部署完成", "en": "Deployment complete"},
    "deploy_done_body": {
        "zh": "已產生腳本：\n{script}\n\n"
              "並在開機啟動資料夾建立捷徑：\n{shortcut}\n\n"
              "下次開機腳本就會自動把符合規則的視窗定位。\n"
              "各程式『自己的開機自啟動』維持原樣即可——它們的視窗出現時腳本就會接手定位。\n\n"
              "想立刻看效果，按「立即測試執行」。",
        "en": "Script generated:\n{script}\n\n"
              "Shortcut created in the startup folder:\n{shortcut}\n\n"
              "On next boot the script will auto-position windows that match your rules.\n"
              "Leave each app's own \"start at login\" as-is — the script takes over "
              "positioning when their windows appear.\n\n"
              "To see it right away, click \"Test-run now\".",
    },
    "undeploy_failed_title": {"zh": "移除失敗", "en": "Removal failed"},
    "log_undeployed": {
        "zh": "已從開機啟動移除（腳本檔仍保留在專案資料夾）。",
        "en": "Removed from startup (the script file stays in the project folder).",
    },
    "run_ahk_not_found_title": {"zh": "找不到 AutoHotkey", "en": "AutoHotkey not found"},
    "run_ahk_not_found_body": {
        "zh": "偵測不到 AutoHotkey v2。",
        "en": "AutoHotkey v2 not detected.",
    },
    "run_failed_title": {"zh": "執行失敗", "en": "Run failed"},
    "log_run_once": {
        "zh": "▶ 已用最新規則啟動 AHK 腳本（常駐於系統列，右鍵圖示可結束）。",
        "en": "▶ Launched the AHK script with the latest rules "
              "(runs in the tray; right-click the icon to quit).",
    },
    "log_open_folder_failed": {
        "zh": "⚠ 開啟資料夾失敗：{e}",
        "en": "⚠ Failed to open folder: {e}",
    },

    # ---- 一鍵擷取布局 ----
    "no_monitor_title": {"zh": "沒有螢幕", "en": "No monitors"},
    "no_monitor_body": {"zh": "偵測不到螢幕。", "en": "No monitors detected."},
    "no_window_title": {"zh": "沒有視窗", "en": "No windows"},
    "no_window_body": {
        "zh": "目前各螢幕上找不到可擷取的前景視窗。",
        "en": "No foreground window to capture on any monitor.",
    },
    "capture_line": {
        "zh": "  螢幕{idx}：{exe}（{mode}）{ttl}",
        "en": "  Monitor {idx}: {exe} ({mode}){ttl}",
    },
    "capture_title_part": {
        "zh": "｜標題含「{title}」",
        "en": " | title contains \"{title}\"",
    },
    "capture_dlg_title": {"zh": "擷取目前布局", "en": "Capture current layout"},
    "capture_dlg_body": {
        "zh": "已擷取目前各螢幕的前景視窗：\n\n{lines}\n\n"
              "要如何套用？\n"
              "　是　＝取代現有全部規則\n"
              "　否　＝加入到現有規則\n"
              "取消＝不動作",
        "en": "Captured the foreground window on each monitor:\n\n{lines}\n\n"
              "How do you want to apply them?\n"
              "  Yes  = replace all existing rules\n"
              "  No   = add to existing rules\n"
              "Cancel = do nothing",
    },
    "capture_mode_replace": {"zh": "取代", "en": "replaced all"},
    "capture_mode_add": {
        "zh": "加入 {added} 條（略過重複）",
        "en": "added {added} (duplicates skipped)",
    },
    "log_capture": {
        "zh": "✔ 一鍵擷取布局：共 {count} 個視窗，{mode}。",
        "en": "✔ Captured layout: {count} window(s), {mode}.",
    },

    # ---- 擷取大小/位置 ----
    "capture_no_window_title": {"zh": "找不到視窗", "en": "Window not found"},
    "capture_no_window_body": {
        "zh": "目前沒有開啟符合「{exe}」的視窗，無法擷取。\n"
              "請先把該程式開到你想要的大小與位置，再按一次。",
        "en": "No open window matching \"{exe}\" was found, so there's nothing to capture.\n"
              "Open that app at the size/position you want, then click again.",
    },
    "log_captured_size": {
        "zh": "已擷取 {exe}：大小 {w}x{h}，相對螢幕 {idx} 位置 ({x},{y})",
        "en": "Captured {exe}: size {w}x{h}, position ({x},{y}) relative to monitor {idx}",
    },
    "captured_title": {"zh": "已擷取", "en": "Captured"},
    "captured_body": {
        "zh": "大小：{w} x {h}\n相對位置：({x}, {y})\n\n"
              "提示：該規則模式需設為「視窗」才會套用此大小。",
        "en": "Size: {w} x {h}\nRelative position: ({x}, {y})\n\n"
              "Note: the rule's mode must be \"Windowed\" for this size to apply.",
    },

    # ---- 系統列選項列 ----
    "btn_hide_tray": {"zh": "🗕 縮到系統列", "en": "🗕 Minimize to tray"},
    "chk_tray_close": {"zh": "關閉時縮到系統列", "en": "On close, minimize to tray"},
    "chk_tray_min": {"zh": "最小化時縮到系統列", "en": "On minimize, hide to tray"},
    "log_hidden_tray": {
        "zh": "已縮到系統列；點擊系統列圖示可叫回視窗。",
        "en": "Minimized to tray; click the tray icon to restore.",
    },
    "log_tray_failed": {
        "zh": "⚠ 系統列圖示建立失敗，關閉/最小化將不會縮到系統列。",
        "en": "⚠ Failed to create the tray icon; close/minimize won't hide to tray.",
    },
}
