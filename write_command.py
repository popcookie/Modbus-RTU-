"""
写指令独立脚本
==============
通过命令行参数向 Modbus RTU 总线上任意设备写入寄存器值。
支持 int16、int32、float 三种数据类型。

用法示例：
  python write_command.py --slave 1 --register 0 --value 123
  python write_command.py --slave 2 --register 10 --value 3.14 --type float
  python write_command.py --slave 3 --register 5 --value 70000 --type int32
  python write_command.py --slave 1 --register 0 --value 65535 --port COM3 --baudrate 19200
"""

import sys
import os
import json
import argparse
import logging
from datetime import datetime

# 添加当前目录到 sys.path 以确保可以导入自定义模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modbus_manager import ModbusManager

# ==================== 日志配置 ====================

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("WriteCommand")
logger.setLevel(logging.INFO)

# 文件日志
file_handler = logging.FileHandler(
    os.path.join(LOG_DIR, "log.txt"),
    encoding="utf-8"
)
file_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
)
logger.addHandler(file_handler)

# 控制台日志
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
)
logger.addHandler(console_handler)


# ==================== 配置加载 ====================

def load_config_for_write(config_path: str = None) -> dict:
    """
    加载配置，优先使用命令行指定的配置文件
    参数:
        config_path: 配置文件路径，为 None 时使用默认路径
    返回:
        配置字典
    """
    if config_path is None:
        config_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "config.json"
        )

    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        return config

    # 返回默认最小配置
    logger.warning("配置文件 %s 不存在，使用默认通信参数", config_path)
    return {
        "serial": {
            "port": None,
            "baudrate": 9600,
            "bytesize": 8,
            "parity": "N",
            "stopbits": 1,
            "timeout": 1.0
        }
    }


# ==================== 主函数 ====================

def main():
    parser = argparse.ArgumentParser(
        description="Modbus RTU 写寄存器工具 - 向指定从站写入寄存器值",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python write_command.py --slave 1 --register 0 --value 123
  python write_command.py --slave 2 --register 10 --value 3.14 --type float
  python write_command.py --slave 3 --register 5 --value 70000 --type int32
  python write_command.py --slave 1 --register 0 --value 255 --port COM3 --baudrate 19200
        """
    )

    # 必需参数
    parser.add_argument(
        "--slave", "-s", type=int, required=True,
        help="从站地址 (1~247)"
    )
    parser.add_argument(
        "--register", "-r", type=int, required=True,
        help="寄存器地址 (0~65535)"
    )
    parser.add_argument(
        "--value", "-v", type=str, required=True,
        help="要写入的值（int16: 0~65535, int32: 0~4294967295, float: 任意浮点数）"
    )

    # 可选参数
    parser.add_argument(
        "--type", "-t", type=str, default="int16",
        choices=["int16", "int32", "float"],
        help="数据类型（默认: int16）"
    )
    parser.add_argument(
        "--config", "-c", type=str, default=None,
        help="配置文件路径（默认: ./config.json）"
    )
    parser.add_argument(
        "--port", "-p", type=str, default=None,
        help="覆盖配置文件中的串口号（如 COM3, /dev/ttyUSB0）"
    )
    parser.add_argument(
        "--baudrate", "-b", type=int, default=None,
        help="覆盖配置文件中的波特率（如 9600, 19200）"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="模拟运行，不实际写入（用于测试参数）"
    )

    args = parser.parse_args()

    # 验证从站地址范围
    if args.slave < 1 or args.slave > 247:
        logger.error("从站地址必须在 1~247 之间")
        sys.exit(1)

    # 验证寄存器地址范围
    if args.register < 0 or args.register > 65535:
        logger.error("寄存器地址必须在 0~65535 之间")
        sys.exit(1)

    # 解析值
    try:
        if args.type == "float":
            value_parsed = float(args.value)
        else:
            value_parsed = int(float(args.value))
    except (ValueError, TypeError) as e:
        logger.error("无法解析写入值 '%s': %s", args.value, e)
        sys.exit(1)

    # 验证值范围
    if args.type == "int16":
        if value_parsed < 0 or value_parsed > 65535:
            logger.error("int16 值范围: 0~65535")
            sys.exit(1)
    elif args.type == "int32":
        if value_parsed < 0 or value_parsed > 4294967295:
            logger.error("int32 值范围: 0~4294967295")
            sys.exit(1)

    # 加载配置
    config = load_config_for_write(args.config)

    # 覆盖端口和波特率
    if args.port is not None:
        config.setdefault("serial", {})["port"] = args.port
        logger.info("使用命令行指定的端口: %s", args.port)
    if args.baudrate is not None:
        config.setdefault("serial", {})["baudrate"] = args.baudrate
        logger.info("使用命令行指定的波特率: %d", args.baudrate)

    # 干运行模式
    if args.dry_run:
        logger.info("=" * 50)
        logger.info("【模拟运行 - 不会实际写入】")
        logger.info("从站地址: %d", args.slave)
        logger.info("寄存器地址: %d", args.register)
        logger.info("写入值: %s (%s)", args.value, args.type)
        logger.info("串口: %s", config.get("serial", {}).get("port", "自动探测"))
        logger.info("波特率: %d", config.get("serial", {}).get("baudrate", 9600))
        logger.info("=" * 50)
        return

    # 连接 Modbus
    logger.info("正在连接 Modbus RTU 总线...")
    modbus_mgr = ModbusManager(config)

    if not modbus_mgr.connect():
        logger.error("Modbus 连接失败，请检查设备连接和配置")
        sys.exit(1)

    try:
        # 执行写入
        logger.info("=" * 50)
        logger.info("【写寄存器操作】")
        logger.info("从站地址: %d", args.slave)
        logger.info("寄存器地址: %d", args.register)
        logger.info("写入值: %s (%s)", args.value, args.type)
        logger.info("端口: %s", config.get("serial", {}).get("port", "自动"))
        logger.info("时间: %s", datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S.%f")[:-3])
        logger.info("=" * 50)

        success = False

        if args.type == "int16":
            success = modbus_mgr.write_register(
                args.slave, args.register, value_parsed
            )
        elif args.type == "int32":
            high = (value_parsed >> 16) & 0xFFFF
            low = value_parsed & 0xFFFF
            success = modbus_mgr.write_registers(
                args.slave, args.register, [high, low]
            )
        elif args.type == "float":
            registers = ModbusManager.float_to_registers(value_parsed)
            success = modbus_mgr.write_registers(
                args.slave, args.register, registers
            )

        if success:
            logger.info("写入成功！")
            print(f"\n✅ 写入成功: 从站={args.slave}, "
                  f"寄存器={args.register}, "
                  f"值={args.value} ({args.type})\n")
        else:
            logger.error("写入失败！")
            print(f"\n❌ 写入失败: 从站={args.slave}, "
                  f"寄存器={args.register}\n")
            sys.exit(1)

    except Exception as e:
        logger.error("写入过程中出现异常: %s", e)
        sys.exit(1)
    finally:
        modbus_mgr.disconnect()
        logger.info("Modbus 连接已关闭")


# ==================== 入口 ====================

if __name__ == "__main__":
    main()