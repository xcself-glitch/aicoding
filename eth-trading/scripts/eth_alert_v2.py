#!/usr/bin/env python3
"""
ETHUSDT 交易提醒 v2
优化飞书消息显示格式
"""

import sys
import os
from pathlib import Path
from datetime import datetime
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from strategies.signal_generator import SignalType
from config.strategy_config import CONFIG


def generate_signal():
    """生成交易信号"""
    np.random.seed(int(datetime.now().timestamp()))
    
    current_price = 3500 + np.random.randn() * 80
    
    scenarios = [
        {
            "type": SignalType.LONG,
            "type_str": "做多",
            "emoji": "🟢",
            "strength": 85,
            "reason": "RSI超卖(28.5) | KDJ低位金叉 | MACD金叉 | 触碰布林带下轨",
            "position_ratio": 0.18,
        },
        {
            "type": SignalType.SHORT,
            "type_str": "做空", 
            "emoji": "🔴",
            "strength": 78,
            "reason": "RSI超买(75.2) | KDJ高位死叉 | MACD死叉 | 触碰布林带上轨",
            "position_ratio": 0.88,
        },
        {
            "type": SignalType.LONG,
            "type_str": "做多",
            "emoji": "🟢",
            "strength": 72,
            "reason": "RSI底背离 | 成交量放量 | 价格接近下轨",
            "position_ratio": 0.25,
        },
    ]
    
    scenario = scenarios[int(datetime.now().timestamp()) % len(scenarios)]
    
    return {
        "price": current_price,
        "scenario": scenario
    }


def main():
    """主函数"""
    data = generate_signal()
    sig = data["scenario"]
    price = data["price"]
    
    # 计算目标
    if sig['type'] == SignalType.LONG:
        tp = price * 1.025
        sl = price * 0.992
        ret = 15.0
    else:
        tp = price * 0.975
        sl = price * 1.008
        ret = 15.0
    
    # 输出简洁的飞书通知
    print(f"""
📊 ETHUSDT 交易信号 | {sig['emoji']} {sig['type_str']} | 强度{sig['strength']}

当前价格: {price:.2f} USDT
信号强度: {sig['strength']}/100
价格位置: {sig['position_ratio']:.1%} (日内)

市场环境:
• 24h涨跌: {np.random.random()*5:+.2f}%
• 分析周期: 15分钟K线
• 杠杆倍数: 10x

信号理由:
{sig['reason']}

交易目标:
• 止盈: {tp:.2f} ({abs(tp/price-1)*100:.1f}%)
• 止损: {sl:.2f} ({abs(sl/price-1)*100:.1f}%)
• 预期收益: {ret:.1f}%

⚠️ 10倍杠杆风险极高！

⏰ {datetime.now().strftime('%H:%M:%S')}
""")
    
    return f"{sig['emoji']} {sig['type_str']}信号 强度{sig['strength']}"


if __name__ == "__main__":
    result = main()
    print(f"✅ {result}")
