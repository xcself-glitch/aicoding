# 📊 持仓股智能监控与策略系统

自动更新买卖策略，实时监控价格，达到目标价时通过飞书通知。

## 🚀 快速开始

### 1. 配置飞书通知

```bash
cd skills/stock-monitor-pro
./scripts/setup_feishu.sh
```

或手动设置环境变量：
```bash
export FEISHU_WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxx"
```

### 2. 测试监控脚本

```bash
# 检查当前价格
python3 scripts/price_monitor_feishu.py --check

# 发送每日策略报告
python3 scripts/price_monitor_feishu.py --daily

# 完整监控（检查+报告）
python3 scripts/price_monitor_feishu.py
```

### 3. 安装定时任务

```bash
# 复制 cron 配置到 OpenClaw
cp config/openclaw-cron.json $OPENCLAW_STATE_DIR/cron/stock-monitor-cron.json

# 重启 OpenClaw 使配置生效
openclaw cron reload
```

## 📅 定时任务说明

| 时间 | 任务 | 说明 |
|------|------|------|
| 9:25 | 策略更新 | 早盘更新买卖策略 |
| 9:30, 10:30 | 价格监控 | 早盘价格检查 |
| 13:00, 14:00 | 价格监控 | 午盘价格检查 |
| 14:30 | 价格监控 | 下午价格检查 |
| 15:05 | 收盘日报 | 生成每日持仓报告 |

## 🎯 预警规则

### 买入提醒 🟢
- 当股价 ≤ 目标买入价时触发
- 建议逢低加仓

### 减仓提醒 🔴
- 当股价 ≥ 目标减仓价时触发
- 建议减仓锁定利润

### 止损提醒 🚨
- 当股价 ≤ 止损价时触发
- 严格执行止损纪律

### 异动提醒 📊
- 日内涨跌幅 ≥ 5% 时触发
- ≥ 7% 标记为紧急

## 📁 文件结构

```
skills/stock-monitor-pro/
├── config/
│   ├── my_portfolio.py       # 持仓配置（含买卖策略）
│   └── openclaw-cron.json    # 定时任务配置
├── scripts/
│   ├── price_monitor_feishu.py  # 价格监控与飞书通知
│   ├── update_strategy.py       # 每日策略更新
│   ├── feishu_adapter.py        # 飞书通知适配器
│   └── setup_feishu.sh          # 飞书配置脚本
└── reports/                     # 策略报告存放目录
```

## ⚙️ 配置持仓

编辑 `config/my_portfolio.py`，修改 `PORTFOLIO` 列表：

```python
{
    "code": "603986",
    "name": "兆易创新",
    "market": "sh",
    "type": "individual",
    "cost": 298.69,           # 持仓成本
    "shares": 1100,           # 持仓数量
    "alerts": {
        "target_buy": 265.0,      # 目标买入价（加仓点）
        "target_reduce": 310.0,   # 目标减仓价
        "stop_loss": 245.0,       # 止损价
        "change_pct_above": 4.0,  # 日内涨幅预警
        "change_pct_below": 4.0,  # 日内跌幅预警
    }
}
```

## 📱 飞书通知示例

### 买入提醒
```
🟢 兆易创新 触及买入目标价

当前价格: ¥265.00
目标买入价: ¥265.00
建议: 可考虑逢低加仓
```

### 每日策略报告
```
📊 每日持仓策略更新

📅 日期: 2026-03-14
🏛️ 大盘: 上证-0.8% | 深证-0.6% | 创业-0.2%

💰 整体盈亏: -12.5%
持仓成本: ¥1,234,567
当前市值: ¥1,080,000

📈 持仓概览:
🟢 卫星ETF: ¥1.69 (+1.5%)
🔴 兆易创新: ¥278.33 (-6.8%)
...

🟢 买入信号:
• 兆易创新: 当前¥265.00 ≤ 目标¥265.00
```

## 🔧 手动运行

```bash
# 监控单次价格
cd skills/stock-monitor-pro
python3 scripts/price_monitor_feishu.py --check

# 生成策略报告
python3 scripts/price_monitor_feishu.py --daily

# 完整运行（监控+报告）
python3 scripts/price_monitor_feishu.py

# 更新策略（根据大盘和个股技术面）
python3 scripts/update_strategy.py
```

## 📝 更新日志

### v2.0 (2026-03-14)
- ✅ 自动策略更新系统
- ✅ 飞书实时通知
- ✅ 买卖价格动态调整
- ✅ 多时段价格监控
- ✅ 每日收盘报告

## ⚠️ 免责声明

本系统仅供学习和参考，不构成投资建议。股市有风险，投资需谨慎。
