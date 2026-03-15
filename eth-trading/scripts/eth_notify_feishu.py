#!/usr/bin/env python3
"""
ETHUSDT 飞书通知模块
参考 stock-monitor-pro 的实现方式
"""

import json
import subprocess
import sys
from datetime import datetime
from typing import Optional

# 默认群聊ID（可从环境变量覆盖）
DEFAULT_CHAT_ID = "oc_aad9321803dede2d45793eeedd7abec5"


def send_crypto_alert(
    title: str, 
    content: str, 
    chat_id: str = None,
    urgent: bool = False
):
    """
    发送加密货币预警通知到飞书
    
    Args:
        title: 通知标题
        content: 通知内容（支持 Markdown）
        chat_id: 群聊ID（可选，默认发送到配置群）
        urgent: 是否紧急通知
    """
    
    # 使用提供的chat_id或默认群
    target_chat_id = chat_id or DEFAULT_CHAT_ID
    
    # 添加紧急标识
    prefix = "🚨 " if urgent else ""
    
    # 格式化消息内容
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    full_message = f"{prefix}📊 **{title}**\n\n{content}\n\n---\n⏰ {timestamp}"
    
    try:
        # 使用 openclaw message send 命令（与股票监控一致）
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
            _console_output(title, content, urgent)
            return False
            
    except Exception as e:
        print(f"❌ 发送异常: {e}")
        _console_output(title, content, urgent)
        return False


def send_trading_signal(
    direction: str,
    price: float,
    strength: float,
    reason: str,
    daily_high: float,
    daily_low: float,
    change_pct: float,
    funding_rate: float,
    tp: float,
    sl: float,
    expected_return: float,
    chat_id: str = None
):
    """
    发送交易信号通知
    
    Args:
        direction: "做多" 或 "做空"
        price: 当前价格
        strength: 信号强度
        reason: 信号理由
        daily_high: 24h最高
        daily_low: 24h最低
        change_pct: 24h涨跌%
        funding_rate: 资金费率
        tp: 止盈价格
        sl: 止损价格
        expected_return: 预期收益率
        chat_id: 群聊ID
    """
    
    # 方向标识
    emoji = "🟢" if direction == "做多" else "🔴"
    
    # 构建消息内容
    content = f"""**{emoji} {direction}交易信号**

💰 **当前价格**: {price:.2f} USDT
📊 **信号强度**: {strength:.0f}/100
📍 **价格位置**: {((price - daily_low) / (daily_high - daily_low) * 100):.1f}% (日内区间)

📈 **市场环境**:
• 24h涨跌: {change_pct:+.2f}%
• 24h最高: {daily_high:.2f}
• 24h最低: {daily_low:.2f}
• 资金费率: {funding_rate:.6f}
• 数据源: Gate.io 永续合约

📋 **信号理由**:
{reason}

🎯 **交易目标**:
• 止盈: {tp:.2f} USDT ({((tp/price - 1) * 100):+.1f}%)
• 止损: {sl:.2f} USDT ({((sl/price - 1) * 100):+.1f}%)
• 预期收益: {expected_return * 100:.1f}%

⚠️ **风险提示**: 10倍杠杆风险极高！"""
    
    title = f"ETHUSDT {direction}信号 | 强度{strength:.0f}"
    
    return send_crypto_alert(title, content, chat_id, urgent=True)


def send_market_summary(
    price: float,
    change_pct: float,
    daily_high: float,
    daily_low: float,
    funding_rate: float,
    signal_type: str,
    signal_reason: str,
    chat_id: str = None
):
    """
    发送市场汇总通知（无交易信号时）
    
    Args:
        price: 当前价格
        change_pct: 24h涨跌%
        daily_high: 24h最高
        daily_low: 24h最低
        funding_rate: 资金费率
        signal_type: 信号类型
        signal_reason: 信号理由
        chat_id: 群聊ID
    """
    
    content = f"""**ETH/USDT 市场监控**

💰 **当前价格**: {price:.2f} USDT
📊 **24h涨跌**: {change_pct:+.2f}%
📈 **24h区间**: {daily_low:.2f} - {daily_high:.2f}
💧 **资金费率**: {funding_rate:.6f}

📍 **信号状态**: {signal_type}
📝 **分析**: {signal_reason}

⏳ 暂无可执行交易信号，继续监控中..."""
    
    title = f"ETHUSDT 市场状态 | {price:.2f}"
    
    return send_crypto_alert(title, content, chat_id, urgent=False)


def _console_output(title: str, content: str, urgent: bool = False):
    """控制台输出（降级方案）"""
    prefix = "🚨 " if urgent else ""
    print(f"\n{'='*60}")
    print(f"{prefix}📢 {title}")
    print(f"{'='*60}")
    print(content)
    print(f"{'='*60}\n")


def test_notification():
    """测试通知"""
    # 测试交易信号
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


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_notification()
    else:
        print("用法: python3 eth_notify_feishu.py --test")
