#!/usr/bin/env python3
"""
个人持仓股池配置 - 国金证券账户
更新时间: 2026-03-14
数据来源: 国金证券APP持仓截图
策略版本: v2.0 (基于大盘+板块+技术面综合策略)
"""

# ============ 市场分析摘要 ============
"""
📊 大盘走势 (2026-03-14):
  - 上证指数: 4095.45 (-0.81%), 成交额10639亿
  - 深证成指: 14280.78 (-0.65%), 成交额13364亿
  - 创业板指: 3310.28 (-0.22%)
  - 科创50: 1373.64 (-0.72%)
  
🎯 策略基调:
  - 大盘弱势震荡，个股普遍浮亏
  - 整体策略: 轻仓位观望，精选加仓标的
  - 重点关注: 兆易创新、汉得信息(接近加仓点)
  - 深度套牢股: 通策医疗、三一重工(躺平策略)
"""

# ============ 持仓列表 ============
# 格式说明:
#   code: 股票代码 (6位数字)
#   name: 股票名称
#   market: 市场 (sh=上海, sz=深圳)
#   type: 类型 (individual=个股, etf=ETF)
#   cost: 持仓成本价
#   shares: 持仓数量
#   note: 备注/策略说明
#   alerts: 预警设置
#     - cost_pct_above: 成本线上方百分比预警(止盈)
#     - cost_pct_below: 成本线下方百分比预警(止损)
#     - target_buy: 目标买入价(加仓)
#     - target_reduce: 目标减仓价
#     - stop_loss: 止损价
#     - change_pct_above/below: 日内涨跌幅预警
#     - ma_monitor: 均线监控开关
#     - rsi_monitor: RSI监控开关

PORTFOLIO = [

    
    # === 个股 - 按策略优先级排序 ===
    
    # 1. 优先加仓标的 (技术面接近支撑) - 重点监控
    {
        "code": "603986",
        "name": "兆易创新",
        "market": "sh",
        "type": "individual",
        "cost": 298.69,
        "shares": 1100,
        "priority": "high",           # 重点股票 - 1分钟监控
        "note": "存储芯片龙头，浮亏-6.8%，策略:逢低加仓，第一加仓点265，止损245",
        "alerts": {
            "cost_pct_above": 10.0,      # 回本减仓
            "cost_pct_below": 12.0,      # 深套提醒
            "target_buy": 265.0,         # 加仓点(当前价278)
            "target_reduce": 310.0,      # 减仓点
            "stop_loss": 245.0,          # 止损位
            "change_pct_above": 4.0,
            "change_pct_below": 4.0,
            "ma_monitor": True,
            "rsi_monitor": True,
            "gap_monitor": True,
        }
    },
    {
        "code": "300170",
        "name": "汉得信息",
        "market": "sz",
        "type": "individual",
        "cost": 25.909,
        "shares": 2700,
        "priority": "high",           # 重点股票 - 1分钟监控
        "note": "AI智能体+信创，浮亏-9.6%，策略:逢低加仓，第一加仓点22",
        "alerts": {
            "cost_pct_above": 10.0,
            "cost_pct_below": 15.0,
            "target_buy": 22.0,          # 加仓点
            "target_reduce": 27.0,       # 减仓点
            "stop_loss": 19.0,           # 止损位
            "change_pct_above": 5.0,
            "change_pct_below": 5.0,
            "ma_monitor": True,
            "rsi_monitor": True,
        }
    },
    {
        "code": "563230",
        "name": "卫星ETF",
        "market": "sz",
        "type": "etf",
        "cost": 1.669,
        "shares": 72000,
        "priority": "high",           # 重点ETF - 1分钟监控
        "note": "卫星通信产业ETF，现浮盈+1.5%，策略:持有待涨，目标1.85减仓",
        "alerts": {
            "cost_pct_above": 10.0,      # 盈利10%提醒
            "cost_pct_below": 8.0,       # 回撤8%提醒
            "target_buy": 1.58,          # 支撑位加仓
            "target_reduce": 1.85,       # 阻力位减仓
            "change_pct_above": 3.0,
            "change_pct_below": 3.0,
            "ma_monitor": True,
            "rsi_monitor": True,
        }
    },
    
    # 2. 观望标的 (等待反弹信号)
    {
        "code": "688158",
        "name": "优刻得",
        "market": "sh",
        "type": "individual",
        "cost": 49.151,
        "shares": 1878,
        "note": "云计算科创板，浮亏-12.5%，策略:观望，等待35支撑位确认",
        "alerts": {
            "cost_pct_above": 15.0,
            "cost_pct_below": 20.0,
            "target_buy": 35.0,          # 跌破35考虑补仓
            "target_reduce": 47.0,       # 接近成本减仓
            "stop_loss": 30.0,
            "change_pct_above": 5.0,
            "change_pct_below": 5.0,
            "ma_monitor": True,
            "rsi_monitor": True,
        }
    },
    {
        "code": "002050",
        "name": "三花智控",
        "market": "sz",
        "type": "individual",
        "cost": 53.056,
        "shares": 1200,
        "note": "新能源车热管理，浮亏-10.8%，策略:观望，43支撑位",
        "alerts": {
            "cost_pct_above": 12.0,
            "cost_pct_below": 18.0,
            "target_buy": 43.0,          # 支撑位加仓
            "target_reduce": 52.0,       # 接近成本减仓
            "stop_loss": 38.0,
            "change_pct_above": 4.0,
            "change_pct_below": 4.0,
            "ma_monitor": True,
            "rsi_monitor": True,
        }
    },
    {
        "code": "600580",
        "name": "卧龙电驱",
        "market": "sh",
        "type": "individual",
        "cost": 45.895,
        "shares": 1300,
        "note": "电机+机器人，浮亏-11.8%，策略:观望，35支撑位",
        "alerts": {
            "cost_pct_above": 12.0,
            "cost_pct_below": 18.0,
            "target_buy": 35.0,
            "target_reduce": 44.0,
            "stop_loss": 32.0,
            "change_pct_above": 4.0,
            "change_pct_below": 4.0,
            "ma_monitor": True,
            "rsi_monitor": True,
        }
    },
    
    # 3. 等待反弹标的 (跌幅较大，不宜加仓)
    {
        "code": "300058",
        "name": "蓝色光标",
        "market": "sz",
        "type": "individual",
        "cost": 17.697,
        "shares": 6400,
        "note": "AI营销龙头，浮亏-15.4%，策略:等待反弹至17减仓，不加仓摊薄",
        "alerts": {
            "cost_pct_above": 10.0,      # 解套减仓
            "cost_pct_below": 25.0,      # 深套提醒
            "target_buy": None,          # 暂停加仓
            "target_reduce": 17.0,       # 解套减仓
            "stop_loss": 10.0,
            "change_pct_above": 5.0,
            "change_pct_below": 5.0,
            "ma_monitor": True,
            "rsi_monitor": True,
        }
    },
    {
        "code": "300418",
        "name": "昆仑万维",
        "market": "sz",
        "type": "individual",
        "cost": 59.638,
        "shares": 1200,
        "note": "AI应用+游戏，浮亏-15.3%，策略:等待反弹，48压力位关注",
        "alerts": {
            "cost_pct_above": 15.0,
            "cost_pct_below": 25.0,
            "target_buy": None,          # 暂停加仓
            "target_reduce": 55.0,       # 接近成本减仓
            "stop_loss": 38.0,
            "change_pct_above": 5.0,
            "change_pct_below": 5.0,
            "ma_monitor": True,
            "rsi_monitor": True,
        }
    },
    {
        "code": "600143",
        "name": "金发科技",
        "market": "sh",
        "type": "individual",
        "cost": 21.034,
        "shares": 2000,
        "note": "新材料，浮亏-15.3%，策略:等待反弹至20减仓",
        "alerts": {
            "cost_pct_above": 15.0,
            "cost_pct_below": 25.0,
            "target_buy": None,          # 暂停加仓
            "target_reduce": 20.0,       # 减仓
            "stop_loss": 12.0,
            "change_pct_above": 4.0,
            "change_pct_below": 4.0,
            "ma_monitor": True,
            "rsi_monitor": True,
        }
    },
    
    # 4. 深度套牢/躺平标的
    {
        "code": "600763",
        "name": "通策医疗",
        "market": "sh",
        "type": "individual",
        "cost": 106.095,
        "shares": 1240,
        "note": "口腔医疗龙头，深套-58%，策略:躺平，40以下可考虑补仓摊薄成本",
        "alerts": {
            "cost_pct_above": 50.0,      # 大幅反弹提醒
            "cost_pct_below": 70.0,      # 深套提醒
            "target_buy": 40.0,          # 极端低位补仓摊薄
            "target_reduce": 60.0,       # 反弹减仓
            "stop_loss": None,           # 已深套不设止损
            "change_pct_above": 6.0,
            "change_pct_below": 6.0,
            "ma_monitor": True,
            "rsi_monitor": True,
        }
    },
    {
        "code": "600031",
        "name": "三一重工",
        "market": "sh",
        "type": "individual",
        "cost": 105.58,
        "shares": 100,
        "note": "工程机械，极端深套-79%，策略:躺平，18以下补仓摊薄",
        "alerts": {
            "cost_pct_above": 80.0,
            "cost_pct_below": 90.0,
            "target_buy": 18.0,          # 极端低位补仓
            "target_reduce": 25.0,       # 反弹减仓
            "stop_loss": None,
            "change_pct_above": 5.0,
            "change_pct_below": 5.0,
            "ma_monitor": True,
            "rsi_monitor": True,
        }
    },
]

# ============ 持仓统计 ============
PORTFOLIO_STATS = {
    "total_stocks": 11,
    "total_etfs": 1,
    "total_individual": 10,
    "update_date": "2026-03-14",
    "strategy_version": "v2.0",
    "market_condition": "震荡偏弱",
}

# ============ 全局预警设置 ============
GLOBAL_ALERTS = {
    "cooldown_minutes": 30,      # 同类预警30分钟内只发一次
    "daily_report": True,        # 收盘日报
    "market_open_alert": True,   # 开盘简报
    "strategy_update_interval": 1,  # 策略更新间隔(天)
}

# ============ 买卖策略矩阵 ============
STRATEGY_MATRIX = {
    "加仓策略": {
        "兆易创新": {"price": 265, "reason": "技术面支撑，浮亏可控"},
        "汉得信息": {"price": 22, "reason": "AI智能体热点，回调到位"},
    },
    "减仓策略": {
        "卫星ETF": {"price": 1.85, "reason": "接近前高阻力位"},
        "通策医疗": {"price": 60, "reason": "深套股反弹减仓"},
        "三一重工": {"price": 25, "reason": "深套股反弹减仓"},
    },
    "观望策略": [
        "蓝色光标", "昆仑万维", "金发科技",  # 跌幅较大不加仓
        "优刻得", "三花智控", "卧龙电驱",    # 等待明确信号
    ]
}

if __name__ == "__main__":
    print("=" * 70)
    print("个人持仓股池配置")
    print("=" * 70)
    print(f"\n总持仓: {PORTFOLIO_STATS['total_stocks']} 只")
    print(f"  - ETF: {PORTFOLIO_STATS['total_etfs']} 只")
    print(f"  - 个股: {PORTFOLIO_STATS['total_individual']} 只")
    print(f"\n更新时间: {PORTFOLIO_STATS['update_date']}")
    print(f"策略版本: {PORTFOLIO_STATS['strategy_version']}")
    print(f"市场环境: {PORTFOLIO_STATS['market_condition']}")
    print("\n" + "-" * 70)
    print("\n📋 当前策略重点:")
    print("  1. 优先加仓: 兆易创新(265)、汉得信息(22)")
    print("  2. 持有待涨: 卫星ETF(目标1.85减仓)")
    print("  3. 观望等待: 其他标的等待明确信号")
    print("  4. 深套躺平: 通策医疗、三一重工")
    print("-" * 70)
