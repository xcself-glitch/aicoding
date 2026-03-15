# ETH交易策略 - OpenClaw 使用指南

本文档介绍如何在 OpenClaw 平台中安装、配置和运行 ETH 交易策略。

---

## 📋 目录

- [快速开始](#快速开始)
- [环境配置](#环境配置)
- [安装步骤](#安装步骤)
- [配置 Cron 定时任务](#配置-cron-定时任务)
- [配置飞书通知](#配置飞书通知)
- [运行回测](#运行回测)
- [启动实盘交易](#启动实盘交易)
- [监控与日志](#监控与日志)
- [常见问题](#常见问题)

---

## 🚀 快速开始

### 1. 一键安装

```bash
# 克隆仓库
git clone https://github.com/xcself-glitch/aicoding.git
cd aicoding/eth-trading

# 运行安装脚本
bash install.sh
```

### 2. 验证安装

```bash
# 测试策略回测
python3 scripts/backtest_v19.py
```

---

## ⚙️ 环境配置

### 必需的 Python 包

```bash
pip3 install numpy requests pandas
```

### 配置文件

编辑 `config/strategy_config_v2.py`：

```python
# GateIO API 配置（实盘交易必需）
GATEIO_CONFIG = {
    "api_key": "your_api_key_here",      # 从 GateIO 获取
    "api_secret": "your_secret_here",    # 从 GateIO 获取
    "use_testnet": True,                  # True=测试网, False=实盘
}

# 交易参数
TRADING_CONFIG = {
    "symbol": "ETH_USDT",
    "timeframe": "5m",                    # 5分钟K线
    "initial_capital": 10000,             # 初始资金(USDT)
    "risk_per_trade": 0.02,               # 每笔交易风险2%
}
```

---

## 📦 安装步骤

### Step 1: 获取代码

```bash
# 方式1: 克隆完整仓库
git clone https://github.com/xcself-glitch/aicoding.git ~/eth-trading

# 方式2: 下载压缩包
wget https://github.com/xcself-glitch/aicoding/raw/main/ETH-Trading-Strategy-V19-5min.tar.gz
tar -xzf ETH-Trading-Strategy-V19-5min.tar.gz -C ~/eth-trading
```

### Step 2: 安装依赖

```bash
cd ~/eth-trading
pip3 install -r requirements.txt 2>/dev/null || pip3 install numpy requests pandas
```

### Step 3: 配置 API Key

```bash
# 编辑配置文件
nano config/strategy_config_v2.py

# 或使用环境变量
export GATEIO_API_KEY="your_api_key"
export GATEIO_API_SECRET="your_secret"
```

---

## ⏰ 配置 Cron 定时任务

### 方法1: 使用 OpenClaw Cron Skill

在 OpenClaw 的 `cron/jobs.json` 中添加：

```json
{
  "jobs": [
    {
      "name": "eth-trading-monitor",
      "schedule": "*/5 * * * *",
      "command": "cd ~/eth-trading && python3 scripts/eth_cron_job.py",
      "enabled": true
    }
  ]
}
```

### 方法2: 使用系统 Cron

```bash
# 编辑 crontab
crontab -e

# 添加以下行（每5分钟执行一次）
*/5 * * * * cd ~/eth-trading && python3 scripts/eth_cron_job.py >> ~/eth-trading/logs/cron.log 2>&1
```

### 方法3: 使用配置好的 Cron 文件

```bash
# 复制配置文件到 OpenClaw cron 目录
cp config/openclaw-cron.json ~/openclaw/cron/jobs.json

# 重启 OpenClaw 服务
openclaw restart
```

---

## 📱 配置飞书通知

### Step 1: 获取飞书 Webhook

1. 在飞书群聊中点击 **"设置" → "群机器人" → "添加机器人"**
2. 选择 **"自定义机器人"**
3. 复制 Webhook URL

### Step 2: 配置通知

编辑 `scripts/eth_notify_feishu.py`：

```python
FEISHU_CONFIG = {
    "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxx",
    "secret": "",  # 如果有签名密钥
}
```

或使用环境变量：

```bash
export FEISHU_WEBHOOK="https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxx"
```

### Step 3: 测试通知

```bash
python3 scripts/test_feishu_alert.py
```

---

## 📊 运行回测

### 回测所有版本

```bash
# V19 终极融合版（推荐）
python3 scripts/backtest_v19.py

# V17 高收益版
python3 scripts/backtest_v17.py

# V18 风控版
python3 scripts/backtest_v18.py

# 其他版本
python3 scripts/backtest_v13.py
python3 scripts/backtest_v15.py
python3 scripts/backtest_v16.py
```

### 生成回测报告

```bash
python3 scripts/backtest_report.py --output report.html
```

### 自定义回测参数

```python
# 在脚本中修改参数
start_date = "2024-01-01"  # 回测开始日期
end_date = "2024-12-31"    # 回测结束日期
initial_capital = 10000    # 初始资金
```

---

## 💹 启动实盘交易

### ⚠️ 风险提示

**加密货币交易风险极高，请确保：**
- 使用测试网充分测试
- 只投入可承受损失的资金
- 了解策略的最大回撤和历史表现

### Step 1: 测试网验证

```bash
# 确保配置中使用测试网
# config/strategy_config_v2.py:
# use_testnet: True

# 运行测试
python3 scripts/eth_trading_bot.py --mode test
```

### Step 2: 启动实盘

```bash
# 修改配置为实盘
# use_testnet: False

# 启动交易机器人
python3 scripts/eth_trading_bot.py --mode live

# 或使用 OpenClaw Skill 启动
openclaw skill run eth-trading --mode live
```

### Step 3: 后台运行

```bash
# 使用 nohup 后台运行
nohup python3 scripts/eth_trading_bot.py --mode live > logs/trading.log 2>&1 &

# 查看日志
tail -f logs/trading.log
```

---

## 📈 监控与日志

### 查看交易日志

```bash
# 实时查看
tail -f ~/eth-trading/logs/trading.log

# 查看最近100行
tail -n 100 ~/eth-trading/logs/trading.log
```

### 监控任务状态

```bash
# 查看 cron 任务
openclaw cron list

# 查看任务日志
openclaw logs --job eth-trading-monitor
```

### 健康检查

```bash
# 检查 OpenClaw 状态
openclaw status

# 检查策略配置
python3 scripts/test_strategy.py
```

---

## 🔧 常见问题

### Q1: 安装依赖失败

```bash
# 更新 pip
pip3 install --upgrade pip

# 使用国内镜像
pip3 install numpy requests pandas -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### Q2: API 连接失败

- 检查 API Key 和 Secret 是否正确
- 确认是否使用了正确的测试网/实盘配置
- 检查网络连接

### Q3: Cron 任务不执行

```bash
# 检查 cron 服务状态
openclaw cron status

# 手动测试任务
cd ~/eth-trading && python3 scripts/eth_cron_job.py

# 查看 cron 日志
openclaw logs --follow
```

### Q4: 飞书通知不生效

- 确认 Webhook URL 正确
- 检查网络是否可以访问飞书服务器
- 查看通知日志：`cat logs/feishu.log`

---

## 📝 策略参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `timeframe` | 5m | K线周期，建议 5m |
| `ema_fast` | 9 | 快速EMA周期 |
| `ema_slow` | 21 | 慢速EMA周期 |
| `rsi_period` | 14 | RSI周期 |
| `atr_period` | 14 | ATR周期 |
| `stop_loss_atr` | 1.5 | 止损ATR倍数 |
| `take_profit_atr` | 3.0 | 止盈ATR倍数 |
| `quality_threshold` | 70 | 入场品质阈值(0-100) |

---

## 🎯 最佳实践

1. **先回测再实盘**
   - 使用历史数据验证策略有效性
   - 了解策略在不同市场条件下的表现

2. **从小资金开始**
   - 初始投入不超过总资金的 10%
   - 逐步增加仓位

3. **持续监控**
   - 定期检查交易日志
   - 关注飞书通知
   - 及时调整策略参数

4. **风险管理**
   - 设置合理的止损
   - 分散投资
   - 不要 All-in

---

## 📚 相关文档

- [INSTALL.md](./INSTALL.md) - 详细安装指南
- [README.md](./README.md) - 项目介绍
- [config/cron-tasks.md](./config/cron-tasks.md) - 定时任务配置

---

## 💬 支持

如有问题，请通过以下方式联系：

- GitHub Issues: https://github.com/xcself-glitch/aicoding/issues
- OpenClaw 社区: https://docs.openclaw.ai

---

**⚠️ 免责声明**: 本策略仅供学习和研究使用，不构成投资建议。加密货币交易风险极高，请自行承担风险。

**更新日期**: 2026-03-15
