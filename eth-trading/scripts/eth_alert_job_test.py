#!/usr/bin/env python3
"""
ETHUSDT 交易提醒任务测试脚本
使用模拟数据测试飞书通知功能
"""

import sys
import os
from pathlib import Path
from datetime import datetime
import numpy as np

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "stock-monitor-pro" / "scripts"))

from feishu_adapter import FeishuAdapter


def generate_mock_signal():
    """生成模拟交易信号"""
    np.random.seed(int(datetime.now().timestamp()))
    
    current_price = 3500 + np.random.randn() * 100
    
    # 模拟信号数据
    scenarios = [
        {
            "type": "🟢 做多",
            "strength": 85,
            "reason": "RSI超卖(28.5) | KDJ低位金叉 | MACD金叉 | 触碰布林带下轨 | 价格低位(18%)",
            "position": 0.18,
            "is_urgent": True
        },
        {
            "type": "🔴 做空", 
            "strength": 78,
            "reason": "RSI超买(75.2) | KDJ高位死叉 | MACD死叉 | 触碰布林带上轨 | 价格高位(88%)",
            "position": 0.88,
            "is_urgent": False
        },
        {
            "type": "🟢 做多",
            "strength": 72,
            "reason": "RSI底背离 | 成交量放量 | 价格接近下轨",
            "position": 0.25,
            "is_urgent": False
        }
    ]
    
    return {
        "price": current_price,
        "scenario": scenarios[int(datetime.now().timestamp()) % len(scenarios)]
    }


def run_eth_alert_test():
    """运行 ETH 交易提醒测试"""
    print("="*60)
    print(f"🚀 ETHUSDT 交易提醒测试 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
    print("="*60)
    
    # 初始化飞书通知
    feishu = FeishuAdapter()
    
    # 生成模拟信号
    mock_data = generate_mock_signal()
    signal = mock_data["scenario"]
    current_price = mock_data["price"]
    
    print(f"\n📊 模拟数据:")
    print(f"   当前价格: {current_price:.2f} USDT")
    print(f"   信号类型: {signal['type']}")
    print(f"   信号强度: {signal['strength']}/100")
    print(f"   价格位置: {signal['position']:.1%}")
    
    # 构建通知内容
    direction = signal['type']
    
    # 计算目标价格
    if "做多" in direction:
        tp_price = current_price * 1.025
        sl_price = current_price * 0.992
        expected_return = 15.0
    else:
        tp_price = current_price * 0.975
        sl_price = current_price * 1.008
        expected_return = 15.0
    
    content = f"""**{direction}信号 detected!** (测试模式)

💰 **当前价格**: {current_price:.2f} USDT
📊 **信号强度**: {signal['strength']}/100
📍 **价格位置**: {signal['position']:.1%} (日内区间)

📈 **市场环境**:
• 24h涨跌: +{np.random.random()*5:.2f}%
• 24h最高: {current_price*1.02:.2f}
• 24h最低: {current_price*0.98:.2f}
• 资金费率: 0.01%

📋 **信号理由**:
{signal['reason']}

🎯 **建议目标**:
• 止盈: {tp_price:.2f}
• 止损: {sl_price:.2f}
• 预期收益: {expected_return:.1f}%

⚠️ **风险提示**: 10倍杠杆交易风险极高，请谨慎操作！

📦 **建议仓位**: 0.25 ETH

---
🧪 这是测试消息，用于验证飞书通知功能
    """
    
    print(f"\n📱 发送飞书通知...")
    
    # 发送通知
    result = feishu.send_message(
        f"🧪 ETHUSDT {direction}信号 | 强度{signal['strength']} (测试)",
        content,
        urgent=signal['is_urgent']
    )
    
    if result:
        print(f"\n✅ 飞书通知发送成功!")
    else:
        print(f"\n❌ 飞书通知发送失败")
    
    print(f"\n{'='*60}")
    print("测试完成")
    print(f"{'='*60}")


if __name__ == "__main__":
    run_eth_alert_test()
