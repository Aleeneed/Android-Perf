import sys
import time
import math
import csv
from collections import deque
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QMessageBox, QFileDialog
)
from PyQt5.QtChart import QChart, QChartView, QLineSeries, QValueAxis
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QPointF
from PyQt5.QtGui import QPainter, QColor

# It's assumed a 'per' module exists with the necessary functions.
# Since it's not provided, a mock will be used for demonstration if run directly.
try:
    import per
except ImportError:
    print("Warning: 'per' module not found. Using mock data.")
    class MockPer:
        def get_foreground_app(self): return "com.mock.app"
        def get_fps(self, app): return 60 * (0.9 + 0.1 * math.sin(time.time()))
        def get_cpu_usage_and_freq(self):
            t = time.time()
            # Simulate initial zero values for the first 0.1 seconds
            if not hasattr(self, 'start_time'):
                self.start_time = t
            if t - self.start_time < 0.1:
                 return [0]*8, [0]*8
            usages = [50 + 40 * math.sin(t + i) for i in range(8)]
            freqs = [1500 + 1000 * math.sin(t + i) for i in range(8)]
            return usages, freqs
        def GPU_Usage(self): return 45 + 20 * math.sin(time.time() * 0.5)
        def get_battery_temp(self): return 35 + 5 * math.sin(time.time() * 0.2)
        def get_mem_usage(self): return 60 + 10 * math.sin(time.time() * 0.3)
        def get_power_data(self, ip):
            t = time.time()
            current = abs(-400 + 150 * math.sin(t * 2))
            voltage = 4.2 - 0.2 * math.sin(t * 2)
            power = current * voltage
            return {'power_mW': power, 'voltage_V': voltage, 'current_mA': current}
        def get_refresh_rate(self): return 120.0
        def get_surfaceflinger_target_layer(self, target): 
            # Mock triplets data
            import random
            triplets = []
            base_time = time.time_ns()
            for i in range(10):
                triplets.append((i, base_time + i * 16_666_666, base_time + i * 16_666_666 + random.randint(0, 50_000_000)))
            return triplets
        def calculate_jank_by_vsync_triplets(self, triplets, period): return (int(time.time()) % 5, int(time.time()) % 2)
        def get_device_name(self): return "Mock Device"
        def get_device_ip(self): return "192.168.1.100"
        def enable_wifi_debug(self): return "192.168.1.100"
        def install_and_start_service(self): print("Mock: Installing service.")
        def run_adb_command(self, cmd): print(f"Mock ADB: {cmd}")
        def uninstall_service(self): print("Mock: Uninstalling service.")
    per = MockPer()


MAX_POINTS = 2000
UI_UPDATE_INTERVAL = 100  # UI 更新频率 100ms，更流畅
DATA_COLLECTION_INTERVAL = 500  # 数据采集间隔改为 500ms
DATA_LOG_INTERVAL = 1.0  # 数据记录到 log 的间隔 1 秒

class DataThread(QThread):
    data_ready = pyqtSignal(dict)

    def __init__(self, interval_ms=500):
        super().__init__()
        self.interval = interval_ms / 1000.0
        self.running = True
        self.last_triplets = []  # 缓存上次的 triplets
        
        # 缓存上次的数据，避免某些数据获取失败时显示空白
        self.last_data = {
            'device': '',
            'ip': '',
            'refresh_rate': 60.0
        }

    def run(self):
        frame_count = 0
        last_triplet_time = 0
        last_slow_data_time = 0  # 用于控制慢速数据获取
        
        while self.running:
            loop_start_time = time.time()
            
            try:
                info = {}
                
                # === 快速数据：每次都获取 ===
                # CPU 使用率和频率 - 相对快速
                usages, freqs = per.get_cpu_usage_and_freq()
                info['usages'] = usages
                info['freqs'] = freqs
                
                # === 慢速数据：每 2 秒获取一次 ===
                current_time = time.time()
                if current_time - last_slow_data_time >= 2.0:
                    last_slow_data_time = current_time
                    
                    # 这些命令较慢，降低频率
                    try:
                        foreground_app = per.get_foreground_app()
                        self.last_data['foreground_app'] = foreground_app
                        
                        # FPS - 较慢
                        fps = per.get_fps(foreground_app)
                        if fps >= 0:  # 只有有效值才更新
                            self.last_data['fps'] = fps
                        
                        # GPU、温度、内存
                        self.last_data['gpu'] = per.GPU_Usage()
                        self.last_data['temp'] = per.get_battery_temp()
                        self.last_data['mem'] = per.get_mem_usage()
                        
                        # 电源数据
                        power_info = per.get_power_data(per.get_device_ip())
                        if power_info:
                            self.last_data['power_info'] = power_info
                        
                        # 刷新率（很少变化）
                        refresh_rate = per.get_refresh_rate()
                        if refresh_rate > 0:
                            self.last_data['refresh_rate'] = refresh_rate
                        
                        # 设备信息（基本不变）
                        if not self.last_data.get('device'):
                            self.last_data['device'] = per.get_device_name()
                        if not self.last_data.get('ip'):
                            self.last_data['ip'] = per.get_device_ip() if hasattr(per, 'get_device_ip') else None
                            
                    except Exception as e:
                        print(f"[DataThread] Slow data error: {e}")
                
                # 使用缓存的数据
                info['fps'] = self.last_data.get('fps', 0.0)
                info['gpu'] = self.last_data.get('gpu', 0.0)
                info['temp'] = self.last_data.get('temp', 0.0)
                info['mem'] = self.last_data.get('mem', 0.0)
                info['power_info'] = self.last_data.get('power_info', {})
                info['refresh_rate'] = self.last_data.get('refresh_rate', 60.0)
                info['device'] = self.last_data.get('device', '')
                info['ip'] = self.last_data.get('ip', None)
                
                # === Jank 计算：每 2 秒一次 ===
                jank_count = 0
                big_jank_count = 0
                
                if current_time - last_triplet_time >= 2.0:
                    last_triplet_time = current_time
                    
                    try:
                        foreground_app = self.last_data.get('foreground_app', '')
                        if foreground_app:
                            layer_name = per.get_surfaceflinger_target_layer(foreground_app)
                            
                            if layer_name and hasattr(per, 'get_vsync_triplets'):
                                current_triplets = per.get_vsync_triplets(layer_name)
                                
                                if current_triplets and len(current_triplets) > 0:
                                    new_triplets = current_triplets
                                    if self.last_triplets and len(self.last_triplets) > 0:
                                        last_timestamp = self.last_triplets[-1][2]
                                        new_triplets = [t for t in current_triplets if t[2] > last_timestamp]
                                    
                                    if new_triplets and len(new_triplets) >= 4:
                                        refresh_period_ns = int(1_000_000_000 / info['refresh_rate'])
                                        jank_count, big_jank_count = per.calculate_jank_by_vsync_triplets(
                                            new_triplets, refresh_period_ns
                                        )
                                    
                                    self.last_triplets = current_triplets[-50:]
                    except Exception as e:
                        if frame_count % 20 == 0:
                            print(f"[DataThread] Jank error: {e}")
                
                info['jank'] = jank_count
                info['big_jank'] = big_jank_count
                
                frame_count += 1
                
            except Exception as e:
                print(f"[DataThread] exception: {e}")
                info = {'error': str(e)}
            
            self.data_ready.emit(info)
            
            # 精确的时间控制
            elapsed = time.time() - loop_start_time
            sleep_time = max(0, self.interval - elapsed)
            
            if sleep_time > 0:
                time.sleep(sleep_time)

    def stop(self):
        self.running = False
        self.wait()


class MonitorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Arrow")
        self.resize(1400, 800)

        self.metric_titles = ["FPS", "Temp", "Mem", "GPU", "Power"]
        self.metric_deques = [deque(maxlen=MAX_POINTS) for _ in self.metric_titles]

        self.power_deques = {
            'power': self.metric_deques[self.metric_titles.index("Power")],
            'voltage': deque(maxlen=MAX_POINTS),
            'current': deque(maxlen=MAX_POINTS),
        }

        self.cpu_usage_deques = [deque(maxlen=MAX_POINTS) for _ in range(8)]
        self.cpu_freq_deques = [deque(maxlen=MAX_POINTS) for _ in range(8)]

        self.metric_series = []
        self.power_series = {}
        self.power_axes = {}

        self.metric_labels = []
        self.power_labels = {}

        self.cpu_usage_series = []
        self.cpu_freq_series = []
        self.cpu_usage_labels = []
        self.cpu_freq_labels = []

        self.data_log = []
        self.data_thread = None
        self.start_time = time.time()
        self.is_monitoring = False
        self.has_logged_data = False # Flag to prevent logging initial zero values
        
        # 累积 Jank 计数
        self.total_jank_count = 0
        self.total_big_jank_count = 0
        
        # 数据记录控制
        self.last_log_time = 0
        self.accumulated_data = {
            'fps_sum': 0, 'fps_count': 0,
            'temp_sum': 0, 'temp_count': 0,
            'mem_sum': 0, 'mem_count': 0,
            'gpu_sum': 0, 'gpu_count': 0,
            'power_sum': 0, 'power_count': 0,
            'voltage_sum': 0, 'voltage_count': 0,
            'current_sum': 0, 'current_count': 0,
            'jank_sum': 0, 'big_jank_sum': 0,
            'cpu_usages': [[] for _ in range(8)],
            'cpu_freqs': [[] for _ in range(8)]
        }

        self.ui_timer = QTimer(self)
        self.ui_timer.setInterval(UI_UPDATE_INTERVAL)
        self.ui_timer.timeout.connect(self.update_display)

        self.init_ui()

    def create_label(self, text="0", color="white"):
        label = QLabel(text)
        label.setFixedWidth(100)
        label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        label.setStyleSheet(f"background-color: black; color: {color}; padding: 2px; border-radius: 4px;")
        return label

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # --- Top Controls ---
        top_layout = QHBoxLayout()
        self.package_combo = QComboBox()
        top_layout.addWidget(QLabel("Package:"))
        top_layout.addWidget(self.package_combo)
        self.start_btn = QPushButton("開始監控")
        self.stop_btn = QPushButton("停止")
        self.export_btn = QPushButton("導出CSV")
        self.wifi_btn = QPushButton("開啟WiFi ADB")
        self.start_btn.clicked.connect(self.start_monitoring)
        self.stop_btn.clicked.connect(self.stop_monitoring)
        self.export_btn.clicked.connect(self.export_csv)
        self.wifi_btn.clicked.connect(self.enable_wifi)
        top_layout.addWidget(self.start_btn)
        top_layout.addWidget(self.stop_btn)
        top_layout.addWidget(self.export_btn)
        top_layout.addWidget(self.wifi_btn)
        main_layout.addLayout(top_layout)

        # --- Info Labels ---
        info_layout = QHBoxLayout()
        self.device_label = QLabel("設備: N/A")
        self.ip_label = QLabel("WiFi模式: N/A")
        self.fps_label = QLabel("FPS: N/A")
        self.jank_label = QLabel("Jank: 0")
        self.big_jank_label = QLabel("Big Jank: 0")
        self.temp_label = QLabel("溫度: N/A")
        self.mem_label = QLabel("記憶體: N/A")
        self.gpu_label = QLabel("GPU: N/A")
        self.power_label = QLabel("功耗(mW): N/A")
        self.voltage_label = QLabel("電壓(V): N/A")
        self.current_label = QLabel("電流(mA): N/A")
        self.monitor_time_label = QLabel("監控時間: 00:00:00")
        for label in [self.device_label, self.ip_label, self.fps_label, self.jank_label, 
                      self.big_jank_label, self.temp_label, self.mem_label, self.gpu_label,
                      self.power_label, self.voltage_label, self.current_label,
                      self.monitor_time_label]:
            info_layout.addWidget(label)
        main_layout.addLayout(info_layout)
        
        self.window_seconds = MAX_POINTS * DATA_COLLECTION_INTERVAL / 1000.0

        # --- Metric Charts (FPS, Temp, Mem, GPU, Power) ---
        metric_layout = QHBoxLayout()
        for title in self.metric_titles:
            chart = QChart()
            chart.setTitle(title)
            chart.setAnimationOptions(QChart.NoAnimation)
            
            axisX = QValueAxis(); axisX.setRange(0, self.window_seconds); axisX.setLabelFormat("%.0fs")
            axisY = QValueAxis()
            chart.addAxis(axisX, Qt.AlignBottom)
            chart.addAxis(axisY, Qt.AlignLeft)
            
            view = QChartView(chart)
            view.setRenderHint(QPainter.Antialiasing, False)
            view.setMinimumSize(200, 150)
            
            if title != "Power":
                chart_box = QVBoxLayout()
                chart_box.addWidget(view)
                axisY.setRange(0, 100)
                series = QLineSeries()
                chart.addSeries(series)
                series.attachAxis(axisX)
                series.attachAxis(axisY)
                label = self.create_label()
                chart_box.addWidget(label, alignment=Qt.AlignCenter)
                self.metric_series.append((series, axisY, axisX))
                self.metric_labels.append(label)
                metric_layout.addLayout(chart_box)
            else: # Combined Power Chart
                axisY.setTitleText("功耗 (mW)")
                axisY.setRange(0, 5000)
                
                power_series = QLineSeries(name="功耗 (mW)"); power_series.setColor(QColor(255, 102, 0))
                chart.addSeries(power_series); power_series.attachAxis(axisX); power_series.attachAxis(axisY)
                self.power_series['power'] = power_series
                
                axisY2 = QValueAxis(); axisY2.setTitleText("V / mA"); axisY2.setRange(0, 2000)
                chart.addAxis(axisY2, Qt.AlignRight)
                self.power_axes['secondary_y'] = axisY2

                voltage_series = QLineSeries(name="電壓 (V)"); voltage_series.setColor(QColor(0, 153, 255))
                chart.addSeries(voltage_series); voltage_series.attachAxis(axisX); voltage_series.attachAxis(axisY2)
                self.power_series['voltage'] = voltage_series
                
                current_series = QLineSeries(name="電流 (mA)"); current_series.setColor(QColor(0, 204, 0))
                chart.addSeries(current_series); current_series.attachAxis(axisX); current_series.attachAxis(axisY2)
                self.power_series['current'] = current_series
                
                self.power_axes['power_y'] = axisY
                self.power_axes['power_x'] = axisX

                power_label_col = QVBoxLayout()
                self.power_labels['power'] = self.create_label("0.0 mW")
                self.power_labels['voltage'] = self.create_label("0.0 V")
                self.power_labels['current'] = self.create_label("0.0 mA")
                power_label_col.addWidget(self.power_labels['power'])
                power_label_col.addWidget(self.power_labels['voltage'])
                power_label_col.addWidget(self.power_labels['current'])

                power_box_h = QHBoxLayout()
                power_box_h.addWidget(view)
                power_box_h.addLayout(power_label_col)
                metric_layout.addLayout(power_box_h)

        main_layout.addLayout(metric_layout)

        # --- CPU Charts ---
        cpu_layout = QVBoxLayout()
        # Usage Chart
        usage_chart = QChart(); usage_chart.setTitle("CPU 使用率 (%)"); usage_chart.setAnimationOptions(QChart.NoAnimation)
        axisX_u = QValueAxis(); axisX_u.setRange(0, self.window_seconds); axisX_u.setLabelFormat("%.0fs")
        axisY_u = QValueAxis(); axisY_u.setRange(0, 100)
        usage_chart.addAxis(axisX_u, Qt.AlignBottom); usage_chart.addAxis(axisY_u, Qt.AlignLeft)
        for i in range(8):
            s = QLineSeries(name=f"CPU{i}")
            usage_chart.addSeries(s); s.attachAxis(axisX_u); s.attachAxis(axisY_u)
            self.cpu_usage_series.append((s, axisY_u, axisX_u))
            self.cpu_usage_labels.append(self.create_label())
        usage_view = QChartView(usage_chart); usage_view.setRenderHint(QPainter.Antialiasing, False); usage_view.setMinimumHeight(220)
        usage_box = QHBoxLayout(); usage_box.addWidget(usage_view)
        usage_label_col = QVBoxLayout(); [usage_label_col.addWidget(lbl) for lbl in self.cpu_usage_labels]; usage_box.addLayout(usage_label_col)
        cpu_layout.addLayout(usage_box)
        
        # Freq Chart
        freq_chart = QChart(); freq_chart.setTitle("CPU 頻率 (MHz)"); freq_chart.setAnimationOptions(QChart.NoAnimation)
        axisX_f = QValueAxis(); axisX_f.setRange(0, self.window_seconds); axisX_f.setLabelFormat("%.0fs")
        axisY_f = QValueAxis(); axisY_f.setRange(0, 3000)
        freq_chart.addAxis(axisX_f, Qt.AlignBottom); freq_chart.addAxis(axisY_f, Qt.AlignLeft)
        for i in range(8):
            s = QLineSeries(name=f"Core{i}")
            freq_chart.addSeries(s); s.attachAxis(axisX_f); s.attachAxis(axisY_f)
            self.cpu_freq_series.append((s, axisY_f, axisX_f))
            self.cpu_freq_labels.append(self.create_label())
        freq_view = QChartView(freq_chart); freq_view.setRenderHint(QPainter.Antialiasing, False); freq_view.setMinimumHeight(220)
        freq_box = QHBoxLayout(); freq_box.addWidget(freq_view)
        freq_label_col = QVBoxLayout(); [freq_label_col.addWidget(lbl) for lbl in self.cpu_freq_labels]; freq_box.addLayout(freq_label_col)
        cpu_layout.addLayout(freq_box)

        main_layout.addLayout(cpu_layout)

    def enable_wifi(self):
        ip = per.enable_wifi_debug()
        if ip:
            self.ip_label.setText(f"WiFi模式: 開啟")
            QMessageBox.information(self, "WiFi ADB", f"WiFi 模式已啟動: {ip}")
        else:
            QMessageBox.warning(self, "WiFi ADB 失敗", "無法啟用 WiFi ADB, 請確認手機已透過 USB 連接。")

    def start_monitoring(self):
        if self.is_monitoring:
            return
        per.install_and_start_service()
        current_package = per.get_foreground_app()
        if not current_package:
            QMessageBox.warning(self, "錯誤", "無法取得前景應用程式。")
            return
        
        self.is_monitoring = True
        self.has_logged_data = False # 重置日誌標記
        self.total_jank_count = 0  # 重置累积 Jank 计数
        self.total_big_jank_count = 0  # 重置累积 Big Jank 计数
        self.last_log_time = time.time()  # 重置记录时间
        
        # 重置累积数据
        self.accumulated_data = {
            'fps_sum': 0, 'fps_count': 0,
            'temp_sum': 0, 'temp_count': 0,
            'mem_sum': 0, 'mem_count': 0,
            'gpu_sum': 0, 'gpu_count': 0,
            'power_sum': 0, 'power_count': 0,
            'voltage_sum': 0, 'voltage_count': 0,
            'current_sum': 0, 'current_count': 0,
            'jank_sum': 0, 'big_jank_sum': 0,
            'cpu_usages': [[] for _ in range(8)],
            'cpu_freqs': [[] for _ in range(8)]
        }
        
        self.package_combo.clear(); self.package_combo.addItem(current_package)
        if self.data_thread:
            self.data_thread.stop(); self.data_thread = None

        for dq in self.metric_deques: dq.clear()
        for dq in self.power_deques.values(): dq.clear()
        for dq in self.cpu_usage_deques: dq.clear()
        for dq in self.cpu_freq_deques: dq.clear()
        self.start_time = time.time()
        self.last_log_time = self.start_time
        
        self.data_thread = DataThread(interval_ms=DATA_COLLECTION_INTERVAL)
        self.data_thread.data_ready.connect(self.on_data_ready)
        self.data_thread.start()
        
        self.ui_timer.start()
        self.data_log.clear()
        self.monitor_time_label.setText("監控時間: 00:00:00")

    def stop_monitoring(self):
        if not self.is_monitoring:
            return
        self.is_monitoring = False
        if self.data_thread:
            self.data_thread.stop(); self.data_thread = None
        self.ui_timer.stop()

    def on_data_ready(self, info):
        if 'error' in info:
            print(f"[MonitorWindow] data error: {info['error']}")
            return
        
        # === 使用单调递增的时间，避免时间跳跃 ===
        current_time = time.time()
        elapsed_seconds = current_time - self.start_time
        
        # --- Update Labels Immediately ---
        if info.get('device'): self.device_label.setText(f"設備: {info['device']}")
        fps = info.get('fps', 0.0) or 0.0
        temp = info.get('temp', 0.0) or 0.0
        mem = info.get('mem', 0.0) or 0.0
        gpu = info.get('gpu', 0.0) or 0.0
        power_info = info.get('power_info', {})
        power_mW = abs(float(power_info.get('power_mW', 0) or 0))
        voltageV = float(power_info.get('voltage_V', 0) or 0)
        current_mA = abs(float(power_info.get('current_mA', 0) or 0))
        
        # === 修正 Jank 显示 - 累积计数 ===
        jank_increment = info.get('jank', 0)
        big_jank_increment = info.get('big_jank', 0)
        
        # 累加到总计数
        self.total_jank_count += jank_increment
        self.total_big_jank_count += big_jank_increment
        
        # 立即更新监控时间标签（使用实际经过的时间）
        h = int(elapsed_seconds // 3600)
        m = int((elapsed_seconds % 3600) // 60)
        s = int(elapsed_seconds % 60)
        self.monitor_time_label.setText(f"監控時間: {h:02}:{m:02}:{s:02}")
        
        self.fps_label.setText(f"FPS: {fps:.1f}")
        self.temp_label.setText(f"溫度: {temp:.1f}°C")
        self.mem_label.setText(f"記憶體: {mem:.1f}%")
        self.gpu_label.setText(f"GPU: {gpu:.1f}%")
        self.power_label.setText(f"功耗(mW): {power_mW:.2f}mW")
        self.voltage_label.setText(f"電壓(V): {voltageV:.3f}V")
        self.current_label.setText(f"電流(mA): {current_mA:.2f}mA")
        self.jank_label.setText(f"Jank: {self.total_jank_count}")
        self.big_jank_label.setText(f"Big Jank: {self.total_big_jank_count}")

        # --- Append data to deques (for charts) ---
        metrics = [fps, temp, mem, gpu]
        for i, v in enumerate(metrics):
            self.metric_deques[i].append((elapsed_seconds, float(v))) 

        self.power_deques['power'].append((elapsed_seconds, power_mW))
        self.power_deques['voltage'].append((elapsed_seconds, voltageV))
        self.power_deques['current'].append((elapsed_seconds, current_mA))
        
        usages = info.get('usages', [0]*8)
        freqs = info.get('freqs', [0]*8)
        for i in range(8):
            self.cpu_usage_deques[i].append((elapsed_seconds, float(usages[i] if i < len(usages) else 0.0)))
            self.cpu_freq_deques[i].append((elapsed_seconds, float(freqs[i] if i < len(freqs) else 0.0)))
        
        # === 优化数据记录：每秒记录一次平均值 ===
        if not self.has_logged_data and sum(usages) > 0:
            self.has_logged_data = True
        
        if self.has_logged_data:
            # 累积数据
            acc = self.accumulated_data
            acc['fps_sum'] += fps; acc['fps_count'] += 1
            acc['temp_sum'] += temp; acc['temp_count'] += 1
            acc['mem_sum'] += mem; acc['mem_count'] += 1
            acc['gpu_sum'] += gpu; acc['gpu_count'] += 1
            acc['power_sum'] += power_mW; acc['power_count'] += 1
            acc['voltage_sum'] += voltageV; acc['voltage_count'] += 1
            acc['current_sum'] += current_mA; acc['current_count'] += 1
            acc['jank_sum'] += jank_increment
            acc['big_jank_sum'] += big_jank_increment
            
            for i in range(8):
                if i < len(usages):
                    acc['cpu_usages'][i].append(usages[i])
                if i < len(freqs):
                    acc['cpu_freqs'][i].append(freqs[i])
            
            # 每秒写入一次数据
            time_since_last_log = current_time - self.last_log_time
            if time_since_last_log >= DATA_LOG_INTERVAL:
                now = time.strftime("%H:%M:%S")
                
                # 计算平均值
                avg_fps = acc['fps_sum'] / max(acc['fps_count'], 1)
                avg_temp = acc['temp_sum'] / max(acc['temp_count'], 1)
                avg_mem = acc['mem_sum'] / max(acc['mem_count'], 1)
                avg_gpu = acc['gpu_sum'] / max(acc['gpu_count'], 1)
                avg_power = acc['power_sum'] / max(acc['power_count'], 1)
                avg_voltage = acc['voltage_sum'] / max(acc['voltage_count'], 1)
                avg_current = acc['current_sum'] / max(acc['current_count'], 1)
                
                # CPU 平均值
                avg_cpu_usages = [
                    sum(acc['cpu_usages'][i]) / max(len(acc['cpu_usages'][i]), 1) 
                    if acc['cpu_usages'][i] else 0.0
                    for i in range(8)
                ]
                avg_cpu_freqs = [
                    sum(acc['cpu_freqs'][i]) / max(len(acc['cpu_freqs'][i]), 1) 
                    if acc['cpu_freqs'][i] else 0.0
                    for i in range(8)
                ]
                
                # 写入日志（使用累积的 Jank 值）
                self.data_log.append([
                    now, avg_fps, avg_temp, avg_mem, avg_gpu, 
                    avg_power, avg_voltage, avg_current,
                    acc['jank_sum'], acc['big_jank_sum']
                ] + avg_cpu_usages + avg_cpu_freqs)
                
                # 重置累积数据
                self.accumulated_data = {
                    'fps_sum': 0, 'fps_count': 0,
                    'temp_sum': 0, 'temp_count': 0,
                    'mem_sum': 0, 'mem_count': 0,
                    'gpu_sum': 0, 'gpu_count': 0,
                    'power_sum': 0, 'power_count': 0,
                    'voltage_sum': 0, 'voltage_count': 0,
                    'current_sum': 0, 'current_count': 0,
                    'jank_sum': 0, 'big_jank_sum': 0,
                    'cpu_usages': [[] for _ in range(8)],
                    'cpu_freqs': [[] for _ in range(8)]
                }
                # 更新 last_log_time，确保精确的 1 秒间隔
                self.last_log_time += DATA_LOG_INTERVAL
                
                # 如果累积了太多延迟（超过 2 秒），重新同步
                if current_time - self.last_log_time > 2.0:
                    self.last_log_time = current_time

    def update_display(self):
        if not self.metric_deques or not self.metric_deques[0]:
            return
        
        elapsed_seconds = self.metric_deques[0][-1][0]
        
        # 监控时间标签已在 on_data_ready 中更新，这里不再重复更新

        divisor, label_format = (60.0, "%.2fm") if elapsed_seconds > 60 else (1.0, "%.0fs")

        # 1. Standard Metrics (FPS, Temp, Mem, GPU)
        for i, (series_obj, axisY, axisX) in enumerate(self.metric_series):
            dq = self.metric_deques[i]
            if not dq: continue
            pts = [QPointF(px / divisor, py) for px, py in dq]
            series_obj.replace(pts)
            if pts:
                self.metric_labels[i].setText(f"{pts[-1].y():.1f}")
                maxy = max(p.y() for p in pts)
                axisY.setRange(0, max(10.0, maxy * 1.2))
                xmax = pts[-1].x()
                axisX.setRange(max(0, xmax - (self.window_seconds/divisor)), xmax)
                axisX.setLabelFormat(label_format)

        # 2. Combined Power Metric
        if self.power_deques['power']:
            power_pts = [QPointF(px/divisor, py) for px, py in self.power_deques['power']]
            self.power_series['power'].replace(power_pts)
            self.power_labels['power'].setText(f"{power_pts[-1].y():.2f} mW")
            self.power_axes['power_y'].setRange(0, max(500.0, max(p.y() for p in power_pts) * 1.2))
            
            voltage_pts = [QPointF(px/divisor, py) for px, py in self.power_deques['voltage']]
            self.power_series['voltage'].replace(voltage_pts)
            self.power_labels['voltage'].setText(f"{voltage_pts[-1].y():.3f} V")

            current_pts = [QPointF(px/divisor, py) for px, py in self.power_deques['current']]
            self.power_series['current'].replace(current_pts)
            self.power_labels['current'].setText(f"{current_pts[-1].y():.2f} mA")
            
            # Update secondary Y-axis
            if voltage_pts and current_pts:
                 max_secondary = max(p.y() for p in voltage_pts + current_pts)
                 self.power_axes['secondary_y'].setRange(0, max(10.0, max_secondary * 1.2))
            
            # Update shared X-axis
            xmax = power_pts[-1].x()
            self.power_axes['power_x'].setRange(max(0, xmax - (self.window_seconds/divisor)), xmax)
            self.power_axes['power_x'].setLabelFormat(label_format)

        def update_cpu_charts(series_list, deques, labels, unit):
            for i, (series_obj, axisY, axisX) in enumerate(series_list):
                dq = deques[i]
                if not dq: continue
                pts = [QPointF(px / divisor, py) for px, py in dq]
                series_obj.replace(pts)
                if pts:
                    labels[i].setText(f"{pts[-1].y():.1f}{unit}")
                    maxy = max(p.y() for p in pts)
                    # Set a reasonable default max Y value
                    default_max_y = 100 if '%' in unit else 2000 
                    axisY.setRange(0, max(default_max_y, maxy * 1.2))
                    xmax = pts[-1].x()
                    axisX.setRange(max(0, xmax - (self.window_seconds/divisor)), xmax)
                    axisX.setLabelFormat(label_format)

        # 3. CPU Usage & 4. CPU Freq
        update_cpu_charts(self.cpu_usage_series, self.cpu_usage_deques, self.cpu_usage_labels, "%")
        update_cpu_charts(self.cpu_freq_series, self.cpu_freq_deques, self.cpu_freq_labels, " MHz")

    def export_csv(self):
        if not self.data_log:
            QMessageBox.information(self, "導出", "沒有可導出的資料。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "儲存CSV", "", "CSV 檔案 (*.csv)")
        if path:
            with open(path, 'w', newline='', encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                header = ["Time", "FPS", "Temp", "Mem", "GPU(%)", "Power(mW)", "Voltage(V)", 
                          "Current(mA)", "Jank", "Big Jank"] + \
                         [f"CPU{i}%" for i in range(8)] + \
                         [f"Core{i}(MHz)" for i in range(8)]
                writer.writerow(header)
                writer.writerows(self.data_log)
            QMessageBox.information(self, "導出成功", "CSV 檔案已儲存。")

    def closeEvent(self, event):
        self.stop_monitoring()
        try:
            per.run_adb_command(["disconnect"])
            per.uninstall_service()
        except Exception as e:
            print(f"清理過程中發生例外: {e}")
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MonitorWindow()
    window.show()
    sys.exit(app.exec_())
