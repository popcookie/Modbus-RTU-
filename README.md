# 氧气项目实时监控系统 (Oxygen Monitor)

基于 Modbus RTU 协议的多设备实时监控系统，支持流量计、热电偶、压力传感器三种设备类型，所有设备并联到同一根 RS485 总线上，共用一个 COM 口。

## 功能特性

### 核心功能
- **Modbus RTU 通信**：支持标准 Modbus RTU 协议，可配置通信参数
- **自动端口探测**：自动扫描可用 COM 口，找到有 Modbus 设备的总线端口
- **自动从站扫描**：扫描 1~247 从站地址，记录响应设备
- **周期性数据采集**：默认每秒一轮读取所有设备寄存器值
- **写寄存器操作**：支持命令行脚本和 GUI 界面两种方式写入寄存器值
- **实时曲线显示**：三种设备类型独立子图，动态刷新最近 60 秒数据
- **报警阈值管理**：每个设备独立设置高限/低限，超限自动弹窗警告
- **CSV 数据存储**：所有设备数据存入同一 CSV 文件，每天自动新建
- **日志记录**：记录启动、连接、读写操作、报警等所有重要事件

### 技术架构
- **多线程设计**：采集线程 + 数据处理线程 + GUI 线程分离，避免界面卡死
- **优雅退出**：关闭窗口或 Ctrl+C 时，自动停止所有线程、关闭文件
- **动态阈值**：运行时通过 GUI 修改阈值，立即生效，无需重启
- **超限弹窗**：报警窗口不自动关闭，需用户确认，支持多窗口同时存在

## 项目结构

```
oxygenmonitor/
├── config.json           # 配置文件（设备列表、通信参数、阈值）
├── modbus_manager.py     # Modbus RTU 通信管理类
├── alarm_manager.py      # 报警管理类（阈值判断、弹窗、日志）
├── data_logger.py        # 主程序（采集、CSV、曲线、GUI 总控）
├── threshold_window.py   # 阈值设置窗口（含写寄存器界面）
├── write_command.py      # 写指令独立脚本
├── requirements.txt      # Python 依赖包
├── README.md             # 项目说明文档
├── logs/                 # 日志目录
│   └── log.txt           # 运行日志
└── data/                 # 数据目录
    └── oxygen_data_YYYYMMDD.csv  # 数据文件（按日期命名）
```

## 环境要求

- Python 3.10+
- Windows / Linux / macOS
- RS485 转 USB 适配器（硬件）

## 安装

```bash
# 安装依赖
pip install -r requirements.txt
```

## 配置说明

编辑 `config.json` 文件：

```json
{
    "serial": {
        "port": null,           // null 表示自动探测，也可手动指定如 "COM3"
        "baudrate": 9600,       // 波特率：9600/19200/38400/115200
        "bytesize": 8,          // 数据位：8
        "parity": "N",          // 校验位：N/E/O
        "stopbits": 1           // 停止位：1/2
    },
    "scan_enabled": true,       // 启动时是否扫描从站
    "interval_seconds": 1,      // 采集间隔（秒）
    "devices": [
        {
            "slave_id": 1,          // Modbus 从站地址 (1~247)
            "type": "flow",         // 设备类型: flow/temp/pressure
            "register": 0,          // 保持寄存器地址
            "name": "氧气流量计",     // 设备名称（显示用）
            "high_limit": 100.0,    // 报警高限
            "low_limit": 0.0        // 报警低限
        }
    ]
}
```

### 设备类型说明

| 类型       | 值       | 说明           |
|-----------|----------|---------------|
| flow      | 流量计   | 流量监控设备   |
| temp      | 热电偶   | 温度监控设备   |
| pressure  | 压力传感器 | 压力监控设备   |

## 使用方式

### 1. 启动主程序（推荐）

```bash
python data_logger.py
```

启动后会依次：
1. 加载配置文件
2. 自动探测 Modbus 端口并连接
3. 扫描从站设备（如果启用）
4. 打开实时曲线窗口（3 个子图）
5. 打开阈值管理窗口（独立窗口）
6. 开始周期性数据采集和 CSV 记录
7. 实时报警检测与弹窗

关闭曲线窗口即可安全退出整个系统。

### 2. 写寄存器（命令行）

```bash
# 写入 16 位整数
python write_command.py --slave 1 --register 0 --value 123

# 写入 32 位整数
python write_command.py --slave 2 --register 10 --value 70000 --type int32

# 写入浮点数
python write_command.py --slave 3 --register 4 --value 3.14 --type float

# 指定端口和波特率
python write_command.py --slave 1 --register 0 --value 255 --port COM3 --baudrate 19200

# 模拟运行（不实际写入，用于验证参数）
python write_command.py --slave 1 --register 0 --value 123 --dry-run
```

### 3. 写寄存器（GUI）

启动主程序后，在「阈值管理与写寄存器」窗口中选择「写寄存器」选项卡：
1. 选择/输入从站地址
2. 输入寄存器地址
3. 选择数据类型（int16/int32/float）
4. 输入写入值
5. 点击「写入寄存器」按钮
6. 在操作结果区域查看反馈

### 4. 独立运行阈值管理窗口

```bash
python threshold_window.py
```

## 界面说明

### 实时曲线窗口
- **子图 1（流量计）**：显示所有流量计设备的实时曲线
- **子图 2（热电偶）**：显示所有热电偶设备的实时曲线
- **子图 3（压力传感器）**：显示所有压力传感器设备的实时曲线
- X 轴：最近 60 秒时间范围
- 图例：显示每个设备的名称
- 窗口标题：「氧气项目实时监控」

### 阈值管理窗口
- **阈值管理选项卡**：表格形式展示所有设备的高限/低限，修改后点击「保存阈值」立即生效
- **写寄存器选项卡**：支持选择从站、寄存器、数据类型，执行写入操作

### 报警弹窗
- 黄色警告窗口，置顶显示
- 包含：设备名称、设备类型、当前值、阈值、超限时间
- 需要用户点击「确认」按钮关闭
- 允许多个报警窗口同时存在
- 每个报警方向（高限/低限）每个设备只弹一次，恢复后会清除状态

## 数据文件

### CSV 数据结构

```
Timestamp,氧气流量计,氮气流量计,反应釜温度,罐体压力
2026-05-07 14:30:01.123,85.200,65.100,45.300,0.850
2026-05-07 14:30:02.234,85.500,65.000,NaN,0.852
```

- 时间戳精度：毫秒
- 读取失败时该值记为 `NaN`
- 每天自动新建文件：`oxygen_data_YYYYMMDD.csv`

### 日志文件 (logs/log.txt)

记录内容：
- 系统启动/退出
- Modbus 连接/断开/扫描
- 每次写寄存器操作
- 报警触发/恢复
- 读取错误/异常

## 依赖包

```
pymodbus >= 3.6.8
pyserial >= 3.5
matplotlib >= 3.5.0
```

`tkinter` 为 Python 内置模块，无需额外安装。

## 常见问题

### Q: 启动提示 "Modbus 连接失败"？
A: 检查 RS485 适配器是否正确连接，USB 驱动是否安装。可手动在 config.json 中指定 `"port": "COM3"`（Windows）或 `"port": "/dev/ttyUSB0"`（Linux）。

### Q: 报警弹窗不出现？
A: 检查设备配置中的 `high_limit` 和 `low_limit` 是否正确设置。确认采集到的数据确实超出阈值范围。

### Q: CSV 文件在哪里？
A: 在 `data/` 目录下，文件名为 `oxygen_data_YYYYMMDD.csv`。

### Q: 如何添加新设备？
A: 在 `config.json` 的 `devices` 数组中添加新条目，然后重启程序。

### Q: 程序退出后报警窗口还在？
A: 程序退出时会自动关闭所有报警窗口。

## License

内部使用