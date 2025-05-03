import re
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QMessageBox, QFileDialog
)
from PyQt5.QtChart import QChart, QChartView, QLineSeries, QValueAxis
from PyQt5.QtCore import Qt, QTimer, QPointF
import csv
import time
import sys
import math
import per 
class MonitorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Android Monitor")
        self.resize(1400, 800)

        self.cpu_usage_series = []
        self.cpu_freq_series = []
        self.cpu_usage_labels = []
        self.cpu_freq_labels = []
        self.metric_series = []
        self.metric_labels = []
        self.metric_titles = ["FPS", "Temp", "Mem", "Power"]
        self.data_log = []
        self.last_frame_time = None
        self.jank_count = 0
        self.big_jank_count = 0
        self.refresh_rate = 60.0
        self.frame_times = []

        self.monitor_seconds = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_data)

        self.monitor_time_timer = QTimer()
        self.monitor_time_timer.timeout.connect(self.update_monitor_time)

        self.init_ui()

    def create_label(self, text="0"):
        label = QLabel(text)
        label.setFixedWidth(80)
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
        self.ip_label = QLabel("WiFi IP：N/A")
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

        metric_layout = QHBoxLayout()
        for title in self.metric_titles:
            chart = QChart()
            chart.setTitle(title)
            series = QLineSeries()
            chart.addSeries(series)
            axisX = QValueAxis(); axisX.setRange(0, 50)
            axisY = QValueAxis(); axisY.setRange(0, 100)
            chart.addAxis(axisX, Qt.AlignBottom)
            chart.addAxis(axisY, Qt.AlignLeft)
            series.attachAxis(axisX)
            series.attachAxis(axisY)

            view = QChartView(chart)
            chart_box = QHBoxLayout(); chart_box.addWidget(view)
            label = self.create_label()
            chart_box.addWidget(label)

            self.metric_series.append((series, axisY))
            self.metric_labels.append(label)
            metric_layout.addLayout(chart_box)

        cpu_layout = QVBoxLayout()

        # CPU Usage Chart
        usage_chart = QChart(); usage_chart.setTitle("CPU 使用率 (%)")
        axisX = QValueAxis(); axisX.setRange(0, 60)
        axisY = QValueAxis(); axisY.setRange(0, 100)
        usage_chart.addAxis(axisX, Qt.AlignBottom)
        usage_chart.addAxis(axisY, Qt.AlignLeft)
        usage_labels = []

        for i in range(8):
            series = QLineSeries(name=f"CPU{i}")
            usage_chart.addSeries(series)
            series.attachAxis(axisX)
            series.attachAxis(axisY)
            self.cpu_usage_series.append(series)
            label = self.create_label()
            usage_labels.append(label)

        usage_view = QChartView(usage_chart)
        usage_box = QHBoxLayout(); usage_box.addWidget(usage_view)
        label_column = QVBoxLayout()
        for label in usage_labels:
            label_column.addWidget(label)
        usage_box.addLayout(label_column)
        self.cpu_usage_labels = usage_labels
        cpu_layout.addLayout(usage_box)

        # CPU Freq Chart
        freq_chart = QChart(); freq_chart.setTitle("CPU 頻率 (MHz)")
        axisX2 = QValueAxis(); axisX2.setRange(0, 60)
        axisY2 = QValueAxis(); axisY2.setRange(0, 3000)
        freq_chart.addAxis(axisX2, Qt.AlignBottom)
        freq_chart.addAxis(axisY2, Qt.AlignLeft)
        freq_labels = []

        for i in range(8):
            series = QLineSeries(name=f"Core{i}")
            freq_chart.addSeries(series)
            series.attachAxis(axisX2)
            series.attachAxis(axisY2)
            self.cpu_freq_series.append(series)
            label = self.create_label()
            freq_labels.append(label)

        freq_view = QChartView(freq_chart)
        freq_box = QHBoxLayout(); freq_box.addWidget(freq_view)
        freq_label_column = QVBoxLayout()
        for label in freq_labels:
            freq_label_column.addWidget(label)
        freq_box.addLayout(freq_label_column)
        self.cpu_freq_labels = freq_labels
        cpu_layout.addLayout(freq_box)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        layout = QVBoxLayout(self.central_widget)
        layout.addLayout(top_layout)
        layout.addLayout(info_layout)
        layout.addLayout(metric_layout)
        layout.addLayout(cpu_layout)

    def enable_wifi(self):
        ip = per.enable_wifi_debug()
        if ip:
            self.ip_label.setText(f"WiFi IP：{ip}")
            QMessageBox.information(self, "WiFi ADB", f"WiFi 模式已啟動：{ip}")
        else:
            QMessageBox.warning(self, "WiFi ADB 失敗", "無法啟用 WiFi ADB，請確認已透過 USB 正確連接手機")

    def start_monitoring(self):
        self.package_combo.clear()
        for series, _ in self.metric_series:
            series.clear()
        for s in self.cpu_usage_series + self.cpu_freq_series:
            s.clear()
        self.current_package = per.get_foreground_app()
        if not self.current_package:
            QMessageBox.warning(self, "錯誤", "無法取得前景應用")
            return
        self.package_combo.addItem(self.current_package)
        self.device_label.setText(f"設備：{per.get_device_name()}")
        self.data_log.clear()
        self.jank_count = 0
        self.big_jank_count = 0
        self.refresh_rate = per.get_refresh_rate()
        self.frame_times = []
        self.timer.start(1000)
        self.monitor_seconds = 0
        self.monitor_time_label.setText("監控時間：00:00:00")
        self.monitor_time_timer.start(1000)

    def stop_monitoring(self):
        self.timer.stop()
        self.monitor_time_timer.stop()
        self.monitor_seconds = 0
        self.monitor_time_label.setText("監控時間：00:00:00")

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "儲存CSV", "", "CSV Files (*.csv)")
        if path:
            with open(path, 'w', newline='', encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["Time"] + self.metric_titles + ["Jank", "Big Jank"] +
                                [f"CPU{i}%" for i in range(8)] + [f"Core{i}(MHz)" for i in range(8)])
                writer.writerows(self.data_log)
            QMessageBox.information(self, "導出成功", "CSV 檔案已儲存")

    def update_monitor_time(self):
        self.monitor_seconds += 1
        h = self.monitor_seconds // 3600
        m = (self.monitor_seconds % 3600) // 60
        s = self.monitor_seconds % 60
        self.monitor_time_label.setText(f"監控時間：{h:02}:{m:02}:{s:02}")

    def update_data(self):
        now = time.strftime("%H:%M:%S")
        fps = per.get_fps(self.current_package)
        usages, freqs = per.get_cpu_usage_and_freq()
        temp = per.get_cpu_temp()
        mem = per.get_mem_usage()
        v, c, power = per.get_power_info()

        self.fps_label.setText(f"FPS：{fps:.1f}")
        self.temp_label.setText(f"Temp：{temp:.1f}°C")
        self.mem_label.setText(f"Memory：{mem:.1f}%")
        self.power_label.setText(f"Power：{power:.2f}W")

        # 記錄 frame timestamps

        # 計算 jank / big jank 根據 frame timestamp 差異
        
        refresh_rate = per.get_refresh_rate()                     # Hz
        refresh_period_ns = int(1_000_000_000 / refresh_rate)

        layer = per.get_surfaceflinger_target_layer(self.current_package)
        triplets = per.dump_surfaceflinger_latency_triplets(layer)
        self.jank_count, self.big_jank_count = per.calculate_jank_by_vsync_triplets(triplets, refresh_period_ns)
        self.jank_label.setText(f"Jank：{self.jank_count}")
        self.big_jank_label.setText(f"Big Jank：{self.big_jank_count}")
        metrics = [fps, temp, mem, power]
        self.data_log.append([now] + metrics + [self.jank_count, self.big_jank_count] + usages + freqs)

        for i, value in enumerate(metrics):
            series, axisY = self.metric_series[i]
            index = series.count()
            series.append(index, value)
            self.metric_labels[i].setText(f"{value:.1f}")
            if index > 50:
                series.chart().axisX().setRange(index - 50, index)
            ymax = max([series.at(j).y() for j in range(series.count())], default=100) * 1.2
            axisY.setRange(0, ymax)

        for i, usage in enumerate(usages):
            if i < len(self.cpu_usage_series):
                series = self.cpu_usage_series[i]
                index = series.count()
                series.append(index, usage)
                self.cpu_usage_labels[i].setText(f"{usage:.1f}%")
                if index > 60:
                    series.chart().axisX().setRange(index - 60, index)

        for i, freq in enumerate(freqs):
            if i < len(self.cpu_freq_series):
                series = self.cpu_freq_series[i]
                index = series.count()
                series.append(index, freq)
                self.cpu_freq_labels[i].setText(f"{freq:.0f} MHz")
                if index > 60:
                    series.chart().axisX().setRange(index - 60, index)
    def closeEvent(self, event):
        # print("應用程式關閉，自動斷開 WiFi ADB...")
        per.run_adb_command(["disconnect"])
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MonitorWindow()
    window.show()
    sys.exit(app.exec_())
