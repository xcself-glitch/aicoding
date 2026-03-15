#!/usr/bin/env python3
"""
ETHUSDT 交易提醒任务脚本
用于定时任务触发，只在有交易信号时发送飞书通知
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 导入飞书通知
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "stock-monitor-pro" / "scripts"))
from feishu_adapter import FeishuAdapter

from strategies.binance_client import BinanceFuturesClient, klines_to_arrays
from strategies.signal_generator import SignalGenerator, SignalType


def run_eth_alert():
    """运行 ETH 交易提醒"""
    print("="*60)
    print(f"🚀 ETHUSDT 交易提醒任务 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
    print("="*60)
    
    # 初始化
    client = BinanceFuturesClient()
    generator = SignalGenerator()
    feishu = FeishuAdapter()
    
    try:
        # 获取实时数据
        print("\n📊 获取 ETHUSDT 数据...")
        data = client.get_realtime_data_for_strategy("ETHUSDT")
        
        if not data:
            print("❌ 无法获取数据，任务结束")
            feishu.send_message(
                "⚠️ ETH交易提醒异常",
                "无法获取币安API数据，请检查网络连接",
                urgent=True
            )
            return
        
        klines = data['klines_15m']
        ticker = data['ticker_24h']
        current_price = data['current_price']
        
        # 设置日内数据
        generator.daily_high = ticker.high_price
        generator.daily_low = ticker.low_price
        generator.daily_open = ticker.open_price
        
        # 转换K线数据
        opens, highs, lows, closes, volumes = klines_to_arrays(klines)
        
        # 生成交易信号
        print("\n📈 分析交易信号...")
        signal = generator.generate_signal(
            opens, highs, lows, closes, volumes,
            current_position=None  # 假设当前无持仓
        )
        
        print(f"\n{signal}")
        
        # 只在有交易信号时发送通知
        if signal.type in [SignalType.LONG, SignalType.SHORT]:
            # 有交易信号，发送飞书通知
            direction = "🟢 做多" if signal.type == SignalType.LONG else "🔴 做空"
            
            # 计算价格位置
            price_position = (current_price - ticker.low_price) / (ticker.high_price - ticker.low_price)
            
            content = f"""**{direction}信号 detected!**

💰 **当前价格**: {current_price:.2f} USDT
📊 **信号强度**: {signal.strength:.0f}/100
📍 **价格位置**: {price_position:.1%} (日内区间)

📈 **市场环境**:
• 24h涨跌: {ticker.price_change_percent:+.2f}%
• 24h最高: {ticker.high_price:.2f}
• 24h最低: {ticker.low_price:.2f}
• 资金费率: {data['funding_rate']:.4%}

📋 **信号理由**:
{signal.reason}

🎯 **建议目标**:
"""
            if signal.targets:
                content += f"""• 止盈: {signal.targets.get('take_profit', 0):.2f}
• 止损: {signal.targets.get('stop_loss', 0):.2f}
• 预期收益: {signal.targets.get('leveraged_return', 0)*100:.1f}%
"""
            
            content += f"""
⚠️ **风险提示**: 10倍杠杆交易风险极高，请谨慎操作！

📦 **建议仓位**: {signal.position_size:.4f} ETH
            """
            
            # 发送通知
            is_urgent = signal.strength >= 80
            feishu.send_message(
                f"🚨 ETHUSDT {direction}信号 | 强度{signal.strength:.0f}",
                content,
                urgent=is_urgent
            )
            
            print(f"\n✅ 交易信号通知已发送 (强度: {signal.strength:.0f})")
            
        elif signal.type == SignalType.HOLD and signal.strength > 0:
            # 观望但有分析价值，可以记录但不通知
            print(f"\n💡 当前观望状态，信号强度不足以触发交易")
            print(f"   理由: {signal.reason}")
            
        else:
            print(f"\n⏸️ 无交易信号，继续观望")
            print(f"   {signal.reason}")
        
        # 显示当前市场状态摘要
        print(f"\n📊 市场摘要:")
        print(f"   ETH价格: {current_price:.2f} USDT")
        print(f"   24h涨跌: {ticker.price_change_percent:+.2f}%")
        print(f"   24h区间: {ticker.low_price:.2f} - {ticker.high_price:.2f}")
        
    except Exception as e:
        print(f"\n❌ 任务异常: {e}")
        import traceback
        traceback.print_exc()
        
        # 发送异常通知
        feishu.send_message(
            "⚠️ ETH交易提醒异常",
            f"任务执行异常:\n```\n{str(e)[:200]}\n```",
            urgent=True
        )


if __name__ == "__main__":
    run_eth_alert()
