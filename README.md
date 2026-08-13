# Android Perf Monitor (Android 效能實時監控工具)

Language / 語言切換：  
[ English ](#english) | [ 繁體中文 ](#繁體中文)

---

<a name="english"></a>
## English

A high-performance real-time GUI monitoring tool built with Python (PyQt5) and the Android ADB interface. This system captures and visualizes multiple key performance metrics from Android devices in real time, including FPS (Frames Per Second), Jank/Big Jank statistics, individual CPU core utilization and frequencies, GPU usage, battery temperature, RAM usage, and real-time power consumption (voltage & current).

### Table of Contents
- [Key Features](#key-features-en)
- [Prerequisites & Environment Setup](#prerequisites--environment-setup-en)
  - [1. Install and Configure ADB (Android Debug Bridge)](#1-install-and-configure-adb-android-debug-bridge-en)
  - [2. Android Device Developer Options Setup](#2-android-device-developer-options-setup-en)
  - [3. Install Python Environment & Dependencies](#3-install-python-environment--dependencies-en)
- [Project Structure](#project-structure-en)
- [Platform Support & Metric Limitations](#platform-support-en)
- [Core Modules & Architecture](#core-modules--architecture-en)
- [Usage Instructions](#usage-instructions-en)
  - [USB Monitoring Mode](#usb-monitoring-mode-en)
  - [WiFi Wireless ADB Monitoring Mode](#wifi-wireless-adb-monitoring-mode-en)
  - [Exporting CSV Data](#exporting-csv-data-en)
- [Troubleshooting & FAQ](#troubleshooting--faq-en)

---

> **⚠️ IMPORTANT NOTICE (Power Consumption Data Collection):**  
> You **MUST** place the bundled **`app-debug.apk`** file in the **SAME directory** as `main.py` and `per.py`. Without this APK file, the system cannot automatically push and launch the background measuring service on the phone, resulting in **N/A or 0 for real-time power consumption (voltage and current) readings**.

<a name="key-features-en"></a>
### Key Features
1. **Multi-Dimensional Real-time Charts:**
   - **FPS & Jank:** Real-time calculation of SurfaceFlinger VSync data to accurately identify Jank (minor stutters) and Big Jank (severe stutters).
   - **CPU Core Analysis:** Independently displays usage percentage (%) and frequency (MHz) for up to 8 CPU cores.
   - **GPU & Memory:** Reads `/sys/class/kgsl/kgsl-3d0/gpubusy` to calculate GPU load and monitors system RAM usage.
   - **Battery & Power Consumption:** Reads battery temperature (°C) in real time and works with a background APK service to report precise power consumption (mW), voltage (V), and current (mA) via an HTTP interface.
2. **Multi-threaded Architecture:**
   - Data collection is separated from UI rendering to ensure fluid charts without freezing.
   - Precise synchronization between data sampling (500ms) and data logging (1.0s).
3. **Wireless Monitoring Support:**
   - Supports one-click enabling of TCP/IP port 5555 for wireless WiFi ADB monitoring.
4. **Data Exporting:**
   - Supports exporting full session monitoring logs to UTF-8-SIG encoded CSV files for easy post-analysis in Excel or Python.

<a name="prerequisites--environment-setup-en"></a>
### Prerequisites & Environment Setup

Please ensure the following environment setup is completed before running the application.

<a name="1-install-and-configure-adb-android-debug-bridge-en"></a>
#### 1. Install and Configure ADB (Android Debug Bridge)
ADB is the core bridge for communicating with Android devices.

- **Step 1: Download Platform Tools**
  Download the latest SDK Platform-Tools from the official Google Developers site (https://developer.android.com/tools/releases/platform-tools).
- **Step 2: Extract and Set System PATH Environment Variable**
  1. Extract the downloaded `platform-tools` zip file to a fixed folder (e.g., `C:\platform-tools`).
  2. Add to Environment Variables (Windows):
     - Press `Win + R`, type `sysdm.cpl`, and press Enter to open System Properties.
     - Switch to the "Advanced" tab and click "Environment Variables".
     - Under "System variables", find `Path` and click "Edit".
     - Click "New" and paste the ADB extraction path (e.g., `C:\platform-tools`).
     - Click "OK" to save all settings.
  3. Verify ADB Installation:
     Open a new Command Prompt (`cmd`) or Terminal and type:
     ```bash
     adb version
     ```
     If configured correctly, it will display the ADB version (e.g., `Android Debug Bridge version 1.0.41`).

*Custom ADB Path Setting:*  
The module supports reading the `ADB_EXEC_PATH` environment variable. If you prefer not to modify PATH, you can set it before execution:
```cmd
set ADB_EXEC_PATH=C:\path\to\your\adb.exe
```

<a name="2-android-device-developer-options-setup-en"></a>
#### 2. Android Device Developer Options Setup
1. **Enable Developer Options:** Go to **Settings -> About Phone**. Tap **Build Number** 7 times continuously until you see "You are now a developer!".
2. **Enable USB Debugging:** Go to **Settings -> System -> Developer Options**. Enable **USB Debugging**. *(For certain brands like Xiaomi/OPPO, also enable "USB Debugging (Security Settings)" to allow mock inputs and APK installation).*
3. **Authorize Connection:** Connect your phone to your computer via USB cable. Run `adb devices` in your command prompt. A prompt "Allow USB debugging?" will appear on your phone screen. Check "Always allow from this computer" and tap **Allow**.

<a name="3-install-python-environment--dependencies-en"></a>
#### 3. Install Python Environment & Dependencies
This tool requires Python 3.8+ and relies on PyQt5 and QtChart modules for GUI rendering.

```bash
pip install PyQt5 PyQtChart requests
```

<a name="project-structure-en"></a>
### Project Structure

Ensure your project folder contains the following files. **Make sure `app-debug.apk` is placed in the same folder**:

```text
.
├── main.py               # Main GUI application & chart plotting logic (MonitorWindow, DataThread)
├── per.py                # ADB underlying communication module (dumpsys parser, sysfs reader, APK service client)
├── app-debug.apk         # [REQUIRED] Battery & power collection service APK (must be in the same folder as main.py)
└── README.md             # Project documentation
```

<a name="platform-support-en"></a>
### Platform Support & Metric Limitations

| Metric | Support | Notes |
| :--- | :--- | :--- |
| **FPS** | **Android 12+ only** | Calculated from SurfaceFlinger VSync timing data. Android 11 and below are treated as unsupported. |
| **GPU Usage** | **Qualcomm Snapdragon only** | Requires the Qualcomm KGSL interface, typically `/sys/class/kgsl/kgsl-3d0/gpubusy`. |
| **Google Pixel GPU Usage** | **Not supported** | Pixel devices are explicitly excluded from GPU usage collection by this project. GPU is shown as `N/A`/unavailable. |
| **CPU Usage/Frequency** | Device-dependent | Availability depends on the CPU sysfs interfaces exposed by the Android device. |
| **RAM / Temperature** | Device-dependent | Depends on the Android device and exposed system interfaces. |
| **Power / Voltage / Current** | Requires `app-debug.apk` | Collected through the bundled BatteryService APK. |

**Important implementation rule:** the application should detect Android version, SoC/vendor, and GPU interface availability before starting metric collection. Unsupported metrics must be displayed as `N/A`/unavailable rather than being interpreted as `0%`.

<a name="core-modules--architecture-en"></a>
### Core Modules & Architecture

#### 1. Battery & Power Service Module (com.example.batteryapi)
- When monitoring starts, `per.py` automatically checks for `app-debug.apk` in the **same directory**, installs it to the device, and starts the foreground service `BatteryService`.
- **Note:** If `app-debug.apk` is missing from the directory, the power module will fail to start, and Power (mW), Voltage (V), and Current (mA) will be unavailable in both the GUI and exported CSV.
- The service hosts an HTTP Server (Port 8080) locally on the device, exposing a `/battery` endpoint that returns JSON data containing precise voltage, current, and power figures.

#### 2. Stutter Analysis Algorithm (Jank & Big Jank)
- Obtains VSync triplet timestamps via `dumpsys SurfaceFlinger --latency`.
- **Jank:** Triggered when a single frame's render time exceeds twice the average of the previous three frames AND is greater than 83.33ms.
- **Big Jank:** Triggered when a single frame's render time exceeds 125ms.

<a name="usage-instructions-en"></a>
### Usage Instructions

<a name="usb-monitoring-mode-en"></a>
#### USB Monitoring Mode
1. Connect your Android phone to the PC via USB cable.
2. Confirm that `app-debug.apk` is located in the root folder of the project.
3. Verify that `adb devices` displays your device status as `device`.
4. Run the main application:
   ```bash
   python main.py
   ```
5. Click **"Start Monitoring"** in the top control panel:
   - The app will automatically detect the foreground package name on the phone.
   - It will install `app-debug.apk` and launch the battery service.
   - Real-time line charts for FPS, Temperature, RAM, GPU, Power, and 8 CPU Cores will begin rendering.
6. Click **"Stop"** to pause data collection.

<a name="wifi-wireless-adb-monitoring-mode-en"></a>
#### WiFi Wireless ADB Monitoring Mode
To perform wireless performance testing (e.g., for mobile gaming tests without cable interference):
1. First, connect the phone to the computer via USB.
2. Click the **"Enable WiFi ADB"** button on the top right of the GUI.
3. The program automatically executes:
   - Reads the phone's `wlan0` IP address (e.g., `192.168.1.100`).
   - Switches ADB to TCP/IP mode: `adb tcpip 5555`.
   - Connects wirelessly: `adb connect 192.168.1.100:5555`.
4. Once connected, you can unplug the USB cable and monitor device performance wirelessly over the local network.

<a name="exporting-csv-data-en"></a>
#### Exporting CSV Data
After stopping a monitoring session, click **"Export CSV"**:
- Select a target folder and file name.
- The exported CSV includes the following fields: `Time`, `FPS`, `Temp`, `Mem`, `GPU(%)`, `Power(mW)`, `Voltage(V)`, `Current(mA)`, `Jank`, `Big Jank`, `CPU0%`~`CPU7%`, `Core0(MHz)`~`Core7(MHz)`.

<a name="troubleshooting--faq-en"></a>
### Troubleshooting & FAQ

| Problem | Cause | Solution |
| :--- | :--- | :--- |
| Console output: `[Error] ADB executable not found` | ADB is not in system PATH or `ADB_EXEC_PATH` is unconfigured. | Follow the [Install and Configure ADB] steps to add ADB to environment variables or restart your terminal/IDE. |
| Power fields show `N/A` or `0` / No power data | `app-debug.apk` is missing from the directory, or port 8080 is blocked. | 1. **Ensure `app-debug.apk` is placed in the exact same folder as `main.py`**.<br>2. Confirm the PC and phone are on the same local network.<br>3. Check if the BatteryAPI app is installed on the phone with necessary permissions. |
| FPS displays `-1` or doesn't update | The active app is not rendering via SurfaceView or layer matching failed. | Switch to an app with active drawing (e.g., a game or video player) so SurfaceFlinger produces layer data. |
| Wireless ADB connection failed | PC and phone are on different Wi-Fi networks/subnets. | Ensure both PC and Android device are connected to the same Wi-Fi router (same LAN segment). |
| `ImportError: No module named 'PyQt5'` | Required Python dependencies are missing. | Run `pip install PyQt5 PyQtChart requests` to install missing packages. |

---

[Back to top / 回頁首](#android-perf-monitor-android-效能實時監控工具)

---

<a name="繁體中文"></a>
## 繁體中文

一個基於 Python (PyQt5) 與 Android ADB 介面的高效能實時監控 GUI 工具。本系統可即時採集並視覺化 Android 裝置的多項關鍵效能指標，包含 FPS (每秒幀率)、Jank/Big Jank (卡頓統計)、CPU 各核心使用率與頻率、GPU 使用率、電池溫度、記憶體佔用以及即時功耗 (電壓與電流)。

### 目錄
- [系統特色](#系統特色-zh)
- [前置環境需求與設定](#前置環境需求與設定-zh)
  - [1. 安裝與設定 ADB (Android Debug Bridge)](#1-安裝與設定-adb-android-debug-bridge-zh)
  - [2. Android 手機端開發者選項設定](#2-android-手機端開發者選項設定-zh)
  - [3. 安裝 Python 執行環境與相依套件](#3-安裝-python-執行環境與相依套件-zh)
- [專案結構說明](#專案結構說明-zh)
- [平台支援與數據限制](#平台支援與數據限制-zh)
- [核心模組與功能解析](#核心模組與功能解析-zh)
- [使用說明](#使用說明-zh)
  - [USB 監控模式](#usb-監控模式-zh)
  - [WiFi 無線 ADB 監控模式](#wifi-無線-adb-監控模式-zh)
  - [導出 CSV 數據](#導出-csv-數據-zh)
- [常問問題與故障排除](#常問問題與故障排除-zh)

---

> **⚠️ 重要提示（功耗數據採集）：**  
> 請務必將隨附的 **`app-debug.apk`** 檔案放置在與 `main.py` / `per.py` **相同的目錄（同一個資料夾）** 下。若缺少此 APK 檔案，系統將無法自動推送到手機並啟動背景測量服務，導致**無法讀取並顯示即時功耗 (電壓與電流) 數據**。

<a name="系統特色-zh"></a>
### 系統特色
1. **多維度實時效能圖表：**
   - **FPS & Jank：** 實時計算 SurfaceFlinger 的 VSync 數據，精確判斷 Jank (微卡頓) 與 Big Jank (嚴重卡頓)。
   - **CPU 核心分析：** 獨立呈現 8 個 CPU 核心的使用率 (%) 與運作頻率 (MHz)。
   - **GPU & 記憶體：** 讀取 `/sys/class/kgsl/kgsl-3d0/gpubusy` 計算 GPU 負載，並監控系統 RAM 使用率。
   - **電池與功耗：** 實時讀取電池溫度 (°C)，並搭配背景 APK 服務透過 HTTP 介面回傳精確的功耗 (mW)、電壓 (V) 與電流 (mA)。
2. **多執行緒架構 (Multi-threading)：**
   - 採集資料與 UI 渲染分離，確保圖表滑順不凍結。
   - 資料採集 (500ms) 與數據日誌紀錄 (1.0s) 精確同步。
3. **無線監控支援：**
   - 支援一鍵開啟 TCP/IP 5555 埠，實現無線 WiFi ADB 連線監控。
4. **數據匯出功能：**
   - 支援將監控過全程的數據導出為 UTF-8-SIG 編碼的 CSV 檔案，方便後續 Excel / Python 分析。

<a name="前置環境需求與設定-zh"></a>
### 前置環境需求與設定

在執行本程式之前，請務必先完成以下環境準備。

<a name="1-安裝與設定-adb-android-debug-bridge-zh"></a>
#### 1. 安裝與設定 ADB (Android Debug Bridge)
ADB 是本工具與 Android 裝置溝通的核心橋樑。

- **Step 1: 下載 Platform Tools**  
  請至 Google 官方開發者網站下載最新版的 SDK Platform-Tools (https://developer.android.com/tools/releases/platform-tools)。
- **Step 2: 解壓縮與系統環境變數設定 (PATH)**  
  1. 將下載的 `platform-tools` 解壓縮至固定的資料夾（例如：`C:\platform-tools`）。
  2. 新增至環境變數 (Windows)：
     - 按下 `Win + R` 輸入 `sysdm.cpl` 開啟系統屬性。
     - 切換至「進階」頁籤，點擊「環境變數」。
     - 在「系統變數」區域中找到 `Path` 變數，點擊「編輯」。
     - 點擊「新增」，填入 ADB 的解壓路徑（例如 `C:\platform-tools`）。
     - 一路點擊「確定」保存設定。
  3. 驗證 ADB 是否安裝成功：  
     開啟新的命令提示字元 (`cmd`) 或 Terminal，輸入：
     ```bash
     adb version
     ```
     若能正確顯示版本號（如 `Android Debug Bridge version 1.0.41`），表示環境變數設定成功。

*自訂 ADB 路徑說明：*  
本專案模組支援讀取環境變數 `ADB_EXEC_PATH`。若未設定 PATH，您亦可在執行程式前設定環境變數：
```cmd
set ADB_EXEC_PATH=C:\path\to\your\adb.exe
```

<a name="2-android-手機端開發者選項設定-zh"></a>
#### 2. Android 手機端開發者選項設定
1. **開啟開發者人員選項：** 前往手機「設定」->「關於手機」。連續點擊「版本號碼 (Build Number)」7 次，直到顯示「您已成為開發人員」。
2. **啟用 USB 偵錯：** 前往手機「設定」->「系統」->「開發人員選項」。開啟 「USB 偵錯 (USB Debugging)」。(部分品牌如小米/OPPO需另外開啟「USB 偵錯 (安全設定)」，允許傳送模擬輸入或安裝 APK)。
3. **首次連線授權：** 將手機透過 USB 傳輸線連接至電腦。在電腦 CMD 輸入 `adb devices`。此時手機螢幕會彈出 「允許 USB 偵錯嗎？」 的授權提示，請勾選「一律允許透過這台電腦進行授權」點擊 「允許」。

<a name="3-安裝-python-執行環境與相依套件-zh"></a>
#### 3. 安裝 Python 執行環境與相依套件
本工具基於 Python 3.8+ 開發，依賴 PyQt5 與 QtChart 模組進行 GUI 渲染。

```bash
pip install PyQt5 PyQtChart requests
```

<a name="專案結構說明-zh"></a>
### 專案結構說明

請確保您的專案目錄包含以下檔案結構，**特別注意 `app-debug.apk` 必須包含在同一個資料夾內**：

```text
.
├── main.py               # 主程式 (GUI 介面與繪圖邏輯，包含 MonitorWindow 與 DataThread)
├── per.py                # ADB 底層溝通模組 (負責 dumpsys 解析、sysfs 讀取與 APK 服務交互)
├── app-debug.apk         # 【必要檔案】電池與功耗採集服務 APK (必須與 main.py 放同目錄，否則無法採集功耗)
└── README.md             # 本說明文件
```

<a name="平台支援與數據限制-zh"></a>
### 平台支援與數據限制

| 指標 | 支援狀態 | 說明 |
| :--- | :--- | :--- |
| **FPS** | **僅 Android 12+** | 透過 SurfaceFlinger VSync 時間資料計算。Android 11 以下視為不支援。 |
| **GPU 使用率** | **僅 Qualcomm Snapdragon** | 必須存在 Qualcomm KGSL 介面，通常為 `/sys/class/kgsl/kgsl-3d0/gpubusy`。 |
| **Google Pixel GPU 使用率** | **不支援** | Pixel 系列明確排除 GPU 使用率採集，GUI／CSV 顯示 `N/A`／不可用。 |
| **CPU 使用率／頻率** | 依裝置而定 | 取決於 Android 裝置是否提供對應 CPU sysfs 介面。 |
| **RAM／溫度** | 依裝置而定 | 取決於裝置提供的系統介面。 |
| **功耗／電壓／電流** | 需要 `app-debug.apk` | 透過內建 BatteryService APK 採集。 |

**重要實作規則：** 啟動監控時，程式應先判斷 Android 版本、SoC／廠商，以及 GPU 介面是否存在。對於不支援的指標，請顯示 `N/A`／不可用，**不要將不支援誤判為 `0%`**。

<a name="核心模組與功能解析-zh"></a>
### 核心模組與功能解析

#### 1. 電池功耗服務模組 (com.example.batteryapi)
- 程式啟動監控時，`per.py` 會自動讀取與主程式**位於同一目錄下的 `app-debug.apk`** 並安裝至手機，隨後啟動前台服務 `BatteryService`。
- **注意：** 若同目錄下未提供 `app-debug.apk`，功耗模組將無法運作，導致圖表與 CSV 中無法顯示功耗 (mW)、電壓 (V) 及電流 (mA)。
- 該服務會在手機本地端啟動 HTTP Server (Port 8080)，提供 `/battery` Endpoint 回傳精確的電壓、電流與功耗 JSON 資料。

#### 2. 卡頓分析演算法 (Jank & Big Jank)
- 透過 `dumpsys SurfaceFlinger --latency` 獲取 VSync triplet 時間戳記。
- 當單一幀渲染時間超過前三幀平均值的 2 倍且大於 83.33ms 時記為 Jank。
- 當單一幀渲染時間大於 125ms 時記為 Big Jank。

<a name="使用說明-zh"></a>
### 使用說明

<a name="usb-監控模式-zh"></a>
#### USB 監控模式
1. 使用 USB 傳輸線連接 Android 手機與電腦。
2. 確認 `app-debug.apk` 檔案已正確放置於專案根目錄中。
3. 確認 `adb devices` 能看到設備狀態為 `device`。
4. 執行主程式：
   ```bash
   python main.py
   ```
5. 在 GUI 介面上方點擊 「開始監控」：
   - 系統會自動獲取當前手機前景應用的 Package Name。
   - 自動將同目錄下的背景功耗 APK (`app-debug.apk`) 推送安裝至手機並啟動服務。
   - 視窗將開始實時繪製 FPS、溫度、RAM、GPU、功耗與 CPU 8 核心折線圖。
6. 點擊 「停止」 可暫停資料監控。

<a name="wifi-無線-adb-監控模式-zh"></a>
#### WiFi 無線 ADB 監控模式
若需要脫離 USB 線材進行高自由度的效能測試（如手遊測試）：
1. 先將手機以 USB 連接至電腦。
2. 點擊 GUI 介面右上方的 「開啟WiFi ADB」 按鈕。
3. 程式會自動執行以下指令：
   - 讀取手機 wlan0 的 IP 位址（如 `192.168.1.100`）。
   - 切換 ADB 至 TCP/IP 模式：`adb tcpip 5555`。
   - 自動連線：`adb connect 192.168.1.100:5555`。
4. 當介面提示成功後，即可拔除 USB 傳輸線，全程透過無線網絡進行效能資料採集。

<a name="導出-csv-數據-zh"></a>
#### 導出 CSV 數據
在監控結束後，點擊 GUI 介面的 「導出CSV」 按鈕：
- 選擇儲存路徑與檔名。
- 匯出的 CSV 將包含完整欄位：`Time`, `FPS`, `Temp`, `Mem`, `GPU(%)`, `Power(mW)`, `Voltage(V)`, `Current(mA)`, `Jank`, `Big Jank`, `CPU0%`~`CPU7%`, `Core0(MHz)`~`Core7(MHz)`。

<a name="常問問題與故障排除-zh"></a>
### 常問問題與故障排除

| 問題現象 | 判斷原因 | 解決方法 |
| :--- | :--- | :--- |
| 主控台顯示 [Error] 找不到 ADB 可執行文件 | 未將 ADB 加入 PATH 或未設定 `ADB_EXEC_PATH`。 | 請參考 [安裝與設定 ADB] 步驟，重新將 ADB 加入系統環境變數，或重開 CMD/IDE。 |
| GUI 功耗欄位顯示 N/A 或 0 / 完全沒有功耗數據 | 專案目錄下缺少 `app-debug.apk`，或是手機防火牆阻擋了 8080 埠。 | 1. **確認 `app-debug.apk` 已放置在與 `main.py` 相同的資料夾下**。<br>2. 確認電腦與手機在同一網域下。<br>3. 檢查手機上是否已有 BatteryAPI 應用程式並允許相關權限。 |
| FPS 顯示 `N/A` / -1 或不更新 | 裝置低於 Android 12，或當前前景 App 未產生可用的 SurfaceFlinger frame data，或 Layer 名稱匹配失敗。 | 先確認 Android 版本為 12 以上，再切換至有持續畫面更新的 App（例如遊戲或影片播放器）。Android 11 以下不支援 FPS。 |
| GPU 顯示 `N/A` | 裝置不是 Qualcomm Snapdragon、缺少 KGSL GPU 介面，或裝置為 Google Pixel 系列。 | GPU 使用率目前只支援 Qualcomm Snapdragon 且需要 KGSL 介面；Pixel 系列明確不支援。`N/A` 代表無法／不允許採集，不代表 GPU 使用率為 0%。 |
| WiFi ADB 連線失敗 | 手機與電腦未連接在同一個 Wi-Fi 路由器下。 | 請確認手機與電腦位於相同區域網路 (LAN) 段。 |
| ImportError: No module named 'PyQt5' | Python 環境缺少 PyQt5 依賴套件。 | 執行 `pip install PyQt5 PyQtChart requests` 進行補齊。 |

---

[Back to top / 回頁首](#android-perf-monitor-android-效能實時監控工具)
