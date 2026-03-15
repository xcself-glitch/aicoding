#!/usr/bin/env python3
"""
兆易创新实时监控 - 带飞书通知
参考ETH监控的实现方式
有预警时才发送飞书消息
"""

import sys
import os
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

# 导入原有监控逻辑
from scripts.monitor_zhaoyi import (
    STOCK_CONFIG, ALERTS,
    fetch_tencent_quote, check_alerts
)

# 导入飞书通知
from scripts.notify_feishu import send_stock_alert


def format_alert_message(data, config, alerts):
    """格式化预警消息用于飞书"""
    price = data['price']
    cost = config['cost']
    shares = config['shares']
    cost_change_pct = (price - cost) / cost * 100
    profit = (price - cost) * shares
    
    # 盈亏图标
    profit_emoji = "🟢" if profit >= 0 else "🔴"
    
    # 构建预警详情
    alert_details = []
    for alert in alerts:
        icon = "🚨" if alert['level'] == 'warning' else "⚠️"
        alert_details.append(
            f"**{icon} {alert['type']}**\n"
            f"• {alert['message']}\n"
            f"• 💡 建议: {alert['action']}"
        )
    
    content = f"""**{config['name']} ({config['code']}) 持仓监控**

💰 **持仓信息**:
• 持仓数量: {shares}股
• 成本价格: ¥{cost:.2f}
• 当前价格: ¥{price:.2f} ({data['change_pct']:+.2f}%)
• 持仓盈亏: {profit_emoji}¥{profit:+,.0f} ({cost_change_pct:+.2f}%)

📊 **今日行情**:
• 开盘价: ¥{data['open']:.2f}
• 最高价: ¥{data['high']:.2f}
• 最低价: ¥{data['low']:.2f}
• 量比: {data['volume_ratio']:.2f}

🚨 **触发预警 ({len(alerts)}条)**:

{chr(10).join(alert_details)}

---
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
    
    return content


def main():
    """主函数"""
    print("="*60)
    print(f"🚀 兆易创新实时监控 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
    print("="*60)
    
    # 获取数据
    print("\n📊 获取腾讯财经行情...")
    data = fetch_tencent_quote(STOCK_CONFIG['code'])
    
    if not data:
        print("❌ 获取行情失败")
        return "数据获取失败"
    
    # 检查预警
    alerts = check_alerts(data, STOCK_CONFIG, ALERTS)
    
    # 基本信息输出
    price = data['price']
    cost = STOCK_CONFIG['cost']
    cost_change_pct = (price - cost) / cost * 100
    profit = (price - cost) * STOCK_CONFIG['shares']
    
    print(f"\n💰 {STOCK_CONFIG['name']} ({STOCK_CONFIG['code']})")
    print(f"   现价: ¥{price:.2f} ({data['change_pct']:+.2f}%)")
    print(f"   盈亏: {'🟢' if profit >= 0 else '🔴'}¥{profit:+,.0f} ({cost_change_pct:+.2f}%)")
    print(f"   区间: ¥{data['low']:.2f} - ¥{data['high']:.2f}")
    
    # 如果有预警，发送飞书通知
    if alerts:
        print(f"\n{'='*60}")
        print(f"📢 🚨 触发 {len(alerts)} 条预警 - 正在发送飞书通知...")
        print(f"{'='*60}")
        
        for alert in alerts:
            icon = "🚨" if alert['level'] == 'warning' else "⚠️"
            print(f"   {icon} [{alert['type']}] {alert['message']}")
            print(f"      💡 {alert['action']}")
        
        # 发送飞书通知
        content = format_alert_message(data, STOCK_CONFIG, alerts)
        title = f"🚨 {STOCK_CONFIG['name']} 预警 | 现价¥{price:.2f}"
        
        send_stock_alert(title, content)
        
        return f"🚨 预警{len(alerts)}条 | {price:.2f}"
    else:
        # 无预警，静默
        print(f"\n✅ 当前无预警，持仓正常")
        return f"正常 | ¥{price:.2f}"


if __name__ == "__main__":
    result = main()
    print(f"\n✅ 监控结果: {result}")
