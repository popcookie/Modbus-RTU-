"""
阈值管理窗口 & 写寄存器界面
============================
使用 tkinter 实现独立的 GUI 窗口，包含：
  - 阈值管理选项卡：显示所有设备，可修改高限/低限，保存后立即生效
  - 写寄存器选项卡：选择从站、寄存器、值、数据类型，执行 Modbus 写操作
"""

import logging
import threading
import tkinter as tk
from tkinter import ttk, messagebox

logger = logging.getLogger("OxygenMonitor.ThresholdWindow")


class ThresholdWindow:
    """阈值管理窗口（含写寄存器功能）"""

    def __init__(self, config: dict, modbus_manager=None,
                 save_callback=None):
        """
        参数:
            config: 配置字典（会被动态修改）
            modbus_manager: ModbusManager 实例（用于写寄存器）
            save_callback: 保存配置的回调函数
        """
        self.config = config
        self.modbus_manager = modbus_manager
        self.save_callback = save_callback
        self.root = None
        self.threshold_entries = {}  # {name: {"high": entry, "low": entry}}

    def run(self):
        """启动阈值管理窗口（阻塞直到关闭）"""
        self.root = tk.Tk()
        self.root.title("阈值管理与写寄存器 - 氧气项目监控系统")
        self.root.geometry("650x550")
        self.root.resizable(True, True)

        # 标签页
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=5, pady=5)

        # 阈值管理标签页
        threshold_frame = tk.Frame(notebook)
        notebook.add(threshold_frame, text="阈值管理")

        # 写寄存器标签页
        write_frame = tk.Frame(notebook)
        notebook.add(write_frame, text="写寄存器")

        self._build_threshold_tab(threshold_frame)
        self._build_write_tab(write_frame)

        # 底部状态栏
        status_frame = tk.Frame(self.root)
        status_frame.pack(fill="x", side="bottom", padx=5, pady=5)

        self.status_label = tk.Label(
            status_frame, text="就绪",
            anchor="w", font=("Microsoft YaHei", 9),
            fg="#666"
        )
        self.status_label.pack(side="left")

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    # ==================== 阈值管理选项卡 ====================

    def _build_threshold_tab(self, parent):
        """构建阈值管理选项卡内容"""
        # 标题
        title_label = tk.Label(
            parent,
            text="设备报警阈值管理",
            font=("Microsoft YaHei", 14, "bold"),
            pady=10
        )
        title_label.pack()

        # 说明
        tip_label = tk.Label(
            parent,
            text="修改阈值后点击「保存阈值」即可立即生效，无需重启程序",
            font=("Microsoft YaHei", 9),
            fg="#555", pady=5
        )
        tip_label.pack()

        # 设备列表框架（可滚动）
        canvas_frame = tk.Frame(parent)
        canvas_frame.pack(fill="both", expand=True, padx=10, pady=5)

        canvas = tk.Canvas(canvas_frame, highlightthickness=0)
        scrollbar = tk.Scrollbar(canvas_frame, orient="vertical",
                                 command=canvas.yview)
        scrollable_frame = tk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 表头
        header_frame = tk.Frame(scrollable_frame, bg="#e9ecef")
        header_frame.pack(fill="x", pady=(0, 5))

        headers = [
            ("设备名称", 18),
            ("类型", 12),
            ("从站", 6),
            ("高限", 14),
            ("低限", 14)
        ]
        for text, width in headers:
            lbl = tk.Label(header_frame, text=text,
                           font=("Microsoft YaHei", 10, "bold"),
                           bg="#e9ecef", width=width, anchor="w",
                           padx=5, pady=3)
            lbl.pack(side="left")

        # 设备行
        type_map = {"flow": "流量计", "temp": "热电偶",
                    "pressure": "压力传感器"}

        devices = self.config.get("devices", [])
        for device in devices:
            row = tk.Frame(scrollable_frame)
            row.pack(fill="x", pady=2)

            name = device.get("name", "")
            dtype = device.get("type", "unknown")
            slave_id = device.get("slave_id", "")

            # 设备名称
            tk.Label(row, text=name, width=18, anchor="w",
                     font=("Microsoft YaHei", 10)).pack(side="left", padx=5)

            # 类型
            tk.Label(row, text=type_map.get(dtype, dtype),
                     width=12, anchor="w",
                     font=("Microsoft YaHei", 10)).pack(side="left", padx=5)

            # 从站
            tk.Label(row, text=str(slave_id), width=6, anchor="center",
                     font=("Microsoft YaHei", 10)).pack(side="left", padx=5)

            # 高限输入
            high_entry = tk.Entry(row, width=14,
                                  font=("Microsoft YaHei", 10))
            high_value = device.get("high_limit")
            if high_value is not None:
                high_entry.insert(0, str(high_value))
            high_entry.pack(side="left", padx=5)

            # 低限输入
            low_entry = tk.Entry(row, width=14,
                                 font=("Microsoft YaHei", 10))
            low_value = device.get("low_limit")
            if low_value is not None:
                low_entry.insert(0, str(low_value))
            low_entry.pack(side="left", padx=5)

            self.threshold_entries[name] = {
                "high": high_entry,
                "low": low_entry
            }

        # 保存按钮
        btn_frame = tk.Frame(parent)
        btn_frame.pack(pady=10)

        save_btn = tk.Button(
            btn_frame, text="💾 保存阈值",
            font=("Microsoft YaHei", 12, "bold"),
            bg="#28a745", fg="white",
            padx=20, pady=5,
            activebackground="#218838", activeforeground="white",
            command=self._save_thresholds
        )
        save_btn.pack(side="left", padx=10)

        reload_btn = tk.Button(
            btn_frame, text="🔄 重新加载",
            font=("Microsoft YaHei", 12, "bold"),
            bg="#007bff", fg="white",
            padx=20, pady=5,
            activebackground="#0069d9", activeforeground="white",
            command=self._reload_thresholds
        )
        reload_btn.pack(side="left", padx=10)

    def _save_thresholds(self):
        """保存阈值到配置并通知主程序"""
        try:
            devices = self.config.get("devices", [])
            for device in devices:
                name = device.get("name", "")
                if name in self.threshold_entries:
                    entries = self.threshold_entries[name]

                    high_str = entries["high"].get().strip()
                    if high_str and high_str != "":
                        try:
                            device["high_limit"] = float(high_str)
                        except ValueError:
                            messagebox.showerror(
                                "输入错误",
                                f"设备「{name}」的高限值无效: {high_str}"
                            )
                            return
                    else:
                        device["high_limit"] = None

                    low_str = entries["low"].get().strip()
                    if low_str and low_str != "":
                        try:
                            device["low_limit"] = float(low_str)
                        except ValueError:
                            messagebox.showerror(
                                "输入错误",
                                f"设备「{name}」的低限值无效: {low_str}"
                            )
                            return
                    else:
                        device["low_limit"] = None

            # 保存配置文件
            if self.save_callback:
                self.save_callback(self.config)

            self.status_label.config(
                text="阈值已保存并生效", fg="#28a745"
            )
            logger.info("阈值已保存到配置文件")

            messagebox.showinfo("成功", "阈值已保存，立即生效！")

        except Exception as e:
            logger.error("保存阈值失败: %s", e)
            messagebox.showerror("错误", f"保存失败: {e}")

    def _reload_thresholds(self):
        """重新从 config 字典加载阈值到界面"""
        devices = self.config.get("devices", [])
        for device in devices:
            name = device.get("name", "")
            if name in self.threshold_entries:
                entries = self.threshold_entries[name]

                entries["high"].delete(0, tk.END)
                high_value = device.get("high_limit")
                if high_value is not None:
                    entries["high"].insert(0, str(high_value))

                entries["low"].delete(0, tk.END)
                low_value = device.get("low_limit")
                if low_value is not None:
                    entries["low"].insert(0, str(low_value))

        self.status_label.config(text="阈值已重新加载", fg="#007bff")

    # ==================== 写寄存器选项卡 ====================

    def _build_write_tab(self, parent):
        """构建写寄存器选项卡内容"""
        # 标题
        title_label = tk.Label(
            parent,
            text="Modbus 写寄存器操作",
            font=("Microsoft YaHei", 14, "bold"),
            pady=10
        )
        title_label.pack()

        # 表单框架
        form_frame = tk.Frame(parent)
        form_frame.pack(padx=30, pady=20, fill="x")

        # 从站地址
        row1 = tk.Frame(form_frame)
        row1.pack(fill="x", pady=8)
        tk.Label(row1, text="从站地址:", font=("Microsoft YaHei", 11),
                 width=14, anchor="e").pack(side="left", padx=5)
        self.slave_var = tk.StringVar(value="1")
        self.slave_combo = ttk.Combobox(
            row1, textvariable=self.slave_var, width=30,
            font=("Microsoft YaHei", 11), state="normal"
        )
        # 填充从站列表
        devices = self.config.get("devices", [])
        slave_list = [str(d["slave_id"]) for d in devices]
        self.slave_combo["values"] = slave_list
        if slave_list:
            self.slave_var.set(slave_list[0])
        self.slave_combo.pack(side="left", padx=5)

        # 寄存器地址
        row2 = tk.Frame(form_frame)
        row2.pack(fill="x", pady=8)
        tk.Label(row2, text="寄存器地址:", font=("Microsoft YaHei", 11),
                 width=14, anchor="e").pack(side="left", padx=5)
        self.register_var = tk.StringVar(value="0")
        reg_entry = tk.Entry(row2, textvariable=self.register_var,
                             font=("Microsoft YaHei", 11), width=32)
        reg_entry.pack(side="left", padx=5)

        # 数据类型
        row3 = tk.Frame(form_frame)
        row3.pack(fill="x", pady=8)
        tk.Label(row3, text="数据类型:", font=("Microsoft YaHei", 11),
                 width=14, anchor="e").pack(side="left", padx=5)
        self.dtype_var = tk.StringVar(value="int16")
        dtype_combo = ttk.Combobox(
            row3, textvariable=self.dtype_var, width=30,
            font=("Microsoft YaHei", 11), state="readonly"
        )
        dtype_combo["values"] = [
            "int16 (16位整数)",
            "int32 (32位整数)",
            "float (32位浮点数)"
        ]
        dtype_combo.current(0)
        dtype_combo.pack(side="left", padx=5)

        # 写入值
        row4 = tk.Frame(form_frame)
        row4.pack(fill="x", pady=8)
        tk.Label(row4, text="写入值:", font=("Microsoft YaHei", 11),
                 width=14, anchor="e").pack(side="left", padx=5)
        self.value_var = tk.StringVar(value="")
        value_entry = tk.Entry(row4, textvariable=self.value_var,
                               font=("Microsoft YaHei", 11), width=32)
        value_entry.pack(side="left", padx=5)

        # 写入按钮
        btn_frame = tk.Frame(parent)
        btn_frame.pack(pady=15)

        write_btn = tk.Button(
            btn_frame, text="✏️ 写入寄存器",
            font=("Microsoft YaHei", 12, "bold"),
            bg="#dc3545", fg="white",
            padx=20, pady=8,
            activebackground="#c82333", activeforeground="white",
            command=self._execute_write
        )
        write_btn.pack(side="left", padx=10)

        clear_btn = tk.Button(
            btn_frame, text="🗑️ 清空",
            font=("Microsoft YaHei", 12),
            bg="#6c757d", fg="white",
            padx=20, pady=8,
            activebackground="#5a6268", activeforeground="white",
            command=lambda: self.value_var.set("")
        )
        clear_btn.pack(side="left", padx=10)

        # 结果文本框
        result_frame = tk.LabelFrame(parent, text="操作结果",
                                      font=("Microsoft YaHei", 10))
        result_frame.pack(padx=20, pady=10, fill="both", expand=True)

        self.result_text = tk.Text(
            result_frame, height=8,
            font=("Consolas", 10),
            state="disabled", wrap="word"
        )
        scrollbar_result = tk.Scrollbar(
            result_frame, orient="vertical",
            command=self.result_text.yview
        )
        self.result_text.configure(yscrollcommand=scrollbar_result.set)
        self.result_text.pack(side="left", fill="both", expand=True,
                              padx=5, pady=5)
        scrollbar_result.pack(side="right", fill="y")

    def _execute_write(self):
        """执行写寄存器操作"""
        slave_str = self.slave_var.get().strip()
        register_str = self.register_var.get().strip()
        value_str = self.value_var.get().strip()
        dtype_str = self.dtype_var.get()

        # 验证输入
        if not slave_str:
            self._log_result("错误: 请输入从站地址\n")
            return
        if not register_str:
            self._log_result("错误: 请输入寄存器地址\n")
            return
        if not value_str:
            self._log_result("错误: 请输入写入值\n")
            return

        try:
            slave_id = int(slave_str)
            register_addr = int(register_str)
        except ValueError:
            self._log_result("错误: 地址必须是整数\n")
            return

        if slave_id < 1 or slave_id > 247:
            self._log_result("错误: 从站地址范围 1~247\n")
            return

        if self.modbus_manager is None:
            self._log_result("错误: Modbus 管理器未初始化\n")
            return

        if not self.modbus_manager.connected:
            self._log_result("错误: Modbus 未连接，无法写入\n")
            return

        # 根据数据类型写入
        self._log_result(f"正在写入 从站={slave_id}, 寄存器={register_addr}, "
                         f"值={value_str}, 类型={dtype_str} ...\n")

        success = False
        try:
            if "int16" in dtype_str or "16位" in dtype_str:
                value = int(float(value_str))
                success = self.modbus_manager.write_register(
                    slave_id, register_addr, value
                )

            elif "int32" in dtype_str or "32位" in dtype_str:
                value = int(float(value_str))
                high = (value >> 16) & 0xFFFF
                low = value & 0xFFFF
                success = self.modbus_manager.write_registers(
                    slave_id, register_addr, [high, low]
                )

            elif "float" in dtype_str or "浮点" in dtype_str:
                value = float(value_str)
                registers = self.modbus_manager.float_to_registers(value)
                success = self.modbus_manager.write_registers(
                    slave_id, register_addr, registers
                )

            if success:
                logger.info("GUI 写寄存器成功: 从站=%d, 寄存器=%d, "
                            "值=%s", slave_id, register_addr, value_str)
                self._log_result("写入成功！\n")
            else:
                self._log_result("写入失败，请检查设备和连接\n")

        except (ValueError, TypeError) as e:
            self._log_result(f"数值转换错误: {e}\n")
        except Exception as e:
            self._log_result(f"写入异常: {e}\n")

    def _log_result(self, message: str):
        """向结果文本框追加消息"""
        self.result_text.config(state="normal")
        self.result_text.insert("end", message)
        self.result_text.see("end")
        self.result_text.config(state="disabled")

    def _on_close(self):
        """关闭窗口时的处理"""
        logger.info("阈值管理窗口关闭")
        if self.root:
            self.root.destroy()


# ==================== 独立运行（测试） ====================

if __name__ == "__main__":
    import sys
    import os
    import json

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    # 加载配置
    config_path = "config.json"
    if not os.path.exists(config_path):
        # 创建测试配置
        config = {
            "devices": [
                {"slave_id": 1, "type": "flow", "register": 0,
                 "name": "氧气流量计", "high_limit": 100.0, "low_limit": 0.0},
                {"slave_id": 2, "type": "flow", "register": 0,
                 "name": "氮气流量计", "high_limit": 80.0, "low_limit": 0.0},
                {"slave_id": 3, "type": "temp", "register": 1,
                 "name": "反应釜温度", "high_limit": 85.0, "low_limit": 10.0},
                {"slave_id": 4, "type": "pressure", "register": 2,
                 "name": "罐体压力", "high_limit": 1.2, "low_limit": 0.1}
            ]
        }
    else:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

    window = ThresholdWindow(config,
                              save_callback=lambda c: print("配置已保存"))
    window.run()