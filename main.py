# optimized_monitor.py
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
from PyQt5.QtGui import QPainter

import per

MAX_POINTS = 2000      # 每個 series 最多保留多少個點 (代表圖表顯示的時間窗口)
UI_UPDATE_INTERVAL = 500  # ms - UI 更新頻率
DATA_THREAD_INTERVAL = 10  # ms - background polling interval


class DataThread(QThread):
    """背景執行緒：每 interval 秒抓取所有 per.* 資料並一次發回主線程。"""
    data_ready = pyqtSignal(dict)

    def __init__(self, interval_ms=500):
        super().__init__()
        self.interval = interval_ms / 500.0
        self.running = True

    def run(self):
        while self.running:
            try:
                # 把所有耗時的 per 呼叫集中在背景執行緒
                info = {}
                info['fps'] = per.get_fps(per.get_foreground_app())
                usages, freqs = per.get_cpu_usage_and_freq()
                info['usages'] = usages
                info['freqs'] = freqs
                info['temp'] = per.get_battery_temp()
                info['mem'] = per.get_mem_usage()
                info['power_info'] = per.get_power_data(per.get_device_ip()) or {}
                info['refresh_rate'] = per.get_refresh_rate()
                layer = per.get_surfaceflinger_target_layer(per.get_foreground_app())
                triplets = per.get_surfaceflinger_target_layer(layer)
                refresh_period_ns = int(1_000_000_000 / (info['refresh_rate'] or 60.0))
                jank_count, big_jank_count = per.calculate_jank_by_vsync_triplets(triplets, refresh_period_ns)
                info['jank'] = jank_count
                info['big_jank'] = big_jank_count
                info['device'] = per.get_device_name()
                info['ip'] = per.get_device_ip() if hasattr(per, 'get_device_ip') else None
            except Exception as e:
                print("[DataThread] exception:", e)
                info = {'error': str(e)}
            self.data_ready.emit(info)
            time.sleep(self.interval)

    def stop(self):
        self.running = False
        self.wait()


class MonitorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Android Monitor - Optimized")
        self.resize(1400, 800)

        # 資料結構：每個 series 使用 deque 儲存 (時間秒數, y值)
        self.metric_titles = ["FPS", "Temp", "Mem", "Power"]
        self.metric_deques = [deque(maxlen=MAX_POINTS) for _ in self.metric_titles]
        self.cpu_usage_deques = [deque(maxlen=MAX_POINTS) for _ in range(8)]
        self.cpu_freq_deques = [deque(maxlen=MAX_POINTS) for _ in range(8)]

        self.metric_series = []
        self.cpu_usage_series = []
        self.cpu_freq_series = []

        self.metric_labels = []
        self.cpu_usage_labels = []
        self.cpu_freq_labels = []

        self.data_log = []
        self.data_thread = None

        self.ui_timer = QTimer()
        self.ui_timer.setInterval(UI_UPDATE_INTERVAL)
        self.ui_timer.timeout.connect(lambda: None)

        self.init_ui()

    def create_label(self, text="0"):
        label = QLabel(text)
        label.setFixedWidth(90)
        label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        label.setStyleSheet("background-color: black; color: white; padding: 2px; border-radius: 4px;")
        return label

    def init_ui(self):
        main_layout = QVBoxLayout()
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

        self.device_label = QLabel("設備：N/A")
        self.ip_label = QLabel("WiFi Mode：N/A")
        self.fps_label = QLabel("FPS：N/A")
        self.jank_label = QLabel("Jank：0")
        self.big_jank_label = QLabel("Big Jank：0")
        self.temp_label = QLabel("Temp：N/A")
        self.mem_label = QLabel("Memory：N/A")
        self.power_label = QLabel("Power：N/A")
        self.monitor_time_label = QLabel("監控時間：00:00:00")

        info_layout = QHBoxLayout()
        for label in [self.device_label, self.ip_label, self.fps_label,
                      self.jank_label, self.big_jank_label,
                      self.temp_label, self.mem_label,
                      self.power_label, self.monitor_time_label]:
            info_layout.addWidget(label)

        window_seconds = MAX_POINTS * DATA_THREAD_INTERVAL / 1000.0

        metric_layout = QHBoxLayout()
        for title in self.metric_titles:
            chart = QChart()
            chart.setTitle(title)
            chart.setAnimationOptions(QChart.NoAnimation)
            axisX = QValueAxis(); axisX.setRange(0, window_seconds); axisX.setLabelFormat("%.0fs")
            axisY = QValueAxis(); axisY.setRange(0, 100)
            chart.addAxis(axisX, Qt.AlignBottom)
            chart.addAxis(axisY, Qt.AlignLeft)
            series = QLineSeries()
            chart.addSeries(series)
            series.attachAxis(axisX)
            series.attachAxis(axisY)
            view = QChartView(chart)
            view.setRenderHint(QPainter.Antialiasing, False)
            view.setMinimumSize(200, 150)
            chart_box = QHBoxLayout(); chart_box.addWidget(view)
            label = self.create_label()
            chart_box.addWidget(label)
            self.metric_series.append((series, axisY, axisX))
            self.metric_labels.append(label)
            metric_layout.addLayout(chart_box)

        cpu_layout = QVBoxLayout()
        usage_chart = QChart()
        usage_chart.setTitle("CPU 使用率 (%)")
        usage_chart.setAnimationOptions(QChart.NoAnimation)
        axisX_u = QValueAxis(); axisX_u.setRange(0, window_seconds); axisX_u.setLabelFormat("%.0fs")
        axisY_u = QValueAxis(); axisY_u.setRange(0, 100)
        usage_chart.addAxis(axisX_u, Qt.AlignBottom)
        usage_chart.addAxis(axisY_u, Qt.AlignLeft)
        for i in range(8):
            s = QLineSeries(name=f"CPU{i}")
            usage_chart.addSeries(s)
            s.attachAxis(axisX_u)
            s.attachAxis(axisY_u)
            self.cpu_usage_series.append((s, axisY_u, axisX_u))
            lbl = self.create_label()
            self.cpu_usage_labels.append(lbl)
        usage_view = QChartView(usage_chart)
        usage_view.setRenderHint(QPainter.Antialiasing, False)
        usage_view.setMinimumHeight(220)
        usage_box = QHBoxLayout(); usage_box.addWidget(usage_view)
        label_column = QVBoxLayout()
        for label in self.cpu_usage_labels: label_column.addWidget(label)
        usage_box.addLayout(label_column)
        cpu_layout.addLayout(usage_box)
        
        freq_chart = QChart()
        freq_chart.setTitle("CPU 頻率 (MHz)")
        freq_chart.setAnimationOptions(QChart.NoAnimation)
        axisX_f = QValueAxis(); axisX_f.setRange(0, window_seconds); axisX_f.setLabelFormat("%.0fs")
        axisY_f = QValueAxis(); axisY_f.setRange(0, 3000)
        freq_chart.addAxis(axisX_f, Qt.AlignBottom)
        freq_chart.addAxis(axisY_f, Qt.AlignLeft)
        for i in range(8):
            s = QLineSeries(name=f"Core{i}")
            freq_chart.addSeries(s)
            s.attachAxis(axisX_f)
            s.attachAxis(axisY_f)
            self.cpu_freq_series.append((s, axisY_f, axisX_f))
            lbl = self.create_label()
            self.cpu_freq_labels.append(lbl)
        freq_view = QChartView(freq_chart)
        freq_view.setRenderHint(QPainter.Antialiasing, False)
        freq_view.setMinimumHeight(220)
        freq_box = QHBoxLayout(); freq_box.addWidget(freq_view)
        freq_label_column = QVBoxLayout()
        for label in self.cpu_freq_labels: freq_label_column.addWidget(label)
        freq_box.addLayout(freq_label_column)
        cpu_layout.addLayout(freq_box)

        central = QWidget()
        self.setCentralWidget(central)
        main_v = QVBoxLayout(central)
        main_v.addLayout(top_layout)
        main_v.addLayout(info_layout)
        main_v.addLayout(metric_layout)
        main_v.addLayout(cpu_layout)

        self.ui_timer.start()

    def enable_wifi(self):
        ip = per.enable_wifi_debug()
        if ip:
            self.ip_label.setText(f"WiFi Mode：{'ON'}")
            QMessageBox.information(self, "WiFi ADB", f"WiFi 模式已啟動：{ip}")
        else:
            QMessageBox.warning(self, "WiFi ADB 失敗", "無法啟用 WiFi ADB，請確認已透過 USB 正確連接手機")

    def start_monitoring(self):
        per.install_and_start_service()
        current_package = per.get_foreground_app()
        if not current_package:
            QMessageBox.warning(self, "錯誤", "無法取得前景應用")
            return
        self.current_package = current_package
        self.package_combo.clear()
        self.package_combo.addItem(self.current_package)
        if self.data_thread:
            self.data_thread.stop()
            self.data_thread = None

        # --- 重置數據和時間 ---
        for dq in self.metric_deques: dq.clear()
        for dq in self.cpu_usage_deques: dq.clear()
        for dq in self.cpu_freq_deques: dq.clear()
        self.start_time = time.time()
        
        self.data_thread = DataThread(interval_ms=DATA_THREAD_INTERVAL)
        self.data_thread.data_ready.connect(self.on_data_ready)
        self.data_thread.start()

        self.data_log.clear()
        self.jank_count = 0
        self.big_jank_count = 0
        self.monitor_seconds = 0
        self.monitor_time_label.setText("監控時間：00:00:00")
        self.monitor_time_timer = QTimer()
        self.monitor_time_timer.setInterval(1000)
        self.monitor_time_timer.timeout.connect(self._update_monitor_time)
        self.monitor_time_timer.start()

    def stop_monitoring(self):
        if self.data_thread:
            self.data_thread.stop()
            self.data_thread = None
        if hasattr(self, 'monitor_time_timer'):
            self.monitor_time_timer.stop()
        self.monitor_time_label.setText("監控時間：00:00:00")

    def _update_monitor_time(self):
        self.monitor_seconds = getattr(self, 'monitor_seconds', 0) + 1
        h = self.monitor_seconds // 3600
        m = (self.monitor_seconds % 3600) // 60
        s = self.monitor_seconds % 60
        self.monitor_time_label.setText(f"監控時間：{h:02}:{m:02}:{s:02}")

    def on_data_ready(self, info):
        if 'error' in info:
            print("[MonitorWindow] data error:", info['error'])
            return
        if info.get('device'):
            self.device_label.setText(f"設備：{info['device']}")
        
        fps = info.get('fps', 0.0) or 0.0
        temp = info.get('temp', 0.0) or 0.0
        mem = info.get('mem', 0.0) or 0.0
        power_mW = float(info.get('power_info', {}).get('power_mW', 0) or 0)
        power_W = abs(power_mW)

        self.fps_label.setText(f"FPS：{fps:.1f}")
        self.temp_label.setText(f"Temp：{temp:.1f}°C")
        self.mem_label.setText(f"Memory：{mem:.1f}%")
        self.power_label.setText(f"Power：{power_W:.2f}mW")
        self.jank_label.setText(f"Jank：{info.get('jank', 0)}")
        self.big_jank_label.setText(f"Big Jank：{info.get('big_jank', 0)}")

        now = time.strftime("%H:%M:%S")
        usages = info.get('usages', [0]*8)
        freqs = info.get('freqs', [0]*8)
        self.data_log.append([now, fps, temp, mem, power_W, info.get('jank',0), info.get('big_jank',0)] + usages + freqs)

        # --- 核心修改：使用秒數作為X值，並動態調整單位 ---
        if not hasattr(self, 'start_time'):
            self.start_time = time.time()
        elapsed_seconds = time.time() - self.start_time

        # 根據總秒數直接決定單位和格式，無需狀態旗標
        if elapsed_seconds > 60:
            divisor = 60.0
            label_format = "%.2fm"  # e.g., "1.25m"
        else:
            divisor = 1.0
            label_format = "%.0fs"  # e.g., "55s"
        
        # 數據統一用秒存儲
        metrics = [fps, temp, mem, power_W]
        for i, v in enumerate(metrics):
            self.metric_deques[i].append((elapsed_seconds, float(v)))
        for i in range(8):
            self.cpu_usage_deques[i].append((elapsed_seconds, float(usages[i] if i < len(usages) else 0.0)))
            self.cpu_freq_deques[i].append((elapsed_seconds, float(freqs[i] if i < len(freqs) else 0.0)))
        
        window_duration_secs = MAX_POINTS * DATA_THREAD_INTERVAL / 1000.0
        window_duration_current_unit = window_duration_secs / divisor

        # --- 更新所有圖表 ---
        # Metric series
        for i, (series_obj, axisY, axisX) in enumerate(self.metric_series):
            deque = self.metric_deques[i]
            if not deque: continue
            pts = [QPointF(px / divisor, py) for px, py in deque]
            series_obj.replace(pts)
            if pts:
                self.metric_labels[i].setText(f"{pts[-1].y():.1f}")
                maxy = max(p.y() for p in pts)
                axisY.setRange(0, max(10.0, maxy * 1.2))
                xmax = pts[-1].x()
                axisX.setRange(max(0, xmax - window_duration_current_unit), xmax)
                axisX.setLabelFormat(label_format)

        # CPU usage series
        for i, (series_obj, axisY, axisX) in enumerate(self.cpu_usage_series):
            deque = self.cpu_usage_deques[i]
            if not deque: continue
            pts = [QPointF(px / divisor, py) for px, py in deque]
            series_obj.replace(pts)
            if pts:
                self.cpu_usage_labels[i].setText(f"{pts[-1].y():.1f}%")
                maxy = max(p.y() for p in pts)
                axisY.setRange(0, max(50.0, maxy * 1.2))
                xmax = pts[-1].x()
                axisX.setRange(max(0, xmax - window_duration_current_unit), xmax)
                axisX.setLabelFormat(label_format)

        # CPU freq series
        for i, (series_obj, axisY, axisX) in enumerate(self.cpu_freq_series):
            deque = self.cpu_freq_deques[i]
            if not deque: continue
            pts = [QPointF(px / divisor, py) for px, py in deque]
            series_obj.replace(pts)
            if pts:
                self.cpu_freq_labels[i].setText(f"{pts[-1].y():.0f} MHz")
                maxy = max(p.y() for p in pts)
                axisY.setRange(0, max(1000.0, maxy * 1.2))
                xmax = pts[-1].x()
                axisX.setRange(max(0, xmax - window_duration_current_unit), xmax)
                axisX.setLabelFormat(label_format)

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "儲存CSV", "", "CSV Files (*.csv)")
        if path:
            with open(path, 'w', newline='', encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["Time", "FPS", "Temp", "Mem", "Power", "Jank", "Big Jank"] +
                                [f"CPU{i}%" for i in range(8)] + [f"Core{i}(MHz)" for i in range(8)])
                for row in self.data_log:
                    writer.writerow(row)
            QMessageBox.information(self, "導出成功", "CSV 檔案已儲存")

    def closeEvent(self, event):
        per.uninstall_service()
        if self.data_thread:
            self.data_thread.stop()
            self.data_thread = None
        try:
            per.run_adb_command(["disconnect"])
        except Exception:
            pass
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MonitorWindow()
    window.show()
    sys.exit(app.exec_())
