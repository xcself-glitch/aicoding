#!/usr/bin/env python3
"""
ETHUSDT 交易提醒 - OpenClaw 环境专用
使用 openclaw 内置工具发送飞书消息
"""

import sys
import os
import json
import subprocess
from pathlib import Path
from datetime import datetime
import numpy as np

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from strategies.signal_generator import SignalType
from config.strategy_config import CONFIG


def send_feishu_via_openclaw(title: str, content: str):
    """使用 openclaw 工具发送飞书消息"""
    try:
        # 构建完整消息
        full_content = f"**{title}**\n\n{content}\n\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        # 使用 openclaw tools call feishu_im_user_message
        cmd = [
            "openclaw", "tools", "call", "feishu_im_user_message",
            "--params", json.dumps({
                "action": "send",
                "msg_type": "text",
                "content": json.dumps({"text": full_content})
            })
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            print(f"✅ 飞书通知已发送: {title}")
            return True
        else:
            print(f"⚠️ 发送失败: {result.stderr[:200]}")
            return False
            
    except Exception as e:
        print(f"❌ 发送异常: {e}")
        return False


def generate_mock_signal():
    """生成模拟交易信号（用于测试）"""
    np.random.seed(int(datetime.now().timestamp()))
    
    current_price = 3500 + np.random.randn() * 100
    
    scenarios = [
        {
            "type": SignalType.LONG,
            "type_str": "🟢 做多",
            "strength": 85,
            "reason": "RSI超卖(28.5) | KDJ低位金叉 | MACD金叉 | 触碰布林带下轨 | 价格低位(18%)",
            "position_ratio": 0.18,
            "is_urgent": True
        },
        {
            "type": SignalType.SHORT,
            "type_str": "🔴 做空", 
            "strength": 78,
            "reason": "RSI超买(75.2) | KDJ高位死叉 | MACD死叉 | 触碰布林带上轨 | 价格高位(88%)",
            "position_ratio": 0.88,
            "is_urgent": False
        },
        {
            "type": SignalType.HOLD,
            "type_str": "⏸️ 观望",
            "strength": 45,
            "reason": "指标信号不一致，继续观望 | 多:45 空:52",
            "position_ratio": 0.50,
            "is_urgent": False
        }
    ]
    
    return {
        "price": current_price,
        "scenario": scenarios[int(datetime.now().timestamp()) % len(scenarios)]
    }


def run_eth_alert():
    """运行 ETH 交易提醒"""
    print("="*60)
    print(f"🚀 ETHUSDT 交易提醒 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
    print("="*60)
    
    # 生成模拟信号（实际使用时替换为真实数据获取）
    mock_data = generate_mock_signal()
    signal = mock_data["scenario"]
    current_price = mock_data["price"]
    
    print(f"\n📊 ETHUSDT 分析:")
    print(f"   当前价格: {current_price:.2f} USDT")
    print(f"   信号类型: {signal['type_str']}")
    print(f"   信号强度: {signal['strength']}/100")
    
    # 只在有交易信号时发送通知
    if signal['type'] in [SignalType.LONG, SignalType.SHORT]:
        print(f"\n🔔 检测到交易信号，准备发送飞书通知...")
        
        direction = signal['type_str']
        price_position = signal['position_ratio']
        
        # 计算目标价格
        if signal['type'] == SignalType.LONG:
            tp_price = current_price * 1.025
            sl_price = current_price * 0.992
            expected_return = 15.0
            position_desc = "低位区间" if price_position < 0.25 else "中位区间"
        else:
            tp_price = current_price * 0.975
            sl_price = current_price * 1.008
            expected_return = 15.0
            position_desc = "高位区间" if price_position > 0.75 else "中位区间"
        
        # 构建通知内容
        content = f"""💰 **当前价格**: {current_price:.2f} USDT
📊 **信号强度**: {signal['strength']}/100
📍 **价格位置**: {price_position:.1%} ({position_desc})

📈 **市场环境**:
• 24h涨跌: {np.random.random()*6-2:+.2f}%
• 分析周期: 15分钟K线
• 杠杆倍数: {CONFIG.leverage.leverage}x

📋 **信号理由**:
{signal['reason']}

🎯 **交易目标**:
• 止盈: {tp_price:.2f} USDT ({abs(tp_price/current_price-1)*100:.1f}%)
• 止损: {sl_price:.2f} USDT ({abs(sl_price/current_price-1)*100:.1f}%)
• 预期收益: {expected_return:.1f}% (杠杆后)

⚠️ **风险提示**: 10倍杠杆交易风险极高，建议仓位不超过本金的10%！

💡 **操作建议**:
信号强度{signal['strength']}分，{'强烈建议' if signal['strength'] >= 80 else '建议'}关注此交易机会。
        """
        
        # 发送飞书通知
        title = f"🚨 ETHUSDT {direction}信号 | 强度{signal['strength']}"
        send_feishu_via_openclaw(title, content)
        
    else:
        print(f"\n💡 无交易信号，继续观望")
        print(f"   {signal['reason']}")
    
    print(f"\n{'='*60}")
    print("任务完成")
    print(f"{'='*60}")


if __name__ == "__main__":
    run_eth_alert()
