# ETH交易策略 - 安装指南 (5分钟监控版)

## 📦 包内容

```
eth-trading-export/
├── strategies/              # 核心策略模块
│   ├── __init__.py
│   ├── signal_generator.py      信号生成器
│   ├── indicators.py            技术指标库
│   ├── gateio_client.py         GateIO API
│   └── binance_client.py        Binance API
├── config/                  # 配置文件
│   ├── strategy_config_v2.py    策略配置
│   ├── strategy_config.py       旧版配置
│   ├── cron-tasks.md            定时任务说明
│   └── openclaw-cron.json       Cron配置 (5分钟)
├── scripts/                 # 执行脚本
│   ├── backtest_v19.py          V19终极融合版
│   ├── eth_trading_bot.py       交易机器人 (默认5分钟)
│   └── ... 其他文件
├── docs/
│   └── api_comparison.md
├── README.md
└── INSTALL.md               # 本文件
```

## ⚡ 监控频率: 5分钟

本版本已将监控频率统一为 **5分钟**：

| 组件 | 频率 | 配置位置 |
|------|------|----------|
| 交易机器人 | 5分钟 | `eth_trading_bot.py --interval 300` |
| Cron任务 | 5分钟 | `openclaw-cron.json` |
| 定时监控 | 5分钟 | `*/5 * * * *` |

## 🚀 快速安装

### 1. 解压
```bash
tar -xzf ETH-Trading-Strategy-V19-5min.tar.gz
cd eth-trading-export
```

### 2. 移动
```bash
mv eth-trading-export /path/to/openclaw/skills/eth-trading
```

### 3. 安装依赖
```bash
pip3 install numpy requests
```

### 4. 配置API
编辑 `config/strategy_config_v2.py`：
```python
GATEIO_API_KEY = "your_key"
GATEIO_SECRET = "your_secret"
FEISHU_WEBHOOK = "your_webhook"  # 可选
```

### 5. 运行
```bash
python3 scripts/backtest_v19.py
```

## 📊 策略性能

| 指标 | 数值 |
|------|------|
| 策略版本 | V19 终极融合版 |
| 监控频率 | **5分钟** |
| 周收益 | +39.3% |
| 胜率 | 25% |
| 最大回撤 | 17.8% |

## 🔧 修改监控频率

### 交易机器人
```bash
# 5分钟 (默认)
python3 scripts/eth_trading_bot.py

# 自定义间隔
python3 scripts/eth_trading_bot.py --interval 600  # 10分钟
```

### Cron任务
编辑 `config/openclaw-cron.json`：
```json
"expr": "*/5 * * * *"  # 每5分钟
```

## 🔒 安全提醒

- 不要提交API密钥
- 先用模拟盘测试
- 只用10-20%资金

---
监控频率: 5分钟 | 版本: V19 | 更新: 2026-03-15
