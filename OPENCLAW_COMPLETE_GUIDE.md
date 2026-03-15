# OpenClaw 完整使用指南 - 股票与加密货币策略

本文档详细介绍如何在 OpenClaw 平台中安装、配置和运行股票交易策略与加密货币策略，以及设置消息通知。

---

## 📋 目录

- [快速开始](#快速开始)
- [环境准备](#环境准备)
- [安装策略](#安装策略)
- [配置消息通知](#配置消息通知)
- [配置定时任务](#配置定时任务)
- [运行回测](#运行回测)
- [启动实盘监控](#启动实盘监控)
- [日常使用命令](#日常使用命令)
- [故障排查](#故障排查)

---

## 🚀 快速开始

### 一键安装（推荐）

```bash
# 1. 下载并安装股票策略
wget https://github.com/xcself-glitch/aicoding/raw/main/Stock-Trading-Strategy-V1.tar.gz
tar -xzf Stock-Trading-Strategy-V1.tar.gz -C ~/stock-trading

# 2. 下载并安装ETH策略
wget https://github.com/xcself-glitch/aicoding/raw/main/ETH-Trading-Strategy-V19-5min.tar.gz
tar -xzf ETH-Trading-Strategy-V19-5min.tar.gz -C ~/eth-trading

# 3. 安装依赖
pip3 install numpy pandas requests yfinance

# 4. 验证安装
cd ~/stock-trading && python3 scripts/backtest_portfolio.py
cd ~/eth-trading && python3 scripts/backtest_v19.py
```

---

## ⚙️ 环境准备

### 1. 检查OpenClaw状态

```bash
# 检查OpenClaw是否正常运行
openclaw status

# 检查配置
openclaw config show

# 诊断问题
openclaw doctor
```

### 2. 安装Python依赖

```bash
# 安装必需包
pip3 install --upgrade pip
pip3 install numpy pandas requests yfinance

# 验证安装
python3 -c "import numpy, pandas, requests; print('✅ 依赖安装成功')"
```

### 3. 创建工作目录

```bash
# 创建策略目录
mkdir -p ~/stock-trading ~/eth-trading

# 设置环境变量
echo 'export STOCK_TRADING_HOME="$HOME/stock-trading"' >> ~/.bashrc
echo 'export ETH_TRADING_HOME="$HOME/eth-trading"' >> ~/.bashrc
source ~/.bashrc
```

---

## 📦 安装策略

### 方法一：从GitHub安装（推荐）

```bash
# 股票策略
cd ~
wget https://github.com/xcself-glitch/aicoding/raw/main/Stock-Trading-Strategy-V1.tar.gz
tar -xzf Stock-Trading-Strategy-V1.tar.gz
mv stock-trading-export stock-trading

# ETH策略
wget https://github.com/xcself-glitch/aicoding/raw/main/ETH-Trading-Strategy-V19-5min.tar.gz
tar -xzf ETH-Trading-Strategy-V19-5min.tar.gz
mv eth-trading-export eth-trading

# 清理
rm -f ETH-Trading-Strategy-V19-5min.tar.gz
```

### 方法二：克隆完整仓库

```bash
# 克隆整个仓库
git clone https://github.com/xcself-glitch/aicoding.git ~/aicoding

# 复制需要的部分
cp -r ~/aicoding/stock-trading ~/stock-trading
cp -r ~/aicoding/eth-trading ~/eth-trading
```

### 方法三：OpenClaw Skill安装

```bash
# 如果有打包的Skill
cp -r ~/stock-trading ~/workspace/skills/stock-trading
cp -r ~/eth-trading ~/workspace/skills/eth-trading

# 重启OpenClaw识别
openclaw restart
```

---

## ⚙️ 配置策略

### 1. 股票策略配置

#### 编辑持仓配置

```bash
nano ~/stock-trading/config/my_portfolio.py
```

**示例配置**:

```python
PORTFOLIO = [
    {
        "code": "603986",
        "name": "兆易创新",
        "market": "sh",
        "type": "individual",
        "cost": 298.69,          # 你的成本价
        "shares": 1100,          # 持仓数量
        "priority": "high",
        "note": "存储芯片龙头，策略:逢低加仓",
        "alerts": {
            "cost_pct_above": 10.0,      # 盈利10%提醒
            "cost_pct_below": 12.0,      # 亏损12%提醒
            "target_buy": 265.0,         # 加仓点
            "target_reduce": 310.0,      # 减仓点
            "stop_loss": 245.0,          # 止损位
            "change_pct_above": 4.0,
            "change_pct_below": 4.0,
            "ma_monitor": True,
            "rsi_monitor": True,
            "gap_monitor": True,
        }
    },
    # 添加更多股票...
]
```

#### 配置定时任务（Cron）

编辑 OpenClaw 的 Cron 配置:

```bash
nano ~/workspace/cron/jobs.json
```

**添加以下内容**:

```json
{
  "jobs": [
    {
      "name": "stock-pre-market",
      "schedule": "30 8 * * 1-5",
      "command": "cd ~/stock-trading && python3 scripts/portfolio_trading_day.py --action pre-market >> ~/stock-trading/logs/cron.log 2>&1",
      "enabled": true,
      "description": "股票盘前简报"
    },
    {
      "name": "stock-market-open",
      "schedule": "15 9 * * 1-5",
      "command": "cd ~/stock-trading && python3 scripts/portfolio_trading_day.py --action open >> ~/stock-trading/logs/cron.log 2>&1",
      "enabled": true,
      "description": "股票开盘建议"
    },
    {
      "name": "stock-intraday",
      "schedule": "*/10 9-11,13-14 * * 1-5",
      "command": "cd ~/stock-trading && python3 scripts/portfolio_trading_day.py --action intraday >> ~/stock-trading/logs/cron.log 2>&1",
      "enabled": true,
      "description": "股票盘中监控（每10分钟）"
    },
    {
      "name": "stock-market-close",
      "schedule": "30 15 * * 1-5",
      "command": "cd ~/stock-trading && python3 scripts/portfolio_trading_day.py --action close >> ~/stock-trading/logs/cron.log 2>&1",
      "enabled": true,
      "description": "股票收盘复盘"
    },
    {
      "name": "stock-daily-summary",
      "schedule": "0 16 * * 1-5",
      "command": "cd ~/stock-trading && python3 scripts/monitor_portfolio.py --summary >> ~/stock-trading/logs/cron.log 2>&1",
      "enabled": true,
      "description": "股票收盘日报"
    }
  ]
}
```

### 2. ETH策略配置

#### 编辑API配置

```bash
nano ~/eth-trading/config/strategy_config_v2.py
```

**配置GateIO API**:

```python
GATEIO_CONFIG = {
    "api_key": "your_gateio_api_key",
    "api_secret": "your_gateio_secret",
    "use_testnet": True,      # True=测试网, False=实盘
}

TRADING_CONFIG = {
    "symbol": "ETH_USDT",
    "timeframe": "5m",
    "initial_capital": 10000,
    "risk_per_trade": 0.02,
}
```

#### 配置ETH定时任务

```bash
nano ~/workspace/cron/jobs.json
```

**添加ETH任务**:

```json
{
  "jobs": [
    {
      "name": "eth-cron-monitor",
      "schedule": "*/5 * * * *",
      "command": "cd ~/eth-trading && python3 scripts/eth_cron_job.py >> ~/eth-trading/logs/cron.log 2>&1",
      "enabled": true,
      "description": "ETH策略监控（每5分钟）"
    },
    {
      "name": "eth-daily-report",
      "schedule": "0 0 * * *",
      "command": "cd ~/eth-trading && python3 scripts/eth_daily_report.py >> ~/eth-trading/logs/cron.log 2>&1",
      "enabled": true,
      "description": "ETH日报"
    },
    {
      "name": "eth-weekly-backtest",
      "schedule": "0 9 * * 1",
      "command": "cd ~/eth-trading && python3 scripts/backtest_v19.py --week >> ~/eth-trading/logs/cron.log 2>&1",
      "enabled": true,
      "description": "ETH周度回测"
    }
  ]
}
```

---

## 📱 配置消息通知

### 1. 飞书Webhook配置

#### 获取Webhook URL

1. 打开飞书群聊 → 点击右上角 **"设置"**
2. 选择 **"群机器人"** → **"添加机器人"**
3. 选择 **"自定义机器人"**
4. 复制 **Webhook URL**

#### 配置股票策略飞书通知

```bash
# 编辑飞书适配器
nano ~/stock-trading/scripts/feishu_adapter.py
```

**配置Webhook**:

```python
FEISHU_CONFIG = {
    "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/xxxx-xxxx-xxxx",
    "secret": "",  # 如果有签名密钥
    "enable": True
}
```

#### 配置ETH策略飞书通知

```bash
# 编辑ETH飞书配置
nano ~/eth-trading/scripts/eth_notify_feishu.py
```

**配置Webhook**:

```python
FEISHU_CONFIG = {
    "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/xxxx-xxxx-xxxx",
    "secret": "",
}
```

### 2. 测试通知

```bash
# 测试股票飞书通知
cd ~/stock-trading
python3 scripts/test_price_alert.py

# 测试ETH飞书通知
cd ~/eth-trading
python3 scripts/test_feishu_alert.py
```

### 3. 配置环境变量（可选）

```bash
# 添加到 ~/.bashrc
export FEISHU_WEBHOOK_STOCK="https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
export FEISHU_WEBHOOK_ETH="https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
export GATEIO_API_KEY="your_key"
export GATEIO_API_SECRET="your_secret"

source ~/.bashrc
```

---

## ⏰ 配置OpenClaw定时任务

### 方法1：使用OpenClaw Cron

```bash
# 查看当前任务
openclaw cron list

# 编辑任务
openclaw cron edit

# 验证任务
openclaw cron validate

# 重启Cron服务
openclaw cron restart
```

### 方法2：直接编辑配置文件

```bash
# 编辑Cron配置
nano ~/workspace/cron/jobs.json
```

**完整的股票+ETH组合配置**:

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
      "name": "stock-market-open",
      "schedule": "15 9 * * 1-5",
      "command": "cd ~/stock-trading && python3 scripts/portfolio_trading_day.py --action open",
      "enabled": true
    },
    {
      "name": "stock-intraday",
      "schedule": "*/10 9-11,13-14 * * 1-5",
      "command": "cd ~/stock-trading && python3 scripts/portfolio_trading_day.py --action intraday",
      "enabled": true
    },
    {
      "name": "stock-market-close",
      "schedule": "30 15 * * 1-5",
      "command": "cd ~/stock-trading && python3 scripts/portfolio_trading_day.py --action close",
      "enabled": true
    },
    {
      "name": "stock-daily-summary",
      "schedule": "0 16 * * 1-5",
      "command": "cd ~/stock-trading && python3 scripts/monitor_portfolio.py --summary",
      "enabled": true
    },
    {
      "name": "eth-monitor",
      "schedule": "*/5 * * * *",
      "command": "cd ~/eth-trading && python3 scripts/eth_cron_job.py",
      "enabled": true
    },
    {
      "name": "eth-daily-report",
      "schedule": "0 0 * * *",
      "command": "cd ~/eth-trading && python3 scripts/eth_daily_report.py",
      "enabled": true
    }
  ]
}
```

### 方法3：使用系统Cron（备用）

```bash
# 编辑系统crontab
crontab -e

# 添加以下内容
# 股票策略
30 8 * * 1-5 cd ~/stock-trading && python3 scripts/portfolio_trading_day.py --action pre-market >> ~/stock-trading/logs/cron.log 2>&1
*/10 9-11,13-14 * * 1-5 cd ~/stock-trading && python3 scripts/portfolio_trading_day.py --action intraday >> ~/stock-trading/logs/cron.log 2>&1

# ETH策略
*/5 * * * * cd ~/eth-trading && python3 scripts/eth_cron_job.py >> ~/eth-trading/logs/cron.log 2>&1
```

---

## 📊 运行回测

### 股票策略回测

```bash
cd ~/stock-trading

# 多策略对比回测（5种策略）
python3 scripts/backtest_portfolio.py

# 优化版回测（V2.0）
python3 scripts/backtest_optimized.py

# 单个股票回测
python3 scripts/backtest_portfolio.py --stock 603986

# 指定周期回测
python3 scripts/backtest_portfolio.py --period 2y
```

### ETH策略回测

```bash
cd ~/eth-trading

# V19终极融合版（推荐）
python3 scripts/backtest_v19.py

# V17高收益版
python3 scripts/backtest_v17.py

# V18风控版
python3 scripts/backtest_v18.py

# 生成回测报告
python3 scripts/backtest_report.py --output report.html
```

### 查看回测结果

```bash
# 股票回测结果
cat ~/stock-trading/BACKTEST_REPORT.md

# ETH回测结果
cat ~/eth-trading/REPORT_V19.md
```

---

## 💹 启动实盘监控

### 1. 测试模式（推荐先测试）

```bash
# 股票策略测试
cd ~/stock-trading
python3 scripts/monitor_portfolio.py --test

# ETH策略测试
cd ~/eth-trading
python3 scripts/eth_trading_bot.py --mode test
```

### 2. 后台监控模式

```bash
# 启动股票交易日监控
cd ~/stock-trading
./scripts/control_trading_day.sh start

# 查看状态
./scripts/control_trading_day.sh status

# 查看日志
./scripts/control_trading_day.sh log

# 生成盘前简报
./scripts/control_trading_day.sh pre-market
```

### 3. 使用nohup后台运行

```bash
# 股票监控
nohup python3 ~/stock-trading/scripts/portfolio_trading_day.py --daemon > ~/stock-trading/logs/daemon.log 2>&1 &

# ETH监控
nohup python3 ~/eth-trading/scripts/eth_trading_bot.py --mode live > ~/eth-trading/logs/trading.log 2>&1 &

# 查看进程
ps aux | grep -E "portfolio|eth_trading"
```

### 4. 使用OpenClaw守护进程

```bash
# 创建OpenClaw守护进程配置
nano ~/workspace/agents/main/agent/daemons.json
```

```json
{
  "daemons": [
    {
      "name": "stock-monitor",
      "command": "cd ~/stock-trading && python3 scripts/portfolio_trading_day.py --daemon",
      "enabled": true,
      "restart": "always"
    },
    {
      "name": "eth-monitor",
      "command": "cd ~/eth-trading && python3 scripts/eth_cron_job.py",
      "enabled": true,
      "restart": "always"
    }
  ]
}
```

---

## 🛠️ 日常使用命令

### 快速命令参考

```bash
# ========== 股票策略 ==========

# 查看持仓状态
cd ~/stock-trading && python3 scripts/monitor_portfolio.py --summary

# 生成盘前简报
cd ~/stock-trading && python3 scripts/portfolio_trading_day.py --action pre-market

# 生成收盘复盘
cd ~/stock-trading && python3 scripts/portfolio_trading_day.py --action close

# 检查持仓
cd ~/stock-trading && python3 scripts/monitor_portfolio.py --check

# 测试飞书通知
cd ~/stock-trading && python3 scripts/test_price_alert.py

# 查看日志
tail -f ~/stock-trading/logs/cron.log

# ========== ETH策略 ==========

# 查看ETH状态
cd ~/eth-trading && python3 scripts/eth_trading_bot.py --status

# 运行回测
cd ~/eth-trading && python3 scripts/backtest_v19.py

# 测试飞书通知
cd ~/eth-trading && python3 scripts/test_feishu_alert.py

# 查看日志
tail -f ~/eth-trading/logs/trading.log

# ========== OpenClaw管理 ==========

# 查看Cron任务
openclaw cron list

# 查看OpenClaw状态
openclaw status

# 查看日志
openclaw logs --follow

# 重启OpenClaw
openclaw restart
```

### 创建快捷命令

```bash
# 添加到 ~/.bashrc
alias stock-status='cd ~/stock-trading && python3 scripts/monitor_portfolio.py --summary'
alias stock-pre='cd ~/stock-trading && python3 scripts/portfolio_trading_day.py --action pre-market'
alias stock-close='cd ~/stock-trading && python3 scripts/portfolio_trading_day.py --action close'
alias stock-log='tail -f ~/stock-trading/logs/cron.log'

alias eth-backtest='cd ~/eth-trading && python3 scripts/backtest_v19.py'
alias eth-log='tail -f ~/eth-trading/logs/trading.log'

alias oc-status='openclaw status'
alias oc-log='openclaw logs --follow'

source ~/.bashrc
```

---

## 🔧 故障排查

### 常见问题

#### Q1: Cron任务不执行

```bash
# 检查Cron服务
openclaw cron status

# 手动测试任务
cd ~/stock-trading && python3 scripts/portfolio_trading_day.py --action pre-market

# 查看Cron日志
openclaw logs --follow

# 检查权限
ls -la ~/stock-trading/scripts/
chmod +x ~/stock-trading/scripts/*.sh
```

#### Q2: 飞书通知不生效

```bash
# 测试Webhook
curl -X POST -H "Content-Type: application/json" \
  -d '{"msg_type":"text","content":{"text":"测试消息"}}' \
  YOUR_WEBHOOK_URL

# 检查配置
grep -r "webhook_url" ~/stock-trading/config/
grep -r "webhook_url" ~/eth-trading/config/

# 检查网络
ping open.feishu.cn
```

#### Q3: 回测运行失败

```bash
# 检查依赖
python3 -c "import numpy, pandas; print('OK')"

# 检查数据
ls -la ~/stock-trading/config/my_portfolio.py

# 安装缺失包
pip3 install numpy pandas requests yfinance
```

#### Q4: OpenClaw启动失败

```bash
# 诊断问题
openclaw doctor

# 查看详细日志
openclaw logs --all

# 重启服务
openclaw restart

# 如果仍失败，查看系统日志
journalctl -u openclaw -f
```

### 日志位置

| 类型 | 路径 |
|------|------|
| 股票策略日志 | `~/stock-trading/logs/cron.log` |
| 股票监控日志 | `~/stock-trading/logs/daemon.log` |
| ETH策略日志 | `~/eth-trading/logs/trading.log` |
| ETH Cron日志 | `~/eth-trading/logs/cron.log` |
| OpenClaw日志 | `~/workspace/logs/` |
| Cron日志 | `~/workspace/cron/logs/` |

---

## 📚 高级配置

### 1. 多环境配置

```bash
# 开发环境
export TRADING_ENV=dev
export LOG_LEVEL=debug

# 生产环境
export TRADING_ENV=prod
export LOG_LEVEL=info
```

### 2. 数据库记录（可选）

```bash
# 安装SQLite
pip3 install sqlite3

# 创建数据库
cd ~/stock-trading
python3 -c "
import sqlite3
conn = sqlite3.connect('trading.db')
conn.execute('''
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY,
    date TEXT,
    symbol TEXT,
    action TEXT,
    price REAL,
    shares INTEGER,
    profit REAL
)
''')
conn.commit()
"
```

### 3. Docker部署（可选）

```dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python3", "scripts/portfolio_trading_day.py", "--daemon"]
```

---

## 🎯 最佳实践

### 1. 风险管理

- 单票仓位不超过20%
- 总回撤超过20%减仓至50%
- 每日检查一次仓位

### 2. 策略选择

| 股票类型 | 推荐策略 | 理由 |
|----------|----------|------|
| 科技股 | RSI | 波动大，反转多 |
| 成长股 | 布林带 | 超买超卖明显 |
| ETF | 均线交叉 | 趋势性强 |
| ETH | V19综合 | 多因子确认 |

### 3. 监控频率

- 股票: 盘中每10分钟
- ETH: 每5分钟
- 日报: 收盘后自动发送
- 周报: 每周一早上

---

## 📞 支持

如有问题，请通过以下方式联系：

- GitHub Issues: https://github.com/xcself-glitch/aicoding/issues
- OpenClaw 社区: https://docs.openclaw.ai
- 飞书文档: https://open.feishu.cn/document

---

**更新日期**: 2026-03-15  
**版本**: V1.0
