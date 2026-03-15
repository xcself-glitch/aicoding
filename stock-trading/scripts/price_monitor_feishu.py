#!/usr/bin/env python3
"""
价格监控与飞书通知系统
- 高频监控：普通股票5分钟，重点股票1分钟
- 智能通知：只有触发交易信号或异常波动时才通知
- 实时监控持仓股价格，达到目标买卖价格时发送飞书通知
"""

import requests
import json
import sys
import os
from datetime import datetime
from pathlib import Path

# 添加配置目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "config"))

# 导入飞书通知
sys.path.insert(0, str(Path(__file__).parent))
from notify_feishu import send_stock_alert


class FeishuNotifier:
    """飞书通知器 - 使用应用机器人"""
    
    def __init__(self):
        self.triggered_today = set()  # 今日已触发的预警（防重复）
    
    def send_message(self, title: str, content: str, urgent: bool = False):
        """发送飞书通知"""
        # 添加紧急标记
        if urgent:
            title = f"🚨 {title}"
        
        return send_stock_alert(title, content)
    
    def is_alert_triggered_today(self, alert_key: str) -> bool:
        """检查今日是否已触发过此预警"""
        today = datetime.now().strftime('%Y%m%d')
        full_key = f"{today}_{alert_key}"
        return full_key in self.triggered_today
    
    def mark_alert_triggered(self, alert_key: str):
        """标记预警已触发"""
        today = datetime.now().strftime('%Y%m%d')
        full_key = f"{today}_{alert_key}"
        self.triggered_today.add(full_key)


class PriceMonitor:
    """价格监控器"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        self.notifier = FeishuNotifier()
        
    def get_stock_quote(self, code, market):
        """获取个股行情"""
        prefix = "sh" if market == 'sh' else "sz"
        url = f"http://qt.gtimg.cn/q={prefix}{code}"
        
        try:
            resp = self.session.get(url, timeout=5)
            resp.encoding = 'gb2312'
            
            for line in resp.text.strip().split(';'):
                if '~' in line:
                    parts = line.split('~')
                    if len(parts) > 45:
                        return {
                            'name': parts[1],
                            'price': float(parts[3]),
                            'change_pct': float(parts[32]),
                            'high': float(parts[33]),
                            'low': float(parts[34]),
                            'open': float(parts[5]),
                            'prev_close': float(parts[4]),
                        }
        except Exception as e:
            print(f"❌ 获取{code}行情失败: {e}")
        return None
    
    def check_price_alerts(self, stock, quote) -> list:
        """
        检查价格预警
        返回需要发送的预警列表（已过滤重复）
        """
        if not quote:
            return []
        
        alerts = []
        code = stock['code']
        name = stock['name']
        price = quote['price']
        alerts_config = stock.get('alerts', {})
        
        # 1. 检查买入目标价
        target_buy = alerts_config.get('target_buy')
        if target_buy and price <= target_buy:
            alert_key = f"{code}_buy"
            if not self.notifier.is_alert_triggered_today(alert_key):
                alerts.append({
                    'type': 'buy',
                    'urgent': True,
                    'title': f'🟢 {name} 触及买入目标价',
                    'content': (
                        f"**{name} ({code})**\n\n"
                        f"💰 当前价格: ¥{price:.2f}\n"
                        f"🎯 目标买入价: ¥{target_buy:.2f}\n"
                        f"📊 偏离目标: {(price/target_buy-1)*100:.1f}%\n\n"
                        f"💡 **建议**: 可考虑逢低加仓\n"
                        f"⏰ {datetime.now().strftime('%H:%M:%S')}"
                    )
                })
                self.notifier.mark_alert_triggered(alert_key)
        
        # 2. 检查减仓目标价
        target_reduce = alerts_config.get('target_reduce')
        if target_reduce and price >= target_reduce:
            alert_key = f"{code}_reduce"
            if not self.notifier.is_alert_triggered_today(alert_key):
                alerts.append({
                    'type': 'reduce',
                    'urgent': True,
                    'title': f'🔴 {name} 触及减仓目标价',
                    'content': (
                        f"**{name} ({code})**\n\n"
                        f"💰 当前价格: ¥{price:.2f}\n"
                        f"🎯 目标减仓价: ¥{target_reduce:.2f}\n"
                        f"📊 偏离目标: +{(price/target_reduce-1)*100:.1f}%\n\n"
                        f"💡 **建议**: 可考虑减仓锁定利润\n"
                        f"⏰ {datetime.now().strftime('%H:%M:%S')}"
                    )
                })
                self.notifier.mark_alert_triggered(alert_key)
        
        # 3. 检查止损价
        stop_loss = alerts_config.get('stop_loss')
        if stop_loss and price <= stop_loss:
            alert_key = f"{code}_stop"
            if not self.notifier.is_alert_triggered_today(alert_key):
                alerts.append({
                    'type': 'stop',
                    'urgent': True,
                    'title': f'🚨 {name} 触及止损价',
                    'content': (
                        f"**{name} ({code})**\n\n"
                        f"💰 当前价格: ¥{price:.2f}\n"
                        f"🛑 止损价: ¥{stop_loss:.2f}\n"
                        f"📊 跌破止损: {(price/stop_loss-1)*100:.1f}%\n\n"
                        f"⚠️ **建议**: 严格执行止损纪律，避免深套\n"
                        f"⏰ {datetime.now().strftime('%H:%M:%S')}"
                    )
                })
                self.notifier.mark_alert_triggered(alert_key)
        
        # 4. 检查日内异动（大涨/大跌）
        change_pct = quote['change_pct']
        change_threshold = alerts_config.get('change_pct_above', 5)  # 默认5%
        
        if abs(change_pct) >= change_threshold:
            alert_key = f"{code}_change_{'up' if change_pct > 0 else 'down'}"
            if not self.notifier.is_alert_triggered_today(alert_key):
                direction = "大涨" if change_pct > 0 else "大跌"
                urgent = abs(change_pct) > 7  # 涨跌幅超7%算紧急
                
                # 根据涨跌幅选择表情
                if change_pct > 7:
                    emoji = "🚀"
                elif change_pct > 5:
                    emoji = "📈"
                elif change_pct < -7:
                    emoji = "💥"
                else:
                    emoji = "📉"
                
                alerts.append({
                    'type': 'change',
                    'urgent': urgent,
                    'title': f'{emoji} {name} 日内{direction}{abs(change_pct):.1f}%',
                    'content': (
                        f"**{name} ({code})**\n\n"
                        f"💰 当前价格: ¥{price:.2f}\n"
                        f"📊 今日涨跌: {change_pct:+.2f}%\n"
                        f"⬆️ 今日最高: ¥{quote['high']:.2f}\n"
                        f"⬇️ 今日最低: ¥{quote['low']:.2f}\n"
                        f"💹 成交额: 活跃\n\n"
                        f"{'⚠️ 异动明显，请关注！' if urgent else '💡 出现较大波动'}\n"
                        f"⏰ {datetime.now().strftime('%H:%M:%S')}"
                    )
                })
                self.notifier.mark_alert_triggered(alert_key)
        
        return alerts
    
    def monitor_stocks(self, stocks: list, verbose: bool = False) -> list:
        """
        监控指定股票列表
        
        Args:
            stocks: 股票列表
            verbose: 是否显示详细输出（普通监控为False，手动运行为True）
        
        Returns:
            触发的预警列表
        """
        if verbose:
            print(f"\n📊 价格监控 - {datetime.now().strftime('%H:%M:%S')}")
            print("-" * 50)
        
        all_alerts = []
        
        for stock in stocks:
            quote = self.get_stock_quote(stock['code'], stock['market'])
            if quote:
                alerts = self.check_price_alerts(stock, quote)
                all_alerts.extend(alerts)
                
                if verbose:
                    status = "🚨" if alerts else "✓"
                    print(f"{status} {stock['name']}: ¥{quote['price']:.2f}")
        
        # 只发送有预警的通知
        for alert in all_alerts:
            self.notifier.send_message(
                title=alert['title'],
                content=alert['content'],
                urgent=alert['urgent']
            )
        
        if verbose:
            if all_alerts:
                print(f"\n🚨 触发 {len(all_alerts)} 条预警，已发送通知")
            else:
                print("\n✅ 无交易信号，继续监控...")
        
        return all_alerts
    
    def send_daily_strategy_update(self, portfolio):
        """发送每日策略更新（收盘报告）"""
        print("\n📊 生成收盘日报...")
        
        # 获取大盘数据
        market_summary = self._get_market_summary()
        
        # 分析每只持仓
        holdings = []
        buy_signals = []
        sell_signals = []
        stop_signals = []
        
        total_cost = 0
        total_value = 0
        
        for stock in portfolio:
            quote = self.get_stock_quote(stock['code'], stock['market'])
            if quote:
                price = quote['price']
                cost = stock['cost']
                shares = stock['shares']
                pnl_pct = (price - cost) / cost * 100
                
                cost_value = cost * shares
                market_value = price * shares
                total_cost += cost_value
                total_value += market_value
                
                holding = {
                    'name': stock['name'],
                    'code': stock['code'],
                    'price': price,
                    'cost': cost,
                    'pnl_pct': pnl_pct,
                    'market_value': market_value,
                    'daily_change': quote['change_pct'],
                    'priority': stock.get('priority', 'normal')
                }
                holdings.append(holding)
                
                # 检查信号
                alerts = stock.get('alerts', {})
                if alerts.get('target_buy') and price <= alerts['target_buy']:
                    buy_signals.append(holding)
                if alerts.get('target_reduce') and price >= alerts['target_reduce']:
                    sell_signals.append(holding)
                if alerts.get('stop_loss') and price <= alerts['stop_loss']:
                    stop_signals.append(holding)
        
        # 计算整体盈亏
        total_pnl = (total_value - total_cost) / total_cost * 100 if total_cost > 0 else 0
        
        # 构建报告内容
        content_lines = [
            f"**📅 日期**: {datetime.now().strftime('%Y-%m-%d')}",
            f"**🏛️ 大盘**: {market_summary}",
            "",
            f"**💰 整体盈亏**: {total_pnl:+.2f}%",
            f"持仓成本: ¥{total_cost:,.2f}",
            f"当前市值: ¥{total_value:,.2f}",
            "",
            "**📈 重点持仓** (1分钟监控):",
        ]
        
        # 按优先级和盈亏排序
        holdings.sort(key=lambda x: (0 if x['priority'] == 'high' else 1, -x['pnl_pct']))
        
        # 显示重点股票
        for h in holdings:
            if h['priority'] == 'high':
                emoji = "🟢" if h['pnl_pct'] > 0 else "🔴"
                content_lines.append(
                    f"{emoji} **{h['name']}**: ¥{h['price']:.2f} ({h['pnl_pct']:+.1f}%)"
                )
        
        # 显示当日信号
        if buy_signals or sell_signals or stop_signals:
            content_lines.append("\n**⚡ 今日交易信号**:")
            for s in buy_signals:
                content_lines.append(f"🟢 买入: {s['name']} ¥{s['price']:.2f}")
            for s in sell_signals:
                content_lines.append(f"🔴 减仓: {s['name']} ¥{s['price']:.2f}")
            for s in stop_signals:
                content_lines.append(f"🚨 止损: {s['name']} ¥{s['price']:.2f}")
        
        content = "\n".join(content_lines)
        
        # 发送收盘报告
        self.notifier.send_message(
            title="📊 收盘日报",
            content=content,
            urgent=False
        )
        
        return buy_signals, sell_signals
    
    def _get_market_summary(self):
        """获取大盘摘要"""
        try:
            indices = ["sh000001", "sz399001", "sz399006"]
            url = f"http://qt.gtimg.cn/q={','.join(indices)}"
            resp = self.session.get(url, timeout=5)
            resp.encoding = 'gb2312'
            
            changes = []
            for line in resp.text.strip().split(';'):
                if '~' in line:
                    parts = line.split('~')
                    if len(parts) > 45:
                        name = parts[1][:2]  # 上证/深证/创业
                        change = float(parts[32])
                        changes.append(f"{name}{change:+.1f}%")
            
            return " | ".join(changes)
        except:
            return "获取失败"


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='价格监控与飞书通知')
    parser.add_argument('--check', action='store_true', help='监控普通股票（5分钟频率）')
    parser.add_argument('--check-key', action='store_true', help='监控重点股票（1分钟频率）')
    parser.add_argument('--daily', action='store_true', help='开盘策略更新')
    parser.add_argument('--report', action='store_true', help='收盘日报')
    args = parser.parse_args()
    
    # 加载持仓配置
    try:
        from my_portfolio import PORTFOLIO
    except ImportError:
        print("❌ 无法加载持仓配置")
        sys.exit(1)
    
    monitor = PriceMonitor()
    
    if args.check_key:
        # 监控重点股票（1分钟）
        key_stocks = [s for s in PORTFOLIO if s.get('priority') == 'high']
        monitor.monitor_stocks(key_stocks, verbose=False)
        
    elif args.check:
        # 监控所有股票（5分钟）- 但只检查是否有新预警
        monitor.monitor_stocks(PORTFOLIO, verbose=False)
        
    elif args.daily:
        # 开盘策略更新
        monitor.send_daily_strategy_update(PORTFOLIO)
        
    elif args.report:
        # 收盘日报
        monitor.send_daily_strategy_update(PORTFOLIO)
        
    else:
        # 手动运行 - 显示详细信息
        print("=" * 60)
        print("📊 持仓价格监控 - 手动运行")
        print("=" * 60)
        
        # 显示重点股票
        key_stocks = [s for s in PORTFOLIO if s.get('priority') == 'high']
        print(f"\n🔥 重点股票 ({len(key_stocks)}只，1分钟监控):")
        alerts = monitor.monitor_stocks(key_stocks, verbose=True)
        
        # 显示普通股票
        normal_stocks = [s for s in PORTFOLIO if s.get('priority') != 'high']
        print(f"\n📋 普通股票 ({len(normal_stocks)}只，5分钟监控):")
        alerts += monitor.monitor_stocks(normal_stocks, verbose=True)
        
        if not alerts:
            print("\n✅ 当前无交易信号，系统持续监控中...")


if __name__ == "__main__":
    main()
