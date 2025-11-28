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
UI_UPDATE_INTERVAL = 500  # Milliseconds for UI refresh
DATA_THREAD_INTERVAL = 10 # Milliseconds for data collection

class DataThread(QThread):
    data_ready = pyqtSignal(dict)

    def __init__(self, interval_ms=500):
        super().__init__()
        self.interval = interval_ms / 1000.0
        self.running = True

    def run(self):
        while self.running:
            try:
                info = {}
                # 获取前景应用
                foreground_app = per.get_foreground_app()
                info['fps'] = per.get_fps(foreground_app)
                
                # CPU 相关
                usages, freqs = per.get_cpu_usage_and_freq()
                info['usages'] = usages
                info['freqs'] = freqs
                
                # GPU、温度、内存
                info['gpu'] = per.GPU_Usage()
                info['temp'] = per.get_battery_temp()
                info['mem'] = per.get_mem_usage()
                
                # 电源数据
                info['power_info'] = per.get_power_data(per.get_device_ip()) or {}
                
                # 刷新率
                info['refresh_rate'] = per.get_refresh_rate()
                
                # === 修正 Jank 计算部分 ===
                # 1. 先获取目标 layer 名称
                layer_name = per.get_surfaceflinger_target_layer(foreground_app)
                
                # 2. 如果成功获取到 layer，则获取 triplets 数据
                triplets = []
                if layer_name:
                    # 注意：这里应该调用 dump_layer_stats 或类似函数获取实际的 triplets
                    # 根据您的 per.py，可能需要一个新函数来获取 triplets
                    # 暂时假设 get_surfaceflinger_target_layer 返回的是 layer name
                    # 需要添加一个函数来获取 vsync triplets
                    try:
                        # 您可能需要在 per.py 中添加 get_vsync_triplets 函数
                        if hasattr(per, 'get_vsync_triplets'):
                            triplets = per.get_vsync_triplets(layer_name)
                        else:
                            # 临时方案：使用 dump_layer_stats 的数据构造 triplets
                            # 实际应用中需要完整的 triplets 数据 (a, b, c)
                            triplets = []
                    except Exception as e:
                        print(f"[DataThread] Failed to get triplets: {e}")
                        triplets = []
                
                # 3. 计算 Jank
                jank_count = 0
                big_jank_count = 0
                if triplets and len(triplets) > 0:
                    refresh_period_ns = int(1_000_000_000 / (info['refresh_rate'] or 60.0))
                    jank_count, big_jank_count = per.calculate_jank_by_vsync_triplets(triplets, refresh_period_ns)
                
                info['jank'] = jank_count
                info['big_jank'] = big_jank_count
                info['device'] = per.get_device_name()
                info['ip'] = per.get_device_ip() if hasattr(per, 'get_device_ip') else None
                
            except Exception as e:
                print(f"[DataThread] exception: {e}")
                info = {'error': str(e)}
            
            self.data_ready.emit(info)
            time.sleep(self.interval)

    def stop(self):
        self.running = False
        self.wait()


class MonitorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Arrow Performance Monitor")
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
        
        self.window_seconds = MAX_POINTS * DATA_THREAD_INTERVAL / 1000.0

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
        self.package_combo.clear(); self.package_combo.addItem(current_package)
        if self.data_thread:
            self.data_thread.stop(); self.data_thread = None

        for dq in self.metric_deques: dq.clear()
        for dq in self.power_deques.values(): dq.clear()
        for dq in self.cpu_usage_deques: dq.clear()
        for dq in self.cpu_freq_deques: dq.clear()
        self.start_time = time.time()
        
        self.data_thread = DataThread(interval_ms=DATA_THREAD_INTERVAL)
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
        
        elapsed_seconds = time.time() - self.start_time
        
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
        
        # === 修正 Jank 显示 ===
        jank = info.get('jank', 0)
        big_jank = info.get('big_jank', 0)
        
        self.fps_label.setText(f"FPS: {fps:.1f}")
        self.temp_label.setText(f"溫度: {temp:.1f}°C")
        self.mem_label.setText(f"記憶體: {mem:.1f}%")
        self.gpu_label.setText(f"GPU: {gpu:.1f}%")
        self.power_label.setText(f"功耗(mW): {power_mW:.2f}mW")
        self.voltage_label.setText(f"電壓(V): {voltageV:.3f}V")
        self.current_label.setText(f"電流(mA): {current_mA:.2f}mA")
        self.jank_label.setText(f"Jank: {jank}")
        self.big_jank_label.setText(f"Big Jank: {big_jank}")

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
        
        # FIX: Only start logging after receiving the first valid CPU data
        if not self.has_logged_data and sum(usages) > 0:
            self.has_logged_data = True
            
        if self.has_logged_data:
            now = time.strftime("%H:%M:%S")
            self.data_log.append([now, fps, temp, mem, gpu, power_mW, voltageV, current_mA, jank, big_jank] + usages + freqs)

    def update_display(self):
        if not self.metric_deques or not self.metric_deques[0]:
            return
        
        elapsed_seconds = self.metric_deques[0][-1][0]
        
        # FIX: Update monitor time label from the same data source as charts
        h = int(elapsed_seconds // 3600)
        m = int((elapsed_seconds % 3600) // 60)
        s = int(elapsed_seconds % 60)
        self.monitor_time_label.setText(f"監控時間: {h:02}:{m:02}:{s:02}")

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
