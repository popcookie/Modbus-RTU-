"""
氧气项目实时监控系统 - 主程序
============================
功能：
  - 读取 config.json 配置
  - 连接 Modbus RTU 总线上所有设备
  - 周期性采集数据并存入 CSV 文件
  - 实时动态曲线显示（matplotlib，3 个子图）
  - 报警检测与弹窗
  - 阈值管理窗口（独立 GUI）
  - 优雅退出

启动方式：
  python data_logger.py
"""

import sys
import os
import json
import logging
import logging.handlers
import threading
import time
import csv
from datetime import datetime
from collections import deque
import queue

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.ticker import MaxNLocator
import tkinter as tk

# 导入自定义模块
from modbus_manager import ModbusManager
from alarm_manager import AlarmManager

# 创建一个隐藏的 tk 根窗口，供报警弹窗（Toplevel）使用
_root_tk = tk.Tk()
_root_tk.withdraw()  # 隐藏根窗口


# ==================== 全局变量 ====================

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "config.json")
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# 确保目录存在
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# 配置日志
LOG_FILE = os.path.join(LOG_DIR, "log.txt")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("OxygenMonitor")


# ==================== 配置加载 ====================

def load_config() -> dict:
    """加载配置文件"""
    if not os.path.exists(CONFIG_PATH):
        logger.error("配置文件 %s 不存在！", CONFIG_PATH)
        sys.exit(1)

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    logger.info("配置文件加载成功，共 %d 个设备",
                len(config.get("devices", [])))
    return config


def save_config(config: dict):
    """保存配置文件"""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        logger.info("配置文件已保存")
    except Exception as e:
        logger.error("保存配置文件失败: %s", e)


# ==================== CSV 数据记录 ====================

class DataLogger:
    """CSV 数据记录器：将采集数据写入每日 CSV 文件"""

    def __init__(self, config: dict):
        self.config = config
        self.csv_file = None
        self.csv_writer = None
        self.current_date = None
        self.column_names = []
        self._open_csv()

    def _get_filename(self) -> str:
        """根据当前日期生成 CSV 文件名"""
        date_str = datetime.now().strftime("%Y%m%d")
        return os.path.join(DATA_DIR, f"oxygen_data_{date_str}.csv")

    def _open_csv(self):
        """打开（或新建）CSV 文件并写入表头"""
        devices = self.config.get("devices", [])
        self.column_names = ["Timestamp"] + [d["name"] for d in devices]

        today = datetime.now().strftime("%Y%m%d")
        filename = self._get_filename()

        # 如果日期变了，关闭旧文件打开新文件
        if self.current_date != today:
            self.close()
            self.current_date = today
            file_exists = os.path.exists(filename)
            self.csv_file = open(filename, "a", newline="", encoding="utf-8")
            self.csv_writer = csv.writer(self.csv_file)
            if not file_exists or os.path.getsize(filename) == 0:
                self.csv_writer.writerow(self.column_names)
                self.csv_file.flush()
                logger.info("创建 CSV 文件: %s", filename)
            else:
                logger.info("打开 CSV 文件: %s", filename)

    def write_row(self, timestamp: str, values: list):
        """写入一行数据"""
        # 检查是否需要切换日期文件
        today = datetime.now().strftime("%Y%m%d")
        if self.current_date != today:
            self._open_csv()
        if self.csv_writer is None:
            return
        try:
            self.csv_writer.writerow([timestamp] + values)
            self.csv_file.flush()
        except Exception as e:
            logger.error("写入 CSV 失败: %s", e)

    def close(self):
        """关闭 CSV 文件"""
        if self.csv_file:
            try:
                self.csv_file.close()
            except Exception:
                pass
            self.csv_file = None
            self.csv_writer = None


# ==================== 数据采集线程 ====================

class DataAcquisitionThread(threading.Thread):
    """数据采集线程：周期性读取所有设备数据"""

    def __init__(self, modbus_mgr: ModbusManager, config: dict,
                 data_queue: queue.Queue, stop_event: threading.Event):
        super().__init__(daemon=True, name="DataAcquisition")
        self.modbus_mgr = modbus_mgr
        self.config = config
        self.data_queue = data_queue
        self.stop_event = stop_event

    def run(self):
        logger.info("数据采集线程启动")
        while not self.stop_event.is_set():
            try:
                devices = self.config.get("devices", [])
                timestamp = datetime.now()
                ts_str = timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

                row_data = {
                    "timestamp": timestamp,
                    "ts_str": ts_str,
                    "values": {},
                    "success": {}
                }

                for device in devices:
                    name = device["name"]
                    slave_id = device["slave_id"]
                    register = device.get("register", 0)

                    registers = self.modbus_mgr.read_register(
                        slave_id, register, count=1
                    )

                    if registers is not None and len(registers) > 0:
                        raw_value = registers[0]
                        # 根据设备类型转换数值
                        dtype = device.get("type", "")
                        if dtype in ("pressure",) and len(registers) >= 2:
                            raw_value = ModbusManager.register_to_float(
                                registers
                            )
                        row_data["values"][name] = raw_value
                        row_data["success"][name] = True
                    else:
                        row_data["values"][name] = float("nan")
                        row_data["success"][name] = False

                self.data_queue.put(row_data)

            except Exception as e:
                logger.error("数据采集异常: %s", e)

            # 等待下一轮采集
            interval = self.config.get("interval_seconds", 1)
            self.stop_event.wait(timeout=max(interval, 0.1))

        logger.info("数据采集线程退出")


# ==================== 实时曲线窗口 ====================

class RealtimePlotWindow:
    """实时曲线窗口：使用 matplotlib 显示 3 个子图"""

    def __init__(self, config: dict, data_queue: queue.Queue,
                 stop_event: threading.Event):
        self.config = config
        self.data_queue = data_queue
        self.stop_event = stop_event
        self.data_buffer = {}
        self.time_buffer = deque(maxlen=60)
        self.max_points = 60  # 显示最近 60 秒数据

        # 颜色列表
        self.colors = plt.cm.tab10.colors

        # 分类设备
        self.devices_by_type = {"flow": [], "temp": [], "pressure": []}
        for device in config.get("devices", []):
            dtype = device.get("type", "flow")
            if dtype in self.devices_by_type:
                self.devices_by_type[dtype].append(device)
            self.data_buffer[device["name"]] = deque(maxlen=self.max_points)

        self._setup_plot()

    def _setup_plot(self):
        """初始化 matplotlib 图形和子图"""
        plt.ion()  # 交互模式
        self.fig, self.axes = plt.subplots(3, 1, figsize=(12, 9),
                                            sharex=True)
        self.fig.canvas.manager.set_window_title("氧气项目实时监控")

        type_titles = {"flow": "流量计", "temp": "热电偶",
                       "pressure": "压力传感器"}
        type_units = {"flow": "流量", "temp": "温度 (℃)",
                      "pressure": "压力 (MPa)"}

        self.lines = {}  # {device_name: line_object}
        self.ax_idx = {"flow": 0, "temp": 1, "pressure": 2}

        for dtype in ["flow", "temp", "pressure"]:
            ax = self.axes[self.ax_idx[dtype]]
            devices = self.devices_by_type[dtype]
            ax.set_title(type_titles.get(dtype, dtype),
                         fontsize=13, fontweight="bold")
            ax.set_ylabel(type_units.get(dtype, ""), fontsize=10)
            ax.grid(True, alpha=0.3)
            ax.set_xlim(-60, 0)

            for i, device in enumerate(devices):
                color = self.colors[i % len(self.colors)]
                line, = ax.plot([], [], label=device["name"],
                                color=color, linewidth=1.5, marker="o",
                                markersize=2)
                self.lines[device["name"]] = line

            if devices:
                ax.legend(loc="upper left", fontsize=8, framealpha=0.7)

        self.axes[-1].set_xlabel("时间 (秒)", fontsize=11)

        self.fig.tight_layout(pad=3.0)

    def update_plot(self, frame):
        """matplotlib 动画回调：更新曲线数据"""
        # 从队列中获取最新数据
        try:
            while True:
                row_data = self.data_queue.get_nowait()
                timestamp = row_data["timestamp"]
                self.time_buffer.append(timestamp)

                for name in self.data_buffer:
                    if name in row_data["values"]:
                        self.data_buffer[name].append(
                            row_data["values"][name]
                        )
        except queue.Empty:
            pass

        if not self.time_buffer:
            return []

        # 计算相对时间（秒）
        ref_time = self.time_buffer[-1]
        times = [(t - ref_time).total_seconds()
                 for t in self.time_buffer]

        all_lines = []
        for name, line in self.lines.items():
            buffer = self.data_buffer[name]
            if len(buffer) > 0:
                data_len = min(len(times), len(buffer))
                x_data = times[-data_len:]
                y_data = list(buffer)[-data_len:]
                line.set_data(x_data, y_data)
            all_lines.append(line)

        # 动态调整 y 轴范围
        for dtype in ["flow", "temp", "pressure"]:
            ax = self.axes[self.ax_idx[dtype]]
            devices = self.devices_by_type[dtype]
            if not devices:
                continue
            all_vals = []
            for d in devices:
                buf = self.data_buffer[d["name"]]
                vals = [v for v in buf if v is not None and
                        not (isinstance(v, float) and v != v)]
                all_vals.extend(vals)
            if all_vals:
                y_min, y_max = min(all_vals), max(all_vals)
                margin = max((y_max - y_min) * 0.1, 0.2)
                ax.set_ylim(y_min - margin, y_max + margin)

        self.fig.canvas.draw_idle()
        return all_lines

    def start(self):
        """启动动画循环"""
        self.ani = animation.FuncAnimation(
            self.fig, self.update_plot,
            interval=500, blit=False, cache_frame_data=False
        )
        plt.show(block=True)


# ==================== 主程序 ====================

def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("氧气项目实时监控系统启动")
    logger.info("=" * 60)

    # 加载配置
    config = load_config()

    # 创建停止事件（用于优雅退出）
    stop_event = threading.Event()

    # 创建数据队列
    data_queue = queue.Queue(maxsize=100)

    # 初始化报警管理器
    alarm_mgr = AlarmManager(config)

    # 初始化 Modbus 管理器并连接
    modbus_mgr = ModbusManager(config)
    if not modbus_mgr.connect():
        logger.error("Modbus 连接失败，请检查设备连接和配置")
        # 即使连接失败也继续运行，允许查看界面和修改配置

    # 从站扫描（如果启用）
    if config.get("scan_enabled", False) and modbus_mgr.connected:
        scan_thread = threading.Thread(
            target=modbus_mgr.scan_slaves,
            args=(1, 247),
            daemon=True,
            name="SlaveScan"
        )
        scan_thread.start()
        logger.info("从站扫描已在后台启动")

    # 初始化数据记录器
    data_logger = DataLogger(config)

    # 启动数据采集线程
    acq_thread = DataAcquisitionThread(
        modbus_mgr, config, data_queue, stop_event
    )
    acq_thread.start()

    # 启动数据处理线程（负责写入 CSV 和报警检查）
    def process_data():
        """数据处理线程：从队列取数据，写入 CSV，检查报警"""
        logger.info("数据处理线程启动")
        while not stop_event.is_set():
            try:
                row_data = data_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                devices = config.get("devices", [])
                values_list = []

                for device in devices:
                    name = device["name"]
                    val = row_data["values"].get(name, float("nan"))
                    if isinstance(val, (int, float)):
                        values_list.append(
                            f"{val:.3f}" if val == val else "NaN"
                        )
                    else:
                        values_list.append(str(val))

                    # 报警检查
                    alarm_mgr.check_and_alert(device, val,
                                              row_data["timestamp"])

                # 写入 CSV
                data_logger.write_row(row_data["ts_str"], values_list)

            except Exception as e:
                logger.error("数据处理异常: %s", e)

    process_thread = threading.Thread(
        target=process_data, daemon=True, name="DataProcess"
    )
    process_thread.start()

    # 尝试启动阈值管理窗口（在独立线程中）
    threshold_window = None
    try:
        # 延迟导入，避免循环依赖
        from threshold_window import ThresholdWindow
    except ImportError:
        logger.warning("无法导入 threshold_window.py，跳过阈值窗口")
    else:
        def start_threshold_window():
            nonlocal threshold_window
            try:
                threshold_window = ThresholdWindow(
                    config, modbus_mgr,
                    save_callback=lambda cfg: save_config(cfg)
                )
                threshold_window.run()
            except Exception as e:
                logger.error("阈值窗口启动失败: %s", e)

        thresh_thread = threading.Thread(
            target=start_threshold_window, daemon=True,
            name="ThresholdWindow"
        )
        thresh_thread.start()
        logger.info("阈值管理窗口已启动")

    # 启动实时曲线窗口（在主线程，阻塞直到关闭）
    plot_window = RealtimePlotWindow(config, data_queue, stop_event)

    # 处理窗口关闭事件
    def on_close(event):
        logger.info("曲线窗口关闭，正在停止系统...")
        stop_event.set()
        data_logger.close()
        modbus_mgr.disconnect()
        alarm_mgr.close_all_alarms()
        logger.info("系统已安全退出")
        sys.exit(0)

    plot_window.fig.canvas.mpl_connect("close_event", on_close)

    try:
        plot_window.start()
    except KeyboardInterrupt:
        logger.info("接收到 Ctrl+C 信号")
    finally:
        stop_event.set()
        data_logger.close()
        modbus_mgr.disconnect()
        alarm_mgr.close_all_alarms()
        logger.info("系统已安全退出")


if __name__ == "__main__":
    main()