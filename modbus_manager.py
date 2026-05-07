"""
Modbus RTU 通信管理模块
=======================
功能：管理 Modbus RTU 通信，包括自动端口探测、从站扫描、读寄存器和写寄存器。
所有设备并联到同一根 RS485 总线，共用一个 COM 口。
"""

import serial
import serial.tools.list_ports
import logging
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException

logger = logging.getLogger("OxygenMonitor.Modbus")


class ModbusManager:
    """Modbus RTU 通信管理类"""

    def __init__(self, config: dict):
        self.config = config
        self.client = None
        self.connected = False
        self.available_ports = []
        self.found_slaves = []

    @staticmethod
    def list_serial_ports() -> list:
        """列出系统中所有可用的串口"""
        ports = []
        try:
            for port in serial.tools.list_ports.comports():
                ports.append({
                    "device": port.device,
                    "description": port.description,
                    "hwid": port.hwid
                })
        except Exception as e:
            logger.warning("列出串口时出错: %s", e)
        return ports

    def auto_detect_port(self, baudrate_list=None):
        """自动探测 Modbus 设备所在的总线端口"""
        if baudrate_list is None:
            baudrate_list = [9600, 19200, 38400, 115200]

        ports = self.list_serial_ports()
        devices = [p["device"] for p in ports]
        logger.info("系统可用串口: %s", devices)
        self.available_ports = devices

        for port_info in ports:
            port = port_info["device"]
            for baudrate in baudrate_list:
                logger.info("尝试端口 %s @ %d bps...", port, baudrate)
                try:
                    test_client = ModbusSerialClient(
                        port=port, baudrate=baudrate,
                        bytesize=8, parity="N", stopbits=1, timeout=0.5
                    )
                    if test_client.connect():
                        try:
                            result = test_client.read_holding_registers(
                                address=0, count=1, slave=1
                            )
                            if not result.isError():
                                logger.info(
                                    "检测到 Modbus 设备: %s @ %d bps",
                                    port, baudrate
                                )
                                test_client.close()
                                self.config["serial"]["port"] = port
                                self.config["serial"]["baudrate"] = baudrate
                                return port
                        except Exception:
                            pass
                        test_client.close()
                except Exception as e:
                    logger.debug("尝试 %s @ %d 失败: %s", port, baudrate, e)

        logger.warning("自动探测未找到任何 Modbus 设备")
        return None

    def connect(self) -> bool:
        """建立 Modbus RTU 连接"""
        serial_cfg = self.config.get("serial", {})
        port = serial_cfg.get("port")

        if port is None or port == "":
            logger.info("未指定端口，开始自动探测...")
            detected_port = self.auto_detect_port()
            if detected_port is None:
                logger.error("自动探测失败，请手动配置端口")
                return False
            port = detected_port

        parity_map = {
            "N": "N", "E": "E", "O": "O",
            "None": "N", "Even": "E", "Odd": "O"
        }
        parity_str = str(serial_cfg.get("parity", "N")).capitalize()
        parity = parity_map.get(parity_str, "N")

        try:
            self.client = ModbusSerialClient(
                port=port,
                baudrate=serial_cfg.get("baudrate", 9600),
                bytesize=serial_cfg.get("bytesize", 8),
                parity=parity,
                stopbits=serial_cfg.get("stopbits", 1),
                timeout=serial_cfg.get("timeout", 0.5)
            )
            if self.client.connect():
                self.connected = True
                logger.info("Modbus RTU 连接成功: %s", port)
                return True
            else:
                logger.error("无法连接到 %s", port)
                return False
        except Exception as e:
            logger.error("连接 Modbus 失败: %s", e)
            return False

    def disconnect(self):
        """断开 Modbus 连接"""
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None
        self.connected = False
        logger.info("Modbus 连接已断开")

    def scan_slaves(self, start_addr=1, end_addr=247) -> list:
        """扫描指定地址范围内的从站设备"""
        if not self.connected or self.client is None:
            logger.error("未连接，无法扫描从站")
            return []

        found = []
        logger.info("开始扫描从站地址 %d~%d...", start_addr, end_addr)

        for slave_id in range(start_addr, end_addr + 1):
            try:
                result = self.client.read_holding_registers(
                    address=0, count=1, slave=slave_id
                )
                if not result.isError():
                    found.append(slave_id)
                    logger.info("  从站 %d 响应正常", slave_id)
            except Exception:
                pass

        self.found_slaves = found
        logger.info("扫描完成，找到 %d 个从站: %s", len(found), found)
        return found

    def read_register(self, slave_id, register_addr, count=1):
        """读取指定从站的保持寄存器值"""
        if not self.connected or self.client is None:
            logger.error("未连接，无法读取")
            return None

        try:
            result = self.client.read_holding_registers(
                address=register_addr, count=count, slave=slave_id
            )
            if result.isError():
                logger.warning(
                    "读取从站 %d 寄存器 %d 返回错误", slave_id, register_addr
                )
                return None
            return list(result.registers)
        except ModbusException as e:
            logger.warning("Modbus 异常 (从站 %d): %s", slave_id, e)
            return None
        except Exception as e:
            logger.warning("读取异常 (从站 %d): %s", slave_id, e)
            return None

    def write_register(self, slave_id, register_addr, value) -> bool:
        """向指定从站写入单个保持寄存器（16位整数）"""
        if not self.connected or self.client is None:
            logger.error("未连接，无法写入")
            return False

        try:
            value = int(value) & 0xFFFF
            result = self.client.write_register(
                address=register_addr, value=value, slave=slave_id
            )
            if result.isError():
                logger.warning(
                    "写入从站 %d 寄存器 %d=%d 返回错误",
                    slave_id, register_addr, value
                )
                return False
            logger.info(
                "写入成功: 从站=%d, 寄存器=%d, 值=%d",
                slave_id, register_addr, value
            )
            return True
        except ModbusException as e:
            logger.error("Modbus 写入异常 (从站 %d): %s", slave_id, e)
            return False
        except Exception as e:
            logger.error("写入异常 (从站 %d): %s", slave_id, e)
            return False

    def write_registers(self, slave_id, register_addr, values) -> bool:
        """向指定从站写入多个保持寄存器（用于32位/浮点数）"""
        if not self.connected or self.client is None:
            logger.error("未连接，无法写入")
            return False

        try:
            values = [int(v) & 0xFFFF for v in values]
            result = self.client.write_registers(
                address=register_addr, values=values, slave=slave_id
            )
            if result.isError():
                logger.warning(
                    "批量写入从站 %d 寄存器 %d 返回错误",
                    slave_id, register_addr
                )
                return False
            logger.info(
                "批量写入成功: 从站=%d, 起始寄存器=%d, 值=%s",
                slave_id, register_addr, values
            )
            return True
        except ModbusException as e:
            logger.error("Modbus 批量写入异常 (从站 %d): %s", slave_id, e)
            return False
        except Exception as e:
            logger.error("批量写入异常 (从站 %d): %s", slave_id, e)
            return False

    @staticmethod
    def register_to_float(registers: list) -> float:
        """将两个 16 位寄存器值转换为 32 位浮点数 (IEEE 754)"""
        import struct
        if len(registers) < 2:
            return float(registers[0]) if registers else 0.0
        raw = (registers[0] << 16) | registers[1]
        try:
            return struct.unpack(">f", struct.pack(">I", raw))[0]
        except Exception:
            return float(raw)

    @staticmethod
    def float_to_registers(value: float) -> list:
        """将 32 位浮点数转换为两个 16 位寄存器值"""
        import struct
        try:
            packed = struct.pack(">f", value)
            raw = struct.unpack(">I", packed)[0]
            high = (raw >> 16) & 0xFFFF
            low = raw & 0xFFFF
            return [high, low]
        except Exception:
            val = int(value) & 0xFFFFFFFF
            return [(val >> 16) & 0xFFFF, val & 0xFFFF]