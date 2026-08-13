# Android Perf Monitor (Android 效能實時監控工具)

一個基於 Python (PyQt5) 與 Android ADB 介面的高效能實時監控 GUI 工具。本系統可即時採集並視覺化 Android 裝置的多項關鍵效能指標，包含 FPS (每秒幀率)、Jank/Big Jank (卡頓統計)、CPU 各核心使用率與頻率、GPU 使用率、電池溫度、記憶體佔用以及即時功耗 (電壓與電流)。

---

## 目錄

- [系統特色](#系統特色)
- [前置環境需求與設定](#前置環境需求與設定)
  - [1. 安裝與設定 ADB (Android Debug Bridge)](#1-安裝與設定-adb-android-debug-bridge)
  - [2. Android 手機端開發者選項設定](#2-android-手機端開發者選項設定)
  - [3. 安裝 Python 執行環境與相依套件](#3-安裝-python-執行環境與相依套件)
- [專案結構說明](#專案結構說明)
- [核心模組與功能解析](#核心模組與功能解析)
- [使用說明](#使用說明)
  - [USB 監控模式](#usb-監控模式)
  - [WiFi 無線 ADB 監控模式](#wifi-無線-adb-監控模式)
  - [導出 CSV 數據](#導出-csv-數據)
- [常問問題與故障排除 (Troubleshooting)](#常問問題與故障排除-troubleshooting)

---

## 系統特色

1. 多維度實時效能圖表：
   - FPS & Jank：實時計算 SurfaceFlinger 的 VSync 數據，精確判斷 Jank (微卡頓) 與 Big Jank (嚴重卡頓)。
   - CPU 核心分析：獨立呈現 8 個 CPU 核心的使用率 (%) 與運作頻率 (MHz)。
   - GPU & 記憶體：讀取 /sys/class/kgsl/kgsl-3d0/gpubusy 計算 GPU 負載，並監控系統 RAM 使用率。
   - 電池與功耗：實時讀取電池溫度 (°C)，並搭配背景 APK 服務透過 HTTP 介面回傳精確的功耗 (mW)、電壓 (V) 與電流 (mA)。
2. 多執行緒架構 (Multi-threading)：
   - 採集資料與 UI 渲染分離，確保圖表滑順不凍結。
   - 資料採集 (500ms) 與數據日誌紀錄 (1.0s) 精確同步。
3. 無線監控支援：
   - 支援一鍵開啟 TCP/IP 5555 埠，實現無線 WiFi ADB 連線監控。
4. 數據匯出功能：
   - 支援將監控過全程的數據導出為 UTF-8-SIG 編碼的 CSV 檔案，方便後續 Excel / Python 分析。

---

## 前置環境需求與設定

在執行本程式之前，請務必先完成以下環境準備。特別是 ADB 環境必須提前下載並配置完畢。

### 1. 安裝與設定 ADB (Android Debug Bridge)

ADB 是本工具與 Android 裝置溝通的核心橋樑。

#### Step 1: 下載 Platform Tools
- Windows / Mac / Linux：請至 Google 官方開發者網站下載最新版的 SDK Platform-Tools (https://developer.android.com/tools/releases/platform-tools)。

#### Step 2: 解壓縮與系統環境變數設定 (PATH)
1. 將下載的 platform-tools 解壓縮至固定的資料夾（例如：C:\platform-tools）。
2. 新增至環境變數 (Windows)：
   - 按下 Win + R 輸入 sysdm.cpl 開啟系統屬性。
   - 切換至「進階」頁籤，點擊「環境變數」。
   - 在「系統變數」區域中找到 Path 變數，點擊「編輯」。
   - 點擊「新增」，填入 ADB 的解壓路徑（例如 C:\platform-tools）。
   - 一路點擊「確定」保存設定。
3. 驗證 ADB 是否安裝成功：
   - 開啟新的命令提示字元 (cmd) 或 Terminal，輸入：
     adb version
   - 若能正確顯示版本號（如 Android Debug Bridge version 1.0.41），表示環境變數設定成功。

自訂 ADB 路徑說明：
本專案模組支援讀取環境變數 ADB_EXEC_PATH。若未設定 PATH，您亦可在執行程式前設定環境變數：
set ADB_EXEC_PATH=C:\path\to\your\adb.exe

---

### 2. Android 手機端開發者選項設定

1. 開啟開發者人員選項：
   - 前往手機「設定」->「關於手機」。
   - 連續點擊「版本號碼 (Build Number)」7 次，直到顯示「您已成為開發人員」。
2. 啟用 USB 偵錯：
   - 前往手機「設定」->「系統」->「開發人員選項」。
   - 開啟 「USB 偵錯 (USB Debugging)」。
   - (部分品牌如小米/OPPO需另外開啟「USB 偵錯 (安全設定)」，允許傳送模擬輸入或安裝 APK)。
3. 首次連線授權：
   - 將手機透過 USB 傳輸線連接至電腦。
   - 在電腦 CMD 輸入 adb devices。
   - 此時手機螢幕會彈出 「允許 USB 偵錯嗎？」 的授權提示，請勾選「一律允許透過這台電腦進行授權」並點擊 「允許」。

---

### 3. 安裝 Python 執行環境與相依套件

本工具基於 Python 3.8+ 開發，依賴 PyQt5 與 QtChart 模組進行 GUI 渲染。

#### 安裝依賴套件

pip install PyQt5 PyQtChart requests

---

## 專案結構說明

請確保您的專案目錄包含以下檔案結構：

.
├── main.py               # 主程式 (GUI 介面與繪圖邏輯，包含 MonitorWindow 與 DataThread)
├── per.py                # ADB 底層溝通模組 (負責 dumpsys 解析、sysfs 讀取與 APK 服務交互)
├── app-debug.apk         # 電池與功耗採集服務 APK (自動安裝至手機)
└── README.md             # 本說明文件

---

## 核心模組與功能解析

### 1. 電池功耗服務模組 (com.example.batteryapi)
- 程式啟動監控時，per.py 會自動將目錄下的 app-debug.apk 安裝至手機，並啟動前台服務 BatteryService。
- 該服務會在手機本地端啟動 HTTP Server (Port 8080)，提供 /battery Endpoint 回傳精確的電壓、電流與功耗 JSON 資料。

### 2. 卡頓分析演算法 (Jank & Big Jank)
- 透過 dumpsys SurfaceFlinger --latency 獲取 VSync triplet 時間戳記。
- 當單一幀渲染時間超過前三幀平均值的 2 倍且大於 83.33ms 時記為 Jank。
- 當單一幀渲染時間大於 125ms 時記為 Big Jank。

---

## 使用說明

### USB 監控模式

1. 使用 USB 傳輸線連接 Android 手機與電腦。
2. 確認 adb devices 能看到設備狀態為 device。
3. 執行主程式：
   python main.py
4. 在 GUI 介面上方點擊 「開始監控」：
   - 系統會自動獲取當前手機前景應用的 Package Name。
   - 自動將背景功耗 APK (app-debug.apk) 推送安裝至手機並啟動服務。
   - 視窗將開始實時繪製 FPS、溫度、RAM、GPU、功耗與 CPU 8 核心折線圖。
5. 點擊 「停止」 可暫停資料監控。

---

## WiFi 無線 ADB 監控模式

若需要脫離 USB 線材進行高自由度的效能測試（如手遊測試）：

1. 先將手機以 USB 連接至電腦。
2. 點擊 GUI 介面右上方的 「開啟WiFi ADB」 按鈕。
3. 程式會自動執行以下指令：
   - 讀取手機 wlan0 的 IP 位址（如 192.168.1.100）。
   - 切換 ADB 至 TCP/IP 模式：adb tcpip 5555。
   - 自動連線：adb connect 192.168.1.100:5555。
4. 當介面提示成功後，即可拔除 USB 傳輸線，全程透過無線網絡進行效能資料採集。

---

## 導出 CSV 數據

在監控結束後，點擊 GUI 介面的 「導出CSV」 按鈕：
- 選擇儲存路徑與檔名。
- 匯出的 CSV 將包含以下完整欄位：
  - Time：時間戳記
  - FPS, Temp, Mem, GPU(%)
  - Power(mW), Voltage(V), Current(mA)
  - Jank, Big Jank
  - CPU0% ~ CPU7% (8 個核心使用率)
  - Core0(MHz) ~ Core7(MHz) (8 個核心運作頻率)

---

## 常問問題與故障排除 (Troubleshooting)

| 問題現象 | 判斷原因 | 解決方法 |
| :--- | :--- | :--- |
| 主控台顯示 [Error] 找不到 ADB 可執行文件 | 未將 ADB 加入 PATH 或未設定 ADB_EXEC_PATH。 | 請參考 [安裝與設定 ADB] 步驟，重新將 ADB 加入系統環境變數，或重開 CMD/IDE。 |
| GUI 功耗欄位顯示 N/A 或 0 | 手機防火牆阻擋了 8080 埠，或 APK 服務未成功啟動。 | 1. 確認電腦與手機在同一網域下。<br>2. 檢查手機上是否已有 BatteryAPI 應用程式並允許相關權限。 |
| FPS 顯示 -1 或不更新 | 當前前景 App 未繪製 SurfaceView 或 Layer 名稱匹配失敗。 | 開啟一個具體畫面的 App (如遊戲或影片播放器)，讓 SurfaceFlinger 產生圖層數據。 |
| WiFi ADB 連線失敗 | 手機與電腦未連接在同一個 Wi-Fi 路由器下。 | 請確認手機與電腦位於相同區域網路 (LAN) 段。 |
| ImportError: No module named 'PyQt5' | Python 環境缺少 PyQt5 依賴套件。 | 執行 pip install PyQt5 PyQtChart 進行補齊。 |
