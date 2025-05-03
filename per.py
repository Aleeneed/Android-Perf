import re
import subprocess
import time
from subprocess import Popen, PIPE

# ========== ADB Utility Functions ==========
CREATE_NO_WINDOW = 0x08000000
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
    # print("route output:", output)

    ip_addr = ""
    for line in output.splitlines():
        if "src" in line:
            ip_addr = line.strip().split("src")[-1].strip()
            break

    if not ip_addr:
        # print("無法取得 IP")
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
    output = run_adb_command(["shell", "dumpsys", "SurfaceFlinger", "--list"])
    pattern = rf"SurfaceView\[{re.escape(package)}/[^\]]+\]\(BLAST\)#\d+"

    matches = []
    for line in output.splitlines():
        match = re.search(pattern, line)
        if match:
            matches.append(match.group())

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

    # 提取 c 值（显示时间）
    display_timestamps = [t[2] for t in triplets if len(t) == 3 and t[2] > 0]

    if len(display_timestamps) < 2:
        return 0, 0

    for i in range(1, len(display_timestamps)):
        interval = display_timestamps[i] - display_timestamps[i - 1]
        dropped_frames = int(round(interval / refresh_period_ns)) - 1
        if dropped_frames > 6.66:
            jank_count += 1
        if dropped_frames >= 8:
            big_jank_count += 1

    return jank_count, big_jank_count
def dump_surfaceflinger_latency_triplets(layer_name):
    cmd = f'adb shell dumpsys SurfaceFlinger --latency \\"{layer_name}\\"'
    p = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE, universal_newlines=True,creationflags=CREATE_NO_WINDOW)
    triplets = []
    for line in p.stdout:
        parts = line.strip().split('\t')
        if len(parts) == 3:
            try:
                a, b, c = map(int, parts)
                if c != 0 and c < 9223372036854775807:
                    triplets.append((a, b, c))
            except:
                pass
    return triplets

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
def get_cpu_temp():
    temp = run_adb_command(["shell", "cat", "/sys/class/thermal/thermal_zone0/temp"])
    return int(temp)/1000 if temp.isdigit() else 0

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
_last_charge = None
_last_time = None
def get_power_info():
    global _last_charge, _last_time

    output = run_adb_command(["shell", "dumpsys", "battery"])
    voltage = 0
    charge = 0
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("voltage:"):
            voltage = int(line.split(":")[1].strip()) / 1000  # mV to V
        elif line.startswith("Charge counter:"):
            charge = int(line.split(":")[1].strip()) / 1000   # µAh to mAh

    now = time.time()

    if _last_charge is not None and _last_time is not None:
        delta_charge = charge - _last_charge  # mAh
        delta_time = (now - _last_time) / 3600  # 小時
        power = 0
        if delta_time > 0:
            power = abs(delta_charge / delta_time) * voltage  # W
    else:
        power = 0

    _last_charge = charge
    _last_time = now
    return round(voltage, 2), round(charge, 2), round(power, 3)

