#!/usr/bin/env python3
"""
ETHUSDT 实时交易监控
使用币安API获取真实数据
"""

import sys
import os
from pathlib import Path
from datetime import datetime
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from strategies.binance_client import BinanceFuturesClient, klines_to_arrays
from strategies.signal_generator import SignalGenerator, SignalType
from config.strategy_config import CONFIG, get_profit_target


def main():
    """主函数"""
    print("="*60)
    print(f"🚀 ETHUSDT 实时交易监控 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
    print("="*60)
    
    client = BinanceFuturesClient()
    generator = SignalGenerator()
    
    try:
        # 获取数据
        print("\n📊 获取币安数据...")
        data = client.get_realtime_data_for_strategy("ETHUSDT")
        
        if not data:
            print("❌ 无法获取数据")
            print("\n⚠️ 币安API访问受限，请检查网络连接")
            print("提示: 可以使用代理服务器访问币安API")
            return "数据获取失败"
        
        klines = data['klines_15m']
        ticker = data['ticker_24h']
        current_price = data['current_price']
        
        # 设置日内数据
        generator.daily_high = ticker.high_price
        generator.daily_low = ticker.low_price
        
        # 转换数据
        opens, highs, lows, closes, volumes = klines_to_arrays(klines)
        
        # 生成信号
        signal = generator.generate_signal(
            opens, highs, lows, closes, volumes,
            current_position=None
        )
        
        print(f"\n💰 ETH/USDT: {current_price:.2f}")
        print(f"   24h涨跌: {ticker.price_change_percent:+.2f}%")
        print(f"   24h区间: {ticker.low_price:.2f} - {ticker.high_price:.2f}")
        print(f"\n📈 信号: {signal.type.value} | 强度: {signal.strength:.0f}")
        print(f"   {signal.reason}")
        
        # 如果有交易信号，输出详细通知
        if signal.type in [SignalType.LONG, SignalType.SHORT]:
            direction = "🟢 做多" if signal.type == SignalType.LONG else "🔴 做空"
            is_long = signal.type == SignalType.LONG
            
            # 计算价格位置
            price_pos = (current_price - ticker.low_price) / (ticker.high_price - ticker.low_price)
            profit_cfg = get_profit_target(price_pos, is_long)
            
            if is_long:
                tp = current_price * (1 + profit_cfg['optimal'])
                sl = current_price * (1 - CONFIG.risk.stop_loss_pct)
            else:
                tp = current_price * (1 - profit_cfg['optimal'])
                sl = current_price * (1 + CONFIG.risk.stop_loss_pct)
            
            print(f"\n{'='*60}")
            print(f"📢 🚨 ETHUSDT {direction}信号")
            print(f"{'='*60}")
            print(f"""
**{direction}交易信号**

💰 当前价格: {current_price:.2f} USDT
📊 信号强度: {signal.strength:.0f}/100
📍 价格位置: {price_pos:.1%} (日内区间)

📈 市场环境:
• 24h涨跌: {ticker.price_change_percent:+.2f}%
• 24h最高: {ticker.high_price:.2f}
• 24h最低: {ticker.low_price:.2f}
• 资金费率: {data['funding_rate']:.4%}

📋 信号理由:
{signal.reason}

🎯 交易目标:
• 止盈: {tp:.2f} USDT ({profit_cfg['optimal']*100:.1f}%)
• 止损: {sl:.2f} USDT ({CONFIG.risk.stop_loss_pct*100:.1f}%)
• 预期收益: {profit_cfg['leveraged_return']*100:.1f}%

⚠️ 风险提示: {CONFIG.leverage.leverage}倍杠杆风险极高，建议仓位不超过本金10%！

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """)
            print(f"{'='*60}")
            
            return f"🚨 {direction}信号 | 强度{signal.strength:.0f} | 价格{current_price:.2f}"
        else:
            print(f"\n⏸️ 当前状态: {signal.reason}")
            return f"观望 | {signal.reason[:50]}"
            
    except Exception as e:
        print(f"\n❌ 监控异常: {e}")
        import traceback
        traceback.print_exc()
        return f"异常: {str(e)[:50]}"


if __name__ == "__main__":
    result = main()
    print(f"\n✅ 监控结果: {result}")
