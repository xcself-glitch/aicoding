#!/usr/bin/env python3
"""
价格预警测试脚本
模拟达到目标价格，测试通知功能
"""

import sys
from pathlib import Path
from datetime import datetime

# 添加路径
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "config"))

from price_monitor_feishu import PriceMonitor, FeishuNotifier
from my_portfolio import PORTFOLIO


def test_buy_alert():
    """测试买入提醒"""
    print("\n" + "=" * 70)
    print("🧪 测试1: 买入提醒触发")
    print("=" * 70)
    
    monitor = PriceMonitor()
    
    # 模拟兆易创新跌到买入目标价以下
    mock_quote = {
        'name': '兆易创新',
        'price': 263.00,  # 低于目标买入价 265
        'change_pct': -5.5,
        'high': 278.33,
        'low': 262.00,
        'open': 275.00,
        'prev_close': 278.33,
    }
    
    # 找到兆易创新的配置
    zhaoyi = None
    for stock in PORTFOLIO:
        if stock['code'] == '603986':
            zhaoyi = stock
            break
    
    if zhaoyi:
        print(f"\n📊 模拟数据:")
        print(f"   股票: {zhaoyi['name']} ({zhaoyi['code']})")
        print(f"   当前价: ¥{mock_quote['price']:.2f}")
        print(f"   目标买入价: ¥{zhaoyi['alerts']['target_buy']:.2f}")
        print(f"   触发条件: ¥{mock_quote['price']:.2f} ≤ ¥{zhaoyi['alerts']['target_buy']:.2f} ✅")
        
        alerts = monitor.check_price_alerts(zhaoyi, mock_quote)
        
        if alerts:
            print(f"\n✅ 成功触发 {len(alerts)} 条预警:")
            for alert in alerts:
                print(f"   📢 {alert['title']}")
                print(f"      紧急程度: {'🚨 紧急' if alert['urgent'] else '🔔 普通'}")
        else:
            print("\n❌ 未触发预警（可能当天已发送过）")
    else:
        print("❌ 未找到兆易创新配置")


def test_reduce_alert():
    """测试减仓提醒"""
    print("\n" + "=" * 70)
    print("🧪 测试2: 减仓提醒触发")
    print("=" * 70)
    
    monitor = PriceMonitor()
    
    # 模拟卫星ETF涨到减仓目标价以上
    mock_quote = {
        'name': '卫星ETF',
        'price': 1.88,  # 高于目标减仓价 1.85
        'change_pct': 8.5,
        'high': 1.90,
        'low': 1.75,
        'open': 1.76,
        'prev_close': 1.73,
    }
    
    # 找到卫星ETF的配置
    etf = None
    for stock in PORTFOLIO:
        if stock['code'] == '563230':
            etf = stock
            break
    
    if etf:
        print(f"\n📊 模拟数据:")
        print(f"   股票: {etf['name']} ({etf['code']})")
        print(f"   当前价: ¥{mock_quote['price']:.2f}")
        print(f"   目标减仓价: ¥{etf['alerts']['target_reduce']:.2f}")
        print(f"   触发条件: ¥{mock_quote['price']:.2f} ≥ ¥{etf['alerts']['target_reduce']:.2f} ✅")
        
        alerts = monitor.check_price_alerts(etf, mock_quote)
        
        if alerts:
            print(f"\n✅ 成功触发 {len(alerts)} 条预警:")
            for alert in alerts:
                print(f"   📢 {alert['title']}")
                print(f"      紧急程度: {'🚨 紧急' if alert['urgent'] else '🔔 普通'}")
        else:
            print("\n❌ 未触发预警（可能当天已发送过）")


def test_stop_loss_alert():
    """测试止损提醒"""
    print("\n" + "=" * 70)
    print("🧪 测试3: 止损提醒触发")
    print("=" * 70)
    
    monitor = PriceMonitor()
    
    # 模拟兆易创新跌到止损价
    mock_quote = {
        'name': '兆易创新',
        'price': 243.00,  # 低于止损价 245
        'change_pct': -12.0,
        'high': 278.33,
        'low': 240.00,
        'open': 275.00,
        'prev_close': 278.33,
    }
    
    zhaoyi = None
    for stock in PORTFOLIO:
        if stock['code'] == '603986':
            zhaoyi = stock
            break
    
    if zhaoyi:
        print(f"\n📊 模拟数据:")
        print(f"   股票: {zhaoyi['name']} ({zhaoyi['code']})")
        print(f"   当前价: ¥{mock_quote['price']:.2f}")
        print(f"   止损价: ¥{zhaoyi['alerts']['stop_loss']:.2f}")
        print(f"   触发条件: ¥{mock_quote['price']:.2f} ≤ ¥{zhaoyi['alerts']['stop_loss']:.2f} ✅")
        
        alerts = monitor.check_price_alerts(zhaoyi, mock_quote)
        
        if alerts:
            print(f"\n✅ 成功触发 {len(alerts)} 条预警:")
            for alert in alerts:
                print(f"   📢 {alert['title']}")
                print(f"      紧急程度: {'🚨 紧急' if alert['urgent'] else '🔔 普通'}")


def test_big_change_alert():
    """测试日内异动提醒"""
    print("\n" + "=" * 70)
    print("🧪 测试4: 日内异动提醒触发")
    print("=" * 70)
    
    monitor = PriceMonitor()
    
    # 模拟汉得信息大涨
    mock_quote = {
        'name': '汉得信息',
        'price': 27.50,  # 大涨超过5%
        'change_pct': 17.5,  # 涨幅17.5%
        'high': 28.00,
        'low': 23.00,
        'open': 23.41,
        'prev_close': 23.41,
    }
    
    hande = None
    for stock in PORTFOLIO:
        if stock['code'] == '300170':
            hande = stock
            break
    
    if hande:
        print(f"\n📊 模拟数据:")
        print(f"   股票: {hande['name']} ({hande['code']})")
        print(f"   当前价: ¥{mock_quote['price']:.2f}")
        print(f"   今日涨跌: {mock_quote['change_pct']:+.1f}%")
        print(f"   预警阈值: ±{hande['alerts'].get('change_pct_above', 5)}%")
        print(f"   触发条件: |{mock_quote['change_pct']:.1f}%| ≥ {hande['alerts'].get('change_pct_above', 5)}% ✅")
        
        alerts = monitor.check_price_alerts(hande, mock_quote)
        
        if alerts:
            print(f"\n✅ 成功触发 {len(alerts)} 条预警:")
            for alert in alerts:
                print(f"   📢 {alert['title']}")
                print(f"      紧急程度: {'🚨 紧急' if alert['urgent'] else '🔔 普通'}")


def test_notification_send():
    """测试通知发送"""
    print("\n" + "=" * 70)
    print("🧪 测试5: 飞书通知发送")
    print("=" * 70)
    
    notifier = FeishuNotifier()
    
    # 模拟买入提醒通知
    title = "🟢 兆易创新 触及买入目标价"
    content = """**兆易创新 (603986)**

当前价格: ¥263.00
目标买入价: ¥265.00
建议: 可考虑逢低加仓

📊 技术指标:
• RSI: 28.5 (超卖)
• 支撑位: ¥260
• 压力位: ¥280

时间: 2026-03-14 10:30:15"""
    
    print(f"\n📤 正在发送测试通知...")
    print(f"标题: {title}")
    
    result = notifier.send_message(title, content, urgent=False)
    
    if result:
        print("\n✅ 通知发送成功！")
    else:
        print("\n⚠️ 通知发送失败（未配置飞书 Webhook）")
        print("   控制台输出通知内容:")
        print(f"\n{'='*60}")
        print(f"📢 {title}")
        print(f"{'='*60}")
        print(content)
        print(f"{'='*60}")


def main():
    """运行所有测试"""
    print("\n" + "=" * 70)
    print("🧪 价格预警系统测试")
    print("=" * 70)
    print("\n本测试将模拟达到目标价格的情况，验证通知功能")
    
    # 运行测试
    test_buy_alert()
    test_reduce_alert()
    test_stop_loss_alert()
    test_big_change_alert()
    test_notification_send()
    
    print("\n" + "=" * 70)
    print("✅ 所有测试完成！")
    print("=" * 70)
    print("\n📋 测试结果说明:")
    print("   • ✅ 表示预警逻辑正确触发")
    print("   • 飞书通知需要配置 Webhook URL 才能发送")
    print("   • 配置方法: ./scripts/setup_feishu.sh")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
