import re
import subprocess
import time
from subprocess import Popen, PIPE
import requests
import json

# ========== ADB Utility Functions ==========
CREATE_NO_WINDOW = 0x08000000
APK_PATH = "./app-debug.apk"  
PACKAGE_NAME = "com.example.batteryapi"
SERVICE_CLASS = "com.example.batteryapi/com.example.batteryapi.BatteryService"
PORT = 8080
def run(cmd):
    return subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode("utf-8", errors="ignore")
def run_adb_command(cmd):
    try:
        result = subprocess.run(["adb"] + cmd, capture_output=True, text=True, encoding="utf-8", timeout=5,creationflags=CREATE_NO_WINDOW)
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""
def get_device_name():
    return run_adb_command(["shell", "getprop", "ro.product.model"])

def enable_wifi_debug():
    # 先抓 IP
    subprocess.run("adb devices",capture_output=True, text=True,creationflags=CREATE_NO_WINDOW)
    output = run_adb_command(["shell", "ip route"])

    ip_addr = ""
    for line in output.splitlines():
        if "src" in line:
            ip_addr = line.strip().split("src")[-1].strip()
            break

    if not ip_addr:
        return ""

    # 然後才切換為 TCP 模式
    run_adb_command(["tcpip", "5555"])
    time.sleep(2)

    connect_result = run_adb_command(["connect", f"{ip_addr}:5555"])
    # print("connect_result:", connect_result)
    if "connected" in connect_result or "already connected" in connect_result:
        return ip_addr
    return ""


def get_wifi_ip():
    output = run_adb_command(["shell", "ip", "route"])
    for line in output.splitlines():
        if "wlan0" in line:
            parts = line.split()
            for part in parts:
                if part.count('.') == 3:
                    return part
    return ""

def get_foreground_app():
    output = run_adb_command(["shell", "dumpsys", "activity", "activities"])
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("ResumedActivity"):
            parts = line.split()
            for part in parts:
                if "/" in part:
                    return part.split("/")[0]
    return ""

def get_surfaceflinger_target_layer(package):
    """
    從 'adb shell dumpsys SurfaceFlinger --list' 的輸出中，
    找到指定 package 的最後一個 SurfaceView layer。
    此函式可以處理 layer 名稱前面包含可選十六進位前綴的情況。
    """
    output = run_adb_command(["shell", "dumpsys", "SurfaceFlinger", "--list"])
    
    pattern = rf"(?:[0-9a-fA-F]+\s+)?SurfaceView\[{re.escape(package)}/[^\]]+\]\(BLAST\)#\d+"

    matches = []
    for line in output.splitlines():
        match = re.search(pattern, line)
        if match:
            # match.group() 會返回整個匹配到的字串
            # 無論是 "SurfaceView[...]" 或是 "2c9183a  SurfaceView[...]"
            matches.append(match.group().strip()) # 使用 strip() 去除前後多餘的空白

    # 返回最後一個匹配項，如果沒有則返回空字串
    return matches[-1] if matches else ""



def get_refresh_rate():
    output = run_adb_command(['shell', 'dumpsys SurfaceFlinger | grep "refresh-rate"'])
    match = re.search(r'refresh-rate\s*:\s*([\d.]+)\s*Hz', output)
    if match:
        return float(match.group(1))
    return 60.0  # fallback 預設為 60Hz

def calculate_jank_by_vsync_triplets(triplets, refresh_period_ns):

    jank_count = 0
    big_jank_count = 0

    display_timestamps = [t[2] for t in triplets if len(t) == 3 and t[2] > 0]

    if len(display_timestamps) < 4:
        return 0, 0

    JANK_THRESHOLD_NS = (1000 / 60 * 2) * 1_000_000  # 83.33ms
    BIG_JANK_THRESHOLD_NS = (1000 / 60 * 3) * 1_000_000  # 125ms

    for i in range(3, len(display_timestamps)):
        current_frame_time = display_timestamps[i] - display_timestamps[i - 1]
        
        prev_frame_times = [
            display_timestamps[i - 1] - display_timestamps[i - 2],
            display_timestamps[i - 2] - display_timestamps[i - 3],
            display_timestamps[i - 3] - display_timestamps[i - 4]
        ]
        avg_prev_three_frames = sum(prev_frame_times) / 3
        condition1_jank = current_frame_time > (avg_prev_three_frames * 2)
        condition2_jank = current_frame_time > JANK_THRESHOLD_NS
        
        if condition1_jank and condition2_jank:
            jank_count += 1
            condition2_big_jank = current_frame_time > BIG_JANK_THRESHOLD_NS
            if condition1_jank and condition2_big_jank:
                big_jank_count += 1

    return jank_count, big_jank_count

def dump_layer_stats(layer_name):
    cmd = f'adb shell dumpsys SurfaceFlinger --latency \\"{layer_name}\\"'
    p = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE, universal_newlines=True,creationflags=CREATE_NO_WINDOW)
    L = []

    for line in p.stdout:
        if line.strip() != '':
            parts = line.strip().split('\t')
            try:
                ints = list(map(int, parts))
                if len(ints) > 1 and ints[1] < 9223372036854775807 and ints[1] != 0:
                    L.append(ints[1])
            except:
                pass
    return L

def get_fps(package):
    layer_name = get_surfaceflinger_target_layer(package)
    # print(layer_name)
    if not layer_name:
        return -1
    L = dump_layer_stats(layer_name)
    size = len(L)
    if size == 0:
        return -1
    interval = L[-1] - L[0]
    if interval == 0:
        return -1
    fps = 1_000_000_000 * (size - 1) / interval
    return round(fps)


def get_cpu_usage_and_freq():
    output = run_adb_command(["shell", "cat", "/proc/stat"])
    lines = output.splitlines()
    current_totals, current_idles = [], []
    for line in lines:
        if line.startswith("cpu"):
            parts = list(map(int, line.split()[1:5]))
            total = sum(parts)
            idle = parts[3]
            current_totals.append(total)
            current_idles.append(idle)
        else:
            break

    if not hasattr(get_cpu_usage_and_freq, "_prev_totals"):
        get_cpu_usage_and_freq._prev_totals = current_totals
        get_cpu_usage_and_freq._prev_idles = current_idles
        return [0] * (len(current_totals) - 1), [0] * (len(current_totals) - 1)

    prev_totals = get_cpu_usage_and_freq._prev_totals
    prev_idles = get_cpu_usage_and_freq._prev_idles

    length = min(len(current_totals), len(prev_totals))
    usages = []
    for i in range(1, length):
        total_diff = current_totals[i] - prev_totals[i]
        idle_diff = current_idles[i] - prev_idles[i]
        usage = (total_diff - idle_diff) / total_diff * 100 if total_diff else 0
        usages.append(usage)

    get_cpu_usage_and_freq._prev_totals = current_totals
    get_cpu_usage_and_freq._prev_idles = current_idles

    freqs = []
    idx = 0
    while True:
        freq = run_adb_command(["shell", "cat", f"/sys/devices/system/cpu/cpu{idx}/cpufreq/scaling_cur_freq"])
        if "No such file" in freq or freq.strip() == "":
            break
        freqs.append(int(freq.strip()) / 1000 if freq.strip().isdigit() else 0)
        idx += 1

    return usages, freqs
def GPU_Usage():
    # 1. 執行 adb 指令讀取 gpubusy 檔案
    output = run_adb_command(["shell", "cat", "/sys/class/kgsl/kgsl-3d0/gpubusy"])
    
    if not output:
        return 0.0

    try:
        # 3. 將輸出的字串分割成兩個部分
        parts = output.split()
        
        if len(parts) == 2:
            busy_cycles = int(parts[0])
            total_cycles = int(parts[1])
            
            if total_cycles == 0:
                return 0.0
            
            usage = (busy_cycles / total_cycles) * 100
            return usage
            
    except (ValueError, IndexError):
        # 如果輸出格式不對 (例如不是數字)，則返回 0
        return 0.0
        
    return 0.0
def get_battery_temp():
    output =run("adb shell dumpsys battery | grep temperature")
    match = re.search(r':\s*(\d+)', output)

    if match:
        # match.group(1) 提取括號 () 內的數字，即 "323"
        temp_str = match.group(1)
        
        try:
            # 轉換為整數 (323)，然後除以 1000 得到攝氏度 (32.3)
            temp_int = int(temp_str)
            return temp_int / 10
        except ValueError:
            # 如果抓到的內容不是有效數字，則返回 0
            return 0
    else:
        # 如果沒有找到匹配的 "temperature: <數字>" 模式，則返回 0
        return 0
def install_and_start_service():
    try:
        # 1. 先嘗試安裝/更新
        run(f'adb install -r "{APK_PATH}"') 
    except subprocess.CalledProcessError as e:
        # 2. 如果安裝失敗，嘗試先卸載再安裝
        run(f"adb uninstall {PACKAGE_NAME}")
        run(f'adb install "{APK_PATH}"')

    # 3. 確保使用 start-foreground-service 啟動，以避免 Android 8.0+ 的限制
    start_cmd = f"adb shell am start-foreground-service -n {SERVICE_CLASS}"
    try:
        run(start_cmd)
        print("✅ 服務啟動成功")
    except subprocess.CalledProcessError as e:
        # 啟動失敗通常是 Manifest 或代碼問題，這裡列出錯誤訊息
        print(e.output)
def get_device_ip():
    output = run("adb shell ip addr show wlan0")
    match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", output)
    if match:
        ip = match.group(1)
        return ip
    else:
        return None
def get_power_data(ip):
    try:
        url = f"http://{ip}:{PORT}/battery"
        resp = requests.get(url, timeout=3)

        if resp.status_code == 200:
            try:
                data = resp.json()
                
                # 【已修正】使用您服務實際回傳的鍵名: 'powerMW', 'voltageV', 'currentMA'
                power = data.get('powerMW')
                voltage = data.get('voltageV') 
                current = data.get('currentMA')

                if power is not None and voltage is not None and current is not None:
                    return {
                        'power_mW': power,
                        'voltage_V': voltage, 
                        'current_mA': current
                    }
                else:
                    return None

            except json.JSONDecodeError:
                return None
        else:
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"⚠️ 無法連線至 {ip}:{PORT}。錯誤: {e}")
        return None
def uninstall_service():
    run(f"adb uninstall {PACKAGE_NAME}")
def get_mem_usage():
    output = run_adb_command(["shell", "cat", "/proc/meminfo"])
    mem = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            mem[parts[0].strip(':')] = int(parts[1])
    total = mem.get("MemTotal", 1)
    available = mem.get("MemAvailable", 0)
    return (total - available) / total * 100
def check_adb_connection():
    
    try:
        output = run("adb get-state").strip()
        if output == "device":
            return True
        else:
            return False
    except subprocess.CalledProcessError:
        return False

if __name__ == '__main__':  
#    print (get_device_name())
    pass
