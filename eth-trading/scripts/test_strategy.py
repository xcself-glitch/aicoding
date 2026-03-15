#!/usr/bin/env python3
"""
ETH策略离线测试
使用模拟数据验证策略逻辑
"""

import sys
import os
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from strategies.signal_generator import SignalGenerator, SignalType
from strategies.indicators import TechnicalIndicators
from config.strategy_config import CONFIG


def generate_mock_data(scenario: str = "range_bound", periods: int = 200) -> dict:
    """
    生成模拟K线数据
    
    Args:
        scenario: 场景类型
            - "range_bound": 震荡市
            - "uptrend": 上涨趋势
            - "downtrend": 下跌趋势
            - "breakout_up": 向上突破
            - "breakout_down": 向下突破
        periods: 数据周期数
    """
    np.random.seed(42)
    base_price = 3500
    
    if scenario == "range_bound":
        # 震荡市 - 适合反转策略
        prices = []
        for i in range(periods):
            # 模拟区间波动
            cycle = np.sin(i / 20) * 100
            noise = np.random.randn() * 15
            price = base_price + cycle + noise
            prices.append(price)
    
    elif scenario == "uptrend":
        # 上涨趋势
        prices = [base_price + i * 2 + np.random.randn() * 20 for i in range(periods)]
    
    elif scenario == "downtrend":
        # 下跌趋势
        prices = [base_price - i * 2 + np.random.randn() * 20 for i in range(periods)]
    
    elif scenario == "breakout_up":
        # 向上突破
        prices = []
        for i in range(periods):
            if i < periods * 0.7:
                price = base_price + np.random.randn() * 30  # 盘整
            else:
                price = base_price + (i - periods * 0.7) * 5 + np.random.randn() * 20
            prices.append(price)
    
    elif scenario == "breakout_down":
        # 向下突破
        prices = []
        for i in range(periods):
            if i < periods * 0.7:
                price = base_price + np.random.randn() * 30
            else:
                price = base_price - (i - periods * 0.7) * 5 + np.random.randn() * 20
            prices.append(price)
    
    else:
        prices = [base_price + np.random.randn() * 50 for _ in range(periods)]
    
    # 生成OHLCV
    closes = prices
    highs = [c + abs(np.random.randn()) * 10 for c in closes]
    lows = [c - abs(np.random.randn()) * 10 for c in closes]
    opens = [closes[i-1] if i > 0 else c for i, c in enumerate(closes)]
    volumes = [10000 + np.random.randn() * 3000 for _ in range(periods)]
    
    return {
        'opens': opens,
        'highs': highs,
        'lows': lows,
        'closes': closes,
        'volumes': volumes
    }


def test_indicators():
    """测试技术指标计算"""
    print("="*70)
    print("📊 技术指标测试")
    print("="*70)
    
    # 生成震荡市数据
    data = generate_mock_data("range_bound", 100)
    
    ti = TechnicalIndicators()
    
    # RSI
    rsi_values = ti.calculate_rsi(data['closes'])
    print(f"\n1. RSI 计算:")
    print(f"   最新值: {rsi_values[-1]:.2f}")
    print(f"   周期: {CONFIG.rsi.period}")
    print(f"   超买阈值: {CONFIG.rsi.overbought}")
    print(f"   超卖阈值: {CONFIG.rsi.oversold}")
    
    # KDJ
    k, d, j = ti.calculate_kdj(data['highs'], data['lows'], data['closes'])
    print(f"\n2. KDJ 计算:")
    print(f"   K={k[-1]:.2f}, D={d[-1]:.2f}, J={j[-1]:.2f}")
    
    # MACD
    macd, signal, hist = ti.calculate_macd(data['closes'])
    print(f"\n3. MACD 计算:")
    print(f"   MACD={macd[-1]:.4f}")
    print(f"   信号线={signal[-1]:.4f}")
    print(f"   柱状图={hist[-1]:.4f}")
    
    # 布林带
    upper, middle, lower = ti.calculate_bollinger(data['closes'])
    print(f"\n4. 布林带 计算:")
    print(f"   上轨={upper[-1]:.2f}")
    print(f"   中轨={middle[-1]:.2f}")
    print(f"   下轨={lower[-1]:.2f}")
    print(f"   带宽={(upper[-1]-lower[-1])/middle[-1]:.2%}")


def test_signal_generation():
    """测试信号生成"""
    print("\n" + "="*70)
    print("📈 信号生成测试")
    print("="*70)
    
    scenarios = [
        ("震荡市", "range_bound"),
        ("上涨趋势", "uptrend"),
        ("下跌趋势", "downtrend"),
    ]
    
    for name, scenario in scenarios:
        print(f"\n{'='*50}")
        print(f"场景: {name}")
        print(f"{'='*50}")
        
        # 生成数据
        data = generate_mock_data(scenario, 100)
        
        # 创建信号生成器
        generator = SignalGenerator()
        generator.daily_high = max(data['highs'][-20:])
        generator.daily_low = min(data['lows'][-20:])
        
        # 生成信号
        signal = generator.generate_signal(
            data['opens'], data['highs'], data['lows'], 
            data['closes'], data['volumes']
        )
        
        print(f"\n当前价格: {data['closes'][-1]:.2f}")
        print(f"日内高点: {generator.daily_high:.2f}")
        print(f"日内低点: {generator.daily_low:.2f}")
        print(f"\n{signal}")
        
        if signal.targets:
            print(f"\n🎯 目标设置:")
            for key, value in signal.targets.items():
                if isinstance(value, float):
                    print(f"   {key}: {value:.2f}")
        
        # 计算指标详情
        indicators = generator.calculate_all_indicators(
            data['opens'], data['highs'], data['lows'], 
            data['closes'], data['volumes']
        )
        context = generator.analyze_market_context(indicators)
        
        print(f"\n市场环境:")
        print(f"   趋势: {context.trend.value}")
        print(f"   趋势强度: {context.trend_strength.name}")
        print(f"   价格位置: {context.price_position:.1%}")
        print(f"   波动率: {context.volatility:.2%}")


def test_position_management():
    """测试仓位管理"""
    print("\n" + "="*70)
    print("💰 仓位管理测试")
    print("="*70)
    
    from config.strategy_config import calculate_position_size
    
    test_cases = [
        (1000, 3500, 95),   # 强信号
        (1000, 3500, 75),   # 中等信号
        (1000, 3500, 50),   # 弱信号
    ]
    
    print(f"\n杠杆倍数: {CONFIG.leverage.leverage}x")
    print(f"最大仓位价值: {CONFIG.leverage.max_position_value} USDT")
    
    for margin, price, strength in test_cases:
        size = calculate_position_size(margin, price, strength)
        value = size * price
        print(f"\n可用保证金: {margin} USDT")
        print(f"当前价格: {price} USDT")
        print(f"信号强度: {strength}/100")
        print(f"建议仓位: {size:.4f} ETH")
        print(f"仓位价值: {value:.2f} USDT")


def test_profit_targets():
    """测试收益目标计算"""
    print("\n" + "="*70)
    print("🎯 收益目标测试")
    print("="*70)
    
    from config.strategy_config import get_profit_target
    
    test_cases = [
        (0.10, True, "低位做多"),
        (0.20, True, "低位做多"),
        (0.50, True, "中位做多"),
        (0.80, False, "高位做空"),
        (0.90, False, "高位做空"),
        (0.50, False, "中位做空"),
    ]
    
    current_price = 3500
    
    print(f"\n当前价格: {current_price} USDT")
    print(f"杠杆: {CONFIG.leverage.leverage}x")
    
    for position, is_long, desc in test_cases:
        target = get_profit_target(position, is_long)
        
        price_change = target['optimal'] * 100
        leveraged_return = target['leveraged_return'] * 100
        
        if is_long:
            tp_price = current_price * (1 + target['optimal'])
        else:
            tp_price = current_price * (1 - target['optimal'])
        
        print(f"\n{desc} (位置: {position:.0%}):")
        print(f"   价格变动: {price_change:.2f}%")
        print(f"   目标价格: {tp_price:.2f}")
        print(f"   杠杆收益: {leveraged_return:.1f}%")


def test_backtest_simulation():
    """模拟回测"""
    print("\n" + "="*70)
    print("📊 回测模拟")
    print("="*70)
    
    # 生成震荡市数据（适合反转策略）
    data = generate_mock_data("range_bound", 300)
    
    generator = SignalGenerator()
    
    signals = []
    position = None
    trades = []
    
    # 滑动窗口回测
    window = 100
    for i in range(window, len(data['closes'])):
        # 获取窗口数据
        w_data = {
            'opens': data['opens'][i-window:i],
            'highs': data['highs'][i-window:i],
            'lows': data['lows'][i-window:i],
            'closes': data['closes'][i-window:i],
            'volumes': data['volumes'][i-window:i]
        }
        
        # 设置日内数据
        generator.daily_high = max(w_data['highs'][-20:])
        generator.daily_low = min(w_data['lows'][-20:])
        
        # 生成信号
        signal = generator.generate_signal(
            w_data['opens'], w_data['highs'], w_data['lows'],
            w_data['closes'], w_data['volumes'],
            current_position=position
        )
        
        if signal.type not in [SignalType.HOLD]:
            signals.append({
                'index': i,
                'price': signal.price,
                'type': signal.type,
                'strength': signal.strength
            })
            
            # 模拟交易
            if signal.type in [SignalType.LONG, SignalType.SHORT]:
                position = "long" if signal.type == SignalType.LONG else "short"
                entry_price = signal.price
            elif signal.type in [SignalType.CLOSE_LONG, SignalType.CLOSE_SHORT]:
                if position:
                    pnl = 0
                    if position == "long":
                        pnl = (signal.price - entry_price) / entry_price
                    else:
                        pnl = (entry_price - signal.price) / entry_price
                    
                    leveraged_pnl = pnl * CONFIG.leverage.leverage
                    trades.append(leveraged_pnl)
                    position = None
    
    print(f"\n回测结果:")
    print(f"   总信号数: {len(signals)}")
    print(f"   完成交易: {len(trades)}")
    
    if trades:
        wins = sum(1 for t in trades if t > 0)
        losses = len(trades) - wins
        total_return = sum(trades)
        
        print(f"   盈利: {wins} 笔")
        print(f"   亏损: {losses} 笔")
        print(f"   胜率: {wins/len(trades)*100:.1f}%")
        print(f"   总收益: {total_return*100:+.2f}%")
        print(f"   平均收益: {total_return/len(trades)*100:+.2f}%")
        
        # 显示最近5笔交易
        print(f"\n最近5笔交易收益:")
        for i, pnl in enumerate(trades[-5:], 1):
            emoji = "🟢" if pnl > 0 else "🔴"
            print(f"   {emoji} 交易{i}: {pnl*100:+.2f}%")


def main():
    """运行所有测试"""
    print("\n" + "="*70)
    print("🚀 ETHUSDT 策略测试套件")
    print("="*70)
    
    test_indicators()
    test_signal_generation()
    test_position_management()
    test_profit_targets()
    test_backtest_simulation()
    
    print("\n" + "="*70)
    print("✅ 所有测试完成")
    print("="*70)


if __name__ == "__main__":
    main()
