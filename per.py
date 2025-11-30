import re
import subprocess
import time
from subprocess import Popen, PIPE
import requests
import json
import os
# ========== ADB Utility Functions ==========
CREATE_NO_WINDOW = 0x08000000
APK_PATH = "./app-debug.apk"  
PACKAGE_NAME = "com.example.batteryapi"
SERVICE_CLASS = "com.example.batteryapi/com.example.batteryapi.BatteryService"
PORT = 8080
# 1. 尝试从环境变量中获取（如果用户设置了）
ADB_EXEC = os.environ.get("ADB_EXEC_PATH")

# 2. 如果未设置，则假设 adb.exe 位于当前目录或 PATH 中（用于开发环境）
# **注意：当打包成 .exe 后，这仍可能失败，建议用户将 adb.exe 放在 .exe 旁边**
if not ADB_EXEC:
    # 在打包环境下，sys.executable 是 .exe 本身
    # 我们假设 adb.exe 与 .exe 位于同一目录下
    # 如果 adb.exe 在 PATH 中，则直接使用 "adb"
    ADB_EXEC = "adb"
def run(cmd):
    return subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode("utf-8", errors="ignore")
def run_adb_command(cmd):
    try:
        # 将 ADB_EXEC 加入命令列表头部
        full_cmd = [ADB_EXEC] + cmd 
        result = subprocess.run(full_cmd, capture_output=True, text=True, encoding="utf-8", timeout=5, creationflags=CREATE_NO_WINDOW)
        
        # 即使 returncode != 0，也返回 stderr/stdout 以便调试
        if result.returncode == 0:
             return result.stdout.strip()
        else:
             # 返回错误信息，以便调用者检查
             return f"ERROR_CODE:{result.returncode}::{result.stderr.strip() or result.stdout.strip()}"

    except FileNotFoundError:
        print(f"\n❌ [严重错误] 找不到 ADB 可执行文件！请确认 ADB_EXEC 变量设置正确：{ADB_EXEC}")
        print("这通常是打包成 .exe 后发生的问题。请确保 adb.exe 位于 PATH 中或已指定绝对路径。")
        return "ADB_NOT_FOUND" # 统一返回一个特殊的错误标志
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

def get_vsync_triplets(layer_name):
    """
    获取指定 layer 的 VSync triplets 数据
    直接复用 dump_layer_stats 的逻辑，但返回完整的 triplets
    返回格式: [(a, b, c), (a, b, c), ...]
    """
    if not layer_name:
        return []
    
    # 使用与 dump_layer_stats 相同的命令格式
    cmd = f'adb shell dumpsys SurfaceFlinger --latency \\"{layer_name}\\"'
    
    try:
        p = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE, 
                  universal_newlines=True, creationflags=CREATE_NO_WINDOW)
        
        triplets = []
        line_count = 0
        
        for line in p.stdout:
            line_count += 1
            line = line.strip()
            
            if line == '':
                continue
            
            # 第一行是刷新周期，跳过
            if line_count == 1:
                continue
            
            parts = line.split('\t')
            
            try:
                if len(parts) >= 3:
                    a = int(parts[0])
                    b = int(parts[1])
                    c = int(parts[2])
                    
                    # 过滤无效数据（与原 dump_layer_stats 逻辑一致）
                    if b < 9223372036854775807 and b != 0:
                        triplets.append((a, b, c))
                        
                        # 打印前几个样本用于调试
            except (ValueError, IndexError) as e:
                if line_count <= 5:
                    print(f"[DEBUG] Failed to parse line {line_count}: '{line}', error: {e}")
                pass        
        return triplets
        
    except Exception as e:
        print(f"[ERROR] get_vsync_triplets failed: {e}")
        import traceback
        traceback.print_exc()
        return []

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
    # 注意：这里的 adb install/uninstall 命令字符串中含有空格和引号，
    # run 函数中使用 shell=True 是合适的，但我们需要确保 ADB_EXEC 在 PATH 中
    # 或者用绝对路径替换 'adb'
    
    adb_exec_cmd = ADB_EXEC if ADB_EXEC != "adb" else "adb" # 确保 cmd 字符串中是 adb
    
    # 转换为使用绝对路径的命令字符串
    install_cmd = f'{adb_exec_cmd} install -r "{APK_PATH}"'
    uninstall_cmd = f'{adb_exec_cmd} uninstall {PACKAGE_NAME}'
    start_cmd = f"{adb_exec_cmd} shell am start-foreground-service -n {SERVICE_CLASS}"
    
    try:
        # 1. 先尝试安装/更新 (注意：如果 adb 找不到，这里会失败)
        run(install_cmd) 
        print(f"✅ 应用 {PACKAGE_NAME} 安装/更新成功。")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ 第一次安装失败 (可能已安装或版本冲突)，尝试卸载后重新安装...")
        
        # 2. 如果第一次安装失败，尝试先卸载再安装
        try:
            # 卸载操作。设置 check=False 容忍卸载失败 (例如：应用未安装)
            subprocess.run(uninstall_cmd, shell=True, check=False, creationflags=CREATE_NO_WINDOW, 
                           stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            
            # 再次尝试安装
            run(f'{adb_exec_cmd} install "{APK_PATH}"')
            print(f"✅ 卸载后，应用 {PACKAGE_NAME} 重新安装成功。")

        except subprocess.CalledProcessError as e2:
            # 这里的 CalledProcessError 可能是第二次安装失败，需要打印输出
            print(f"❌ 卸载/再次安装失败，错误信息：\n{e2.output}")
            raise # 再次安装失败是严重错误，重新抛出
        except FileNotFoundError:
            # 这里的 FileNotFoundError 意味着 ADB_EXEC 路径不对
            print(f"❌ [严重错误] 在异常处理块中仍找不到 ADB ({adb_exec_cmd})。请检查路径。")
            raise
    except FileNotFoundError:
        # 捕获外部 adb 命令找不到的错误
        print(f"❌ [严重错误] 找不到 ADB ({adb_exec_cmd})。请检查 ADB_EXEC 路径。")
        raise
        

    # 3. 启动服务
    try:
        # 启动命令
        run(start_cmd)
        print("✅ 远端服务启动成功")
    except subprocess.CalledProcessError as e:
        # 启动失败通常是 Manifest 或代碼问题
        print(f"❌ 服务启动失败，错误信息：\n{e.output}")
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
    # 使用 check=False 容忍卸载失败（应用可能未安装）
    adb_exec_cmd = ADB_EXEC if ADB_EXEC != "adb" else "adb"
    subprocess.run(f"{adb_exec_cmd} uninstall {PACKAGE_NAME}", 
                   shell=True, check=False, 
                   creationflags=CREATE_NO_WINDOW)
    print(f"✅ 尝试卸载 {PACKAGE_NAME} 完毕。")
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
        # 使用 run_adb_command
        output = run_adb_command(["get-state"]).strip()
        
        if output.startswith("ERROR_CODE") or output == "ADB_NOT_FOUND":
            return False
        
        # 如果 adb get-state 返回 device，则连接正常
        if output == "device":
            return True
        else:
            return False
    except:
        # 捕获所有其他潜在错误
        return False

if __name__ == '__main__':  
#    print (get_device_name())
    pass
