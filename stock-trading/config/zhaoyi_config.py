#!/usr/bin/env python3
"""
兆易创新持仓监控配置
持仓: 1100股, 成本: ¥298.69, 现价: ¥278.33, 浮亏: -6.82%
"""

WATCHLIST = [
    {
        "code": "603986",
        "name": "兆易创新",
        "market": "sh",
        "type": "individual",
        "cost": 298.69,
        "shares": 1100,
        "note": "存储芯片龙头，AI算力+国产替代双驱动",
        "alerts": {
            # === 成本百分比预警 ===
            "cost_pct_above": 10.0,      # 盈利10%提醒 (¥328.56)
            "cost_pct_below": -10.0,     # 亏损扩大至10%提醒 (¥268.82)
            
            # === 目标买卖点 ===
            "target_buy": 270.0,         # 补仓点 ¥270 (强支撑位)
            "target_reduce": 295.0,      # 减仓点 ¥295 (接近成本线)
            "stop_loss": 265.0,          # 止损价 ¥265 (跌破支撑)
            
            # === 日内异动预警 ===
            "change_pct_above": 4.0,     # 日内大涨4%提醒
            "change_pct_below": -4.0,    # 日内大跌4%提醒
            
            # === 成交量预警 ===
            "volume_surge": 2.0,         # 放量2倍提醒
            
            # === 技术指标监控 ===
            "ma_monitor": True,          # 均线金叉死叉
            "rsi_monitor": True,         # RSI超买超卖
            "gap_monitor": True,         # 跳空缺口
            "trailing_stop": True,       # 动态止盈
        }
    }
]

# 通知配置
NOTIFICATION = {
    "enabled": True,
    "channels": ["console"],  # 可扩展为 feishu/wechat/email
    "cooldown_minutes": 30,   # 同类预警30分钟内只发一次
    "daily_report": True,     # 收盘日报
}
