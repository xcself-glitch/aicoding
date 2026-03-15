#!/usr/bin/env python3
"""
测试飞书交易信号通知
发送一条模拟的做多信号
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.eth_notify_feishu import send_trading_signal, send_market_summary, test_notification


def test_long_signal():
    """测试做多信号"""
    print("测试做多信号通知...")
    send_trading_signal(
        direction="做多",
        price=2075.30,
        strength=85,
        reason="RSI超卖(28.5) | KDJ低位金叉 | MACD金叉 | 触碰布林带下轨",
        daily_high=2116.16,
        daily_low=2060.00,
        change_pct=-1.68,
        funding_rate=-0.000012,
        tp=2127.18,
        sl=2059.05,
        expected_return=0.15
    )


def test_short_signal():
    """测试做空信号"""
    print("测试做空信号通知...")
    send_trading_signal(
        direction="做空",
        price=2100.00,
        strength=75,
        reason="RSI超买(72.5) | KDJ高位死叉 | MACD顶背离 | 触碰布林带上轨",
        daily_high=2120.00,
        daily_low=2050.00,
        change_pct=+2.50,
        funding_rate=0.000025,
        tp=2058.00,
        sl=2116.80,
        expected_return=0.12
    )


def test_market_summary():
    """测试市场汇总"""
    print("测试市场汇总通知...")
    send_market_summary(
        price=2075.30,
        change_pct=-1.68,
        daily_high=2116.16,
        daily_low=2060.00,
        funding_rate=-0.000012,
        signal_type="持仓观望",
        signal_reason="RSI中性区域，等待突破确认"
    )


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="测试ETH飞书通知")
    parser.add_argument("--type", choices=["long", "short", "summary", "all"], default="all",
                        help="测试类型: long(做多), short(做空), summary(汇总), all(全部)")
    
    args = parser.parse_args()
    
    if args.type == "long" or args.type == "all":
        test_long_signal()
    
    if args.type == "short" or args.type == "all":
        test_short_signal()
    
    if args.type == "summary" or args.type == "all":
        test_market_summary()
    
    print("\n✅ 测试完成")
