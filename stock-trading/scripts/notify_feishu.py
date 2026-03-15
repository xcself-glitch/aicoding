#!/usr/bin/env python3
"""
应用机器人通知脚本
使用飞书应用机器人发送消息
"""

import json
import subprocess
import sys
from datetime import datetime

# 默认群聊ID（股票监控群）
DEFAULT_CHAT_ID = "oc_aad9321803dede2d45793eeedd7abec5"


def send_stock_alert(title: str, content: str, chat_id: str = None):
    """
    发送股票预警通知到飞书
    
    Args:
        title: 通知标题
        content: 通知内容（支持 Markdown）
        chat_id: 群聊ID（可选，默认发送到配置群）
    """
    
    # 使用提供的chat_id或默认群
    target_chat_id = chat_id or DEFAULT_CHAT_ID
    
    # 格式化消息内容
    full_message = f"📊 **{title}**\n\n{content}\n\n---\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    try:
        # 使用 openclaw message send 命令
        cmd = [
            "openclaw", "message", "send",
            "--target", target_chat_id,
            "--message", full_message,
            "--channel", "feishu"
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        # 检查输出中是否包含成功标识
        if "Sent via Feishu" in result.stderr or result.returncode == 0:
            print(f"✅ 飞书通知已发送: {title}")
            return True
        else:
            print(f"⚠️ 发送返回: {result.stderr[:200]}")
            # 降级到控制台
            _console_output(title, content)
            return False
            
    except Exception as e:
        print(f"❌ 发送异常: {e}")
        _console_output(title, content)
        return False


def _console_output(title: str, content: str):
    """控制台输出（降级方案）"""
    print(f"\n{'='*60}")
    print(f"📢 {title}")
    print(f"{'='*60}")
    print(content)
    print(f"{'='*60}\n")


def test_notification():
    """测试通知"""
    send_stock_alert(
        title="🎉 股票监控系统已激活",
        content="""**配置成功！**

您的持仓监控已连接到本群。

📊 监控范围：11只持仓股
⏰ 检查频率：交易日每30分钟
📱 通知方式：本群实时推送

监控列表：
• 兆易创新、汉得信息（逢低加仓）
• 卫星ETF（1.85减仓）
• 其他标的持有观望

系统将自动推送：
✅ 价格触及目标价位
✅ 日内大涨/大跌异动
✅ 每日收盘策略报告"""
    )


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_notification()
    else:
        print("用法: python3 notify_feishu.py --test")
