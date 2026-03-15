#!/usr/bin/env python3
"""
飞书通知适配器
支持多种方式发送飞书通知
"""

import json
import requests
import os
import subprocess
from datetime import datetime


class FeishuAdapter:
    """飞书通知适配器"""
    
    def __init__(self):
        self.webhook_url = os.environ.get('FEISHU_WEBHOOK_URL', '')
        self.use_app_bot = os.environ.get('USE_FEISHU_APP_BOT', 'true').lower() == 'true'
        self.chat_id = os.environ.get('FEISHU_CHAT_ID', '')
        self.session = requests.Session()
        
    def send_by_webhook(self, title: str, content: str, color: str = "blue"):
        """通过飞书 Webhook 发送消息卡片"""
        if not self.webhook_url:
            print(f"⚠️ 未配置飞书 Webhook，跳过通知: {title}")
            return self._console_fallback(title, content)
        
        # 颜色映射
        color_map = {
            "red": "red",
            "green": "green", 
            "blue": "blue",
            "orange": "orange",
            "urgent": "red"
        }
        
        card = {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": title},
                    "template": color_map.get(color, "blue")
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": content}
                    },
                    {
                        "tag": "note",
                        "elements": [
                            {"tag": "plain_text", "content": f"⏰ {datetime.now().strftime('%m-%d %H:%M')}"}
                        ]
                    }
                ]
            }
        }
        
        try:
            resp = self.session.post(self.webhook_url, json=card, timeout=10)
            if resp.status_code == 200:
                print(f"✅ 飞书通知已发送: {title}")
                return True
            else:
                print(f"❌ Webhook 发送失败: {resp.status_code}")
                return self._console_fallback(title, content)
        except Exception as e:
            print(f"❌ Webhook 异常: {e}")
            return self._console_fallback(title, content)
    
    def send_by_app_bot(self, title: str, content: str, urgent: bool = False):
        """通过飞书应用机器人发送消息（使用 openclaw feishu_im_user_message 工具）"""
        try:
            # 构建消息内容
            full_content = f"**{title}**\n\n{content}\n\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            # 使用 openclaw 命令发送消息
            # 需要先获取 chat_id，这里使用消息工具发送
            cmd = [
                "openclaw", "tools", "call", "feishu_im_user_message",
                "--params", json.dumps({
                    "action": "send",
                    "receive_id_type": "chat_id",
                    "receive_id": self.chat_id or "_default_",
                    "msg_type": "text",
                    "content": json.dumps({"text": full_content})
                })
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                print(f"✅ 应用机器人通知已发送: {title}")
                return True
            else:
                # 降级到 Webhook
                print(f"⚠️ 应用机器人发送失败，尝试 Webhook: {result.stderr[:100]}")
                return self.send_by_webhook(title, content, "red" if urgent else "blue")
                
        except Exception as e:
            print(f"⚠️ 应用机器人异常: {e}")
            return self.send_by_webhook(title, content, "red" if urgent else "blue")
    
    def send_message(self, title: str, content: str, urgent: bool = False):
        """发送消息（自动选择方式）"""
        # 优先使用 Webhook（最简单直接）
        if self.webhook_url:
            color = "red" if urgent else "blue"
            return self.send_by_webhook(title, content, color)
        
        # 其次尝试应用机器人
        if self.use_app_bot:
            return self.send_by_app_bot(title, content, urgent)
        
        # 降级到控制台
        return self._console_fallback(title, content)
    
    def _console_fallback(self, title: str, content: str):
        """控制台降级输出"""
        print(f"\n{'='*60}")
        print(f"📢 {title}")
        print(f"{'='*60}")
        print(content)
        print(f"{'='*60}\n")
        return True


def main():
    """测试发送"""
    adapter = FeishuAdapter()
    
    # 测试消息
    adapter.send_message(
        title="🧪 股票监控系统测试",
        content="**测试通知**\n\n您的持仓监控已就绪！\n\n• 买入提醒: 已配置\n• 减仓提醒: 已配置\n• 每日报告: 已配置",
        urgent=False
    )


if __name__ == "__main__":
    main()
