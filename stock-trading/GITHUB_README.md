# 📈 股票交易策略与消息通知系统

专业级A股投资组合监控与交易策略回测系统，支持飞书消息通知。

---

## 🎯 系统特点

### 核心功能
- ✅ **7大预警规则**: 成本百分比、日内涨跌幅、成交量异动、均线金叉死叉、RSI超买超卖、跳空缺口、动态止盈
- ✅ **多策略回测**: RSI、布林带、MACD、均线交叉、多因子综合策略
- ✅ **飞书通知**: 实时预警推送到飞书群
- ✅ **自动监控**: 交易日全流程自动监控

### 技术亮点
- 🚀 **回测优化**: 基于交易理论的策略优化（趋势跟踪+均值回归动态切换）
- 📊 **Kelly仓位管理**: 最优仓位计算
- 🛡️ **ATR动态止损**: 自适应波动率止损
- 🧠 **市场状态检测**: 自动识别趋势/震荡/高波动市场

---

## 📁 文件结构

```
stock-trading/
├── config/                          # 配置文件
│   ├── my_portfolio.py             # 持仓配置（11只股票）
│   ├── zhaoyi_config.py            # 单股配置示例
│   └── openclaw-cron.json          # 定时任务配置
│
├── scripts/                         # 核心脚本
│   ├── backtest_portfolio.py       # 多策略回测（5种策略）
│   ├── backtest_optimized.py       # 优化版回测（V2.0）
│   ├── monitor_portfolio.py        # 全仓监控
│   ├── portfolio_trading_day.py    # 交易日全流程监控
│   ├── notify_feishu.py            # 飞书通知
│   ├── feishu_adapter.py           # 飞书适配器
│   ├── analyser.py                 # 智能分析引擎
│   ├── control_portfolio.sh        # 全仓控制脚本
│   ├── control_trading_day.sh      # 交易日控制
│   └── setup_feishu.sh             # 飞书设置脚本
│
├── reports/                         # 报告输出
│   └── strategy_*.json             # 策略报告
│
├── SKILL.md                         # 完整使用文档
├── BACKTEST_REPORT.md              # 回测分析报告
├── FEISHU_SETUP.md                 # 飞书配置指南
├── README.md                        # 项目说明
└── setup_zhaoyi_monitor.sh         # 一键设置脚本
```

---

## 🚀 快速开始

### 1. 安装依赖

```bash
pip3 install numpy pandas requests
```

### 2. 配置持仓

编辑 `config/my_portfolio.py`，填入你的股票和成本价：

```python
PORTFOLIO = [
    {
        "code": "603986",
        "name": "兆易创新",
        "cost": 298.69,          # 你的成本价
        "shares": 1100,          # 持仓数量
        "alerts": {
            "cost_pct_above": 10.0,   # 盈利10%提醒
            "cost_pct_below": 10.0,   # 亏损10%提醒
            "change_pct_above": 4.0,  # 日内大涨4%
            "change_pct_below": 4.0,  # 日内大跌4%
        }
    },
    # ... 添加更多股票
]
```

### 3. 配置飞书通知

```bash
# 运行飞书设置脚本
bash scripts/setup_feishu.sh

# 或手动编辑
export FEISHU_WEBHOOK="https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxx"
```

### 4. 运行回测

```bash
# 多策略回测（对比5种策略）
python3 scripts/backtest_portfolio.py

# 优化版回测（V2.0）
python3 scripts/backtest_optimized.py
```

### 5. 启动监控

```bash
# 启动交易日全流程监控（推荐）
./scripts/control_trading_day.sh start

# 查看状态
./scripts/control_trading_day.sh status

# 查看日志
./scripts/control_trading_day.sh log

# 生成盘前简报
./scripts/control_trading_day.sh pre-market
```

---

## 📊 回测结果

### 最佳策略推荐

| 股票 | 推荐策略 | 回测收益 | 胜率 |
|------|----------|----------|------|
| 兆易创新 | RSI超买超卖 | **+19.33%** | 100% |
| 汉得信息 | 布林带均值回归 | **+14.11%** | 100% |
| 卫星ETF | 均线交叉 | -1.92% (回撤最小) | 21.4% |
| 昆仑万维 | RSI超买超卖 | -0.45% (回撤最小) | 50% |

### 策略说明

1. **RSI策略**: RSI<30买入，RSI>70卖出
   - 适合: 科技股、波动大的股票
   - 优点: 高胜率，捕捉反转

2. **布林带策略**: 触及下轨买入，触及上轨卖出
   - 适合: 高波动成长股
   - 优点: 均值回归收益高

3. **MACD策略**: 金叉买入，死叉卖出
   - 适合: 趋势明确的行情
   - 优点: 趋势跟踪效果好

4. **均线交叉**: MA5上穿MA10买入
   - 适合: ETF、趋势股
   - 优点: 简单直观

5. **多因子综合**: 结合多个指标
   - 适合: 平衡型投资
   - 优点: 多条件共振更可靠

---

## 🔔 预警规则

### 成本百分比预警
```python
"cost_pct_above": 15.0,    # 盈利15%提醒
"cost_pct_below": -12.0,   # 亏损12%提醒
```

### 日内涨跌幅预警
```python
"change_pct_above": 4.0,   # 个股大涨4%
"change_pct_below": -4.0,  # 个股大跌4%
```

### 技术指标预警
```python
"ma_monitor": True,        # 均线金叉死叉
"rsi_monitor": True,       # RSI超买超卖
"gap_monitor": True,       # 跳空缺口
"trailing_stop": True      # 动态止盈
```

---

## 📱 飞书通知示例

### 紧急预警（多条件共振）
```
🚨【紧急】🔴 江西铜业 (600362)
━━━━━━━━━━━━━━━━━━━━
💰 当前价格: ¥65.50 (+15.0%)
📊 持仓成本: ¥57.00 | 盈亏: 🔴+14.9%

🎯 触发预警 (3项):
  • 🎯 盈利 15% (目标价 ¥65.55)
  • 🌟 均线金叉 (MA5¥63.2上穿MA10¥62.8)
  • 📊 放量 2.5倍 (5日均量)

💡 Kimi建议:
🚀 多条件共振，趋势强劲，可考虑继续持有或分批减仓。
```

### 盘前简报
```
======================================================================
🌅 盘前简报
======================================================================
📅 日期: 2026年03月14日 星期六

📊 今日交易提示:
   A股开盘时间: 09:30
   集合竞价: 09:15-09:25
   上午收盘: 11:30
   下午开盘: 13:00
   下午收盘: 15:00

💰 当前持仓概况:
   总成本:   ¥   1,103,327.78
   总市值:   ¥     930,827.98
   总盈亏:   🟢¥    -172,499.80 (-15.63%)

⚠️ 重点关注股票:
   ⚠️  蓝色光标: 浮亏 -15.4%，关注反弹
   🚨 通策医疗: 深套 -58.1%，建议关注止损机会

💡 今日操作建议:
   1. 深套股票(2只): 建议观望，暂不加仓摊薄
   2. 整体策略: 控制仓位，等待市场企稳信号
```

---

## ⚙️ 交易日监控节奏

| 时间 | 动作 | 说明 |
|------|------|------|
| 08:30 | 🌅 **盘前简报** | 持仓概况 + 风险提示 + 今日操作建议 |
| 09:15 | 📈 **开盘建议** | 集合竞价分析 + 操作策略 |
| **09:30-11:30** | 🔍 **上午盘中监控** | 每10分钟扫描，异动提醒 |
| **11:31-12:59** | ⏸️ **午休** | **A股休市，暂停监控** |
| **13:00-15:00** | 🔍 **下午盘中监控** | 每10分钟扫描，异动提醒 |
| 15:30 | 🌙 **收盘复盘** | 当日总结 + 明日建议 |

---

## 🛠️ 常用命令

```bash
# 启动/停止监控
./scripts/control_trading_day.sh start
./scripts/control_trading_day.sh stop

# 查看状态
./scripts/control_trading_day.sh status
./scripts/control_trading_day.sh log

# 手动生成报告
./scripts/control_trading_day.sh pre-market  # 盘前简报
./scripts/control_trading_day.sh open        # 开盘建议
./scripts/control_trading_day.sh intraday    # 盘中检查
./scripts/control_trading_day.sh close       # 收盘复盘
./scripts/control_trading_day.sh check       # 即时持仓检查

# 回测
python3 scripts/backtest_portfolio.py
python3 scripts/backtest_optimized.py
```

---

## 📚 文档索引

| 文档 | 说明 |
|------|------|
| [SKILL.md](./SKILL.md) | 完整使用文档和配置说明 |
| [BACKTEST_REPORT.md](./BACKTEST_REPORT.md) | 策略回测分析报告 |
| [FEISHU_SETUP.md](./FEISHU_SETUP.md) | 飞书配置详细指南 |
| [README.md](./README.md) | 项目简介 |

---

## ⚠️ 风险提示

1. **本系统仅供学习和研究使用，不构成投资建议**
2. **加密货币和股票交易风险极高，请自行承担风险**
3. **回测结果不代表未来收益，实盘可能有滑点和延迟**
4. **请根据自身风险承受能力调整仓位和止损**

---

## 📝 更新日志

- **2026-03-15**: 添加多策略回测系统
- **2026-03-15**: 添加优化版回测（V2.0）
- **2026-03-15**: 添加完整回测分析报告
- **2026-03-14**: 交易日全流程监控
- **2026-03-13**: 7大预警规则完善

---

## 💬 支持

如有问题，请通过以下方式联系：

- GitHub Issues: https://github.com/xcself-glitch/aicoding/issues
- OpenClaw 社区: https://docs.openclaw.ai

---

**免责声明**: 本策略仅供学习和研究使用，不构成投资建议。股票市场风险极高，请自行承担风险。

**更新日期**: 2026-03-15
