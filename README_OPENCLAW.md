# OpenClaw 股票与加密货币交易指南

在 OpenClaw 平台中运行专业的股票和加密货币交易策略，支持飞书消息通知。

---

## 🚀 5分钟快速开始

```bash
# 1. 下载策略
wget https://github.com/xcself-glitch/aicoding/raw/main/Stock-Trading-Strategy-V1.tar.gz
wget https://github.com/xcself-glitch/aicoding/raw/main/ETH-Trading-Strategy-V19-5min.tar.gz

# 2. 解压安装
tar -xzf Stock-Trading-Strategy-V1.tar.gz -C ~/stock-trading
tar -xzf ETH-Trading-Strategy-V19-5min.tar.gz -C ~/eth-trading

# 3. 安装依赖
pip3 install numpy pandas requests yfinance

# 4. 验证安装
cd ~/stock-trading && python3 scripts/backtest_portfolio.py
```

---

## 📦 包含内容

### 股票策略 (Stock Trading)
- **7大预警规则**: 成本百分比、日内涨跌幅、成交量异动、均线金叉死叉、RSI超买超卖、跳空缺口、动态止盈
- **5种回测策略**: RSI、布林带、MACD、均线交叉、多因子综合
- **回测表现**: 兆易创新+19.33%，汉得信息+14.11%
- **飞书通知**: 实时预警推送到飞书群
- **交易日监控**: 盘前/盘中/收盘全流程监控

### ETH策略 (ETH Trading)
- **V19终极融合版**: +39.3%周收益
- **多时间框架**: 周线趋势+日线确认+小时入场
- **ATR动态止损**: 2-2.5倍ATR
- **自动交易**: 支持GateIO实盘
- **飞书日报**: 每日自动发送交易报告

---

## ⚙️ 配置说明

### 1. 股票持仓配置

编辑 `~/stock-trading/config/my_portfolio.py`:

```python
PORTFOLIO = [
    {
        "code": "603986",
        "name": "兆易创新",
        "cost": 298.69,      # 你的成本价
        "shares": 1100,      # 持仓数量
        "alerts": {
            "cost_pct_above": 10.0,   # 盈利10%提醒
            "cost_pct_below": 12.0,   # 亏损12%提醒
            "change_pct_above": 4.0,
            "change_pct_below": 4.0,
        }
    },
]
```

### 2. ETH API配置

编辑 `~/eth-trading/config/strategy_config_v2.py`:

```python
GATEIO_CONFIG = {
    "api_key": "your_api_key",
    "api_secret": "your_secret",
    "use_testnet": True,   # True=测试网, False=实盘
}
```

### 3. 飞书Webhook配置

在飞书群设置中添加自定义机器人，复制Webhook URL，填入:
- `~/stock-trading/scripts/feishu_adapter.py`
- `~/eth-trading/scripts/eth_notify_feishu.py`

---

## ⏰ OpenClaw定时任务配置

编辑 `~/workspace/cron/jobs.json`:

```json
{
  "jobs": [
    {
      "name": "stock-pre-market",
      "schedule": "30 8 * * 1-5",
      "command": "cd ~/stock-trading && python3 scripts/portfolio_trading_day.py --action pre-market",
      "enabled": true
    },
    {
      "name": "stock-intraday",
      "schedule": "*/10 9-11,13-14 * * 1-5",
      "command": "cd ~/stock-trading && python3 scripts/portfolio_trading_day.py --action intraday",
      "enabled": true
    },
    {
      "name": "eth-monitor",
      "schedule": "*/5 * * * *",
      "command": "cd ~/eth-trading && python3 scripts/eth_cron_job.py",
      "enabled": true
    }
  ]
}
```

然后重启Cron:
```bash
openclaw cron restart
```

---

## 📊 常用命令

### 股票策略

```bash
# 查看持仓
cd ~/stock-trading && python3 scripts/monitor_portfolio.py --summary

# 盘前简报
cd ~/stock-trading && python3 scripts/portfolio_trading_day.py --action pre-market

# 回测
cd ~/stock-trading && python3 scripts/backtest_portfolio.py

# 启动监控
cd ~/stock-trading && ./scripts/control_trading_day.sh start
```

### ETH策略

```bash
# 回测
cd ~/eth-trading && python3 scripts/backtest_v19.py

# 启动交易
cd ~/eth-trading && python3 scripts/eth_trading_bot.py --mode live

# 查看状态
cd ~/eth-trading && python3 scripts/eth_trading_bot.py --status
```

---

## 📚 完整文档

| 文档 | 说明 |
|------|------|
| [OPENCLAW_COMPLETE_GUIDE.md](./OPENCLAW_COMPLETE_GUIDE.md) | **完整使用指南**（推荐） |
| [stock-trading/SKILL.md](./stock-trading/SKILL.md) | 股票策略详细文档 |
| [stock-trading/BACKTEST_REPORT.md](./stock-trading/BACKTEST_REPORT.md) | 股票回测报告 |
| [eth-trading/OPENCLAW_GUIDE.md](./eth-trading/OPENCLAW_GUIDE.md) | ETH策略指南 |
| [eth-trading/README.md](./eth-trading/README.md) | ETH策略说明 |

---

## 🎯 策略推荐

| 资产 | 推荐策略 | 预期收益 | 适用场景 |
|------|----------|----------|----------|
| 兆易创新 | RSI超买超卖 | +19.33% | 科技股波动 |
| 汉得信息 | 布林带均值回归 | +14.11% | AI高波动 |
| ETH | V19终极融合 | +39.3%/周 | 加密货币 |

---

## 🔔 消息通知示例

### 股票预警
```
🚨【紧急】🔴 兆易创新 (603986)
━━━━━━━━━━━━━━━━━━━━
💰 当前价格: ¥328.56 (+10.0%)
📊 持仓成本: ¥298.69 | 盈亏: 🔴+10.0%

🎯 触发预警:
  • 🎯 盈利 10% (目标达成)
  • 📊 放量 2.5倍
```

### ETH交易信号
```
🚀 【买入信号】ETH/USDT
━━━━━━━━━━━━━━━━━━
💰 买入价格: $3,456.78
📊 止损价格: $3,280.94 (5%)
🎯 目标价格: $3,800.00 (+10%)
💡 信号强度: 85/100
```

---

## ⚠️ 风险提示

- **本系统仅供学习和研究使用，不构成投资建议**
- **股票和加密货币交易风险极高，请自行承担风险**
- **回测结果不代表未来收益，实盘可能有滑点和延迟**
- **请使用测试网充分测试后再进行实盘交易**

---

## 📞 支持

- GitHub Issues: https://github.com/xcself-glitch/aicoding/issues
- OpenClaw 文档: https://docs.openclaw.ai

---

**更新日期**: 2026-03-15
