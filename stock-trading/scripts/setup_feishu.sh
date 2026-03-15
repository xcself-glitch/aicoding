#!/bin/bash
# 飞书通知配置脚本

echo "========================================"
echo "📱 飞书通知配置"
echo "========================================"
echo ""
echo "要启用飞书通知，需要配置飞书 Webhook URL:"
echo ""
echo "1. 在飞书群中创建自定义机器人"
echo "2. 获取 Webhook URL"
echo "3. 设置环境变量或修改配置文件"
echo ""

CONFIG_FILE="$HOME/.stock_monitor_config"

read -p "请输入飞书 Webhook URL (留空则跳过): " webhook_url

if [ -n "$webhook_url" ]; then
    # 保存配置
    echo "FEISHU_WEBHOOK_URL=$webhook_url" > "$CONFIG_FILE"
    echo "export FEISHU_WEBHOOK_URL=$webhook_url" >> ~/.bashrc
    export FEISHU_WEBHOOK_URL=$webhook_url
    
    echo ""
    echo "✅ 飞书配置已保存!"
    echo ""
    
    # 测试发送
    echo "🧪 发送测试消息..."
    python3 << EOF
import sys
import os
sys.path.insert(0, 'skills/stock-monitor-pro/scripts')
from feishu_adapter import FeishuAdapter

adapter = FeishuAdapter()
result = adapter.send_by_webhook(
    title="🎉 股票监控系统已配置",
    content="**测试通知**\n\n您的持仓监控已成功配置飞书通知！\n\n功能包括:\n• 价格预警通知\n• 每日策略更新\n• 买卖信号提醒",
    color="green"
)
if result:
    print("✅ 测试消息发送成功!")
else:
    print("❌ 测试消息发送失败，请检查 Webhook URL")
EOF
else
    echo "⚠️ 未配置 Webhook，通知将只在控制台显示"
fi

echo ""
echo "========================================"
