"""
报警管理模块
============
功能：阈值判断、弹窗警告、日志记录。
支持多设备同时报警，不阻塞主程序采集。
"""

import logging
import threading
import tkinter as tk
from tkinter import ttk
from datetime import datetime

logger = logging.getLogger("OxygenMonitor.Alarm")


class AlarmManager:
    """报警管理类：负责阈值判断和弹窗警告"""

    def __init__(self, config: dict):
        """
        初始化报警管理器
        参数:
            config: 配置字典，包含 devices 列表及各自的阈值
        """
        self.config = config
        self.alarm_windows = []      # 当前打开的报警窗口列表
        self.alarm_lock = threading.Lock()
        self.alarm_states = {}       # 记录每个设备的报警状态，避免重复弹窗
        # 格式: {device_name: {"high": False, "low": False}}

    def update_config(self, config: dict):
        """更新配置引用（阈值动态修改后调用）"""
        self.config = config

    def check_device(self, device_name: str, device_type: str,
                     current_value, high_limit, low_limit,
                     timestamp=None) -> list:
        """
        检查单个设备是否超出阈值
        参数:
            device_name: 设备名称
            device_type: 设备类型 (flow/temp/pressure)
            current_value: 当前值
            high_limit: 高限
            low_limit: 低限
            timestamp: 时间戳（可选）
        返回:
            报警类型列表: ["high", "low"] 或 []
        """
        if current_value is None or (isinstance(current_value, float) and
                                      (current_value != current_value)):
            return []  # NaN 不报警

        alarms = []

        try:
            val = float(current_value)
        except (TypeError, ValueError):
            return []

        if high_limit is not None:
            try:
                if val > float(high_limit):
                    alarms.append("high")
            except (TypeError, ValueError):
                pass

        if low_limit is not None:
            try:
                if val < float(low_limit):
                    alarms.append("low")
            except (TypeError, ValueError):
                pass

        # 检查报警状态变化，避免重复弹窗
        triggered = []
        now = timestamp or datetime.now()

        with self.alarm_lock:
            if device_name not in self.alarm_states:
                self.alarm_states[device_name] = {"high": False, "low": False}

            for alarm_type in alarms:
                if not self.alarm_states[device_name].get(alarm_type, False):
                    self.alarm_states[device_name][alarm_type] = True
                    triggered.append(alarm_type)
                    logger.warning(
                        "报警触发: 设备=%s, 类型=%s, 方向=%s, "
                        "当前值=%.3f, 高限=%.3f, 低限=%.3f",
                        device_name, device_type, alarm_type,
                        val,
                        float(high_limit) if high_limit is not None else -1,
                        float(low_limit) if low_limit is not None else -1
                    )

            # 恢复正常时清除报警状态
            for alarm_type in ["high", "low"]:
                if alarm_type not in alarms:
                    if self.alarm_states[device_name].get(alarm_type, False):
                        logger.info("报警恢复: 设备=%s, 方向=%s, 当前值=%.3f",
                                     device_name, alarm_type, val)
                    self.alarm_states[device_name][alarm_type] = False

        return triggered

    def show_alarm_popup(self, device_name: str, device_type: str,
                         current_value, high_limit, low_limit,
                         alarm_types: list, timestamp=None):
        """
        弹出报警窗口（在独立线程中运行，不阻塞主程序）
        参数:
            device_name: 设备名称
            device_type: 设备类型
            current_value: 当前值
            high_limit: 高限
            low_limit: 低限
            alarm_types: 报警类型列表
            timestamp: 时间戳
        """
        if timestamp is None:
            timestamp = datetime.now()

        alarm_thread = threading.Thread(
            target=self._create_alarm_window,
            args=(device_name, device_type, current_value,
                  high_limit, low_limit, alarm_types, timestamp),
            daemon=True
        )
        alarm_thread.start()

    def _create_alarm_window(self, device_name: str, device_type: str,
                              current_value, high_limit, low_limit,
                              alarm_types: list, timestamp):
        """在独立线程中创建 tkinter 报警弹窗"""
        try:
            window = tk.Toplevel()
            window.title("⚠️ 报警 - " + device_name)
            window.geometry("420x280")
            window.configure(bg="#fff3cd")
            window.resizable(False, False)

            # 设置窗口置顶
            window.attributes("-topmost", True)

            with self.alarm_lock:
                self.alarm_windows.append(window)

            # 类型中文映射
            type_map = {
                "flow": "流量计",
                "temp": "热电偶",
                "pressure": "压力传感器"
            }
            type_cn = type_map.get(device_type, device_type)

            # 标题
            title_label = tk.Label(
                window,
                text="⚠️ 报警触发",
                font=("Microsoft YaHei", 16, "bold"),
                fg="#dc3545",
                bg="#fff3cd"
            )
            title_label.pack(pady=(15, 10))

            # 信息框架
            info_frame = tk.Frame(window, bg="#fff3cd")
            info_frame.pack(padx=20, pady=10, fill="both", expand=True)

            info_lines = [
                ("设备名称：", device_name),
                ("设备类型：", type_cn),
                ("当前值：", f"{current_value:.3f}" if isinstance(
                    current_value, (int, float)) else str(current_value)),
                ("高限阈值：", f"{high_limit:.3f}" if high_limit is not None
                 else "未设置"),
                ("低限阈值：", f"{low_limit:.3f}" if low_limit is not None
                 else "未设置"),
                ("报警类型：", ", ".join(alarm_types)),
                ("超限时间：", timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3])
            ]

            for label_text, value_text in info_lines:
                row_frame = tk.Frame(info_frame, bg="#fff3cd")
                row_frame.pack(fill="x", pady=3)
                lbl = tk.Label(row_frame, text=label_text,
                               font=("Microsoft YaHei", 10, "bold"),
                               fg="#856404", bg="#fff3cd",
                               width=12, anchor="e")
                lbl.pack(side="left")
                val = tk.Label(row_frame, text=value_text,
                               font=("Microsoft YaHei", 10),
                               fg="#856404", bg="#fff3cd",
                               anchor="w")
                val.pack(side="left", padx=(5, 0))

            # 警告提示
            tip_label = tk.Label(
                window,
                text="请及时检查设备状态！",
                font=("Microsoft YaHei", 9, "italic"),
                fg="#856404",
                bg="#fff3cd"
            )
            tip_label.pack(pady=(5, 5))

            # 关闭按钮
            def close_window():
                try:
                    with self.alarm_lock:
                        if window in self.alarm_windows:
                            self.alarm_windows.remove(window)
                    window.destroy()
                except Exception:
                    pass

            btn = tk.Button(
                window, text="确认", command=close_window,
                font=("Microsoft YaHei", 11, "bold"),
                bg="#dc3545", fg="white",
                padx=30, pady=5,
                activebackground="#c82333", activeforeground="white"
            )
            btn.pack(pady=(5, 15))

            window.protocol("WM_DELETE_WINDOW", close_window)
            window.mainloop()

        except Exception as e:
            logger.error("创建报警窗口时出错: %s", e)

    def check_and_alert(self, device: dict, current_value,
                        timestamp=None) -> list:
        """
        综合检查：判断阈值并弹窗
        参数:
            device: 设备配置字典
            current_value: 当前值
            timestamp: 时间戳
        返回:
            触发的报警类型列表
        """
        name = device.get("name", f"Slave-{device.get('slave_id')}")
        dtype = device.get("type", "unknown")
        high = device.get("high_limit")
        low = device.get("low_limit")

        alarms = self.check_device(name, dtype, current_value,
                                    high, low, timestamp)
        if alarms:
            self.show_alarm_popup(name, dtype, current_value,
                                   high, low, alarms, timestamp)
        return alarms

    def close_all_alarms(self):
        """关闭所有报警窗口"""
        with self.alarm_lock:
            windows = list(self.alarm_windows)
            self.alarm_windows.clear()

        for window in windows:
            try:
                window.destroy()
            except Exception:
                pass

        logger.info("已关闭所有报警窗口，共 %d 个", len(windows))