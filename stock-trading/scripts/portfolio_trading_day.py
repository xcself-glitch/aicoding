#!/usr/bin/env python3
"""
交易日全流程监控系统
- 盘前简报 (8:30)
- 开盘建议 (9:15)
- 盘中监控 (9:30-15:00)
- 收盘复盘 (15:30)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
import json
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess

# 导入持仓配置
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'config'))
from my_portfolio import PORTFOLIO, GLOBAL_ALERTS

class TradingDayMonitor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        self.results = []
        self.prev_close_data = {}  # 上一交易日数据
        self.today_data = {}
        
    def fetch_stock_data(self, stock):
        """获取单只股票数据"""
        try:
            code = stock['code']
            prefix = 'sh' if stock['market'] == 'sh' else 'sz'
            url = f"http://qt.gtimg.cn/q={prefix}{code}"
            
            resp = self.session.get(url, timeout=5)
            resp.encoding = 'gbk'
            
            text = resp.text
            start = text.find('"') + 1
            end = text.rfind('"')
            parts = text[start:end].split('~')
            
            if len(parts) < 40:
                return None
            
            price = float(parts[3])
            prev_close = float(parts[4])
            cost = stock['cost']
            shares = stock['shares']
            cost_change_pct = (price - cost) / cost * 100
            profit = (price - cost) * shares
            day_change_pct = float(parts[32])
            
            return {
                'code': code,
                'name': stock['name'],
                'price': price,
                'prev_close': prev_close,
                'open': float(parts[5]),
                'high': float(parts[33]),
                'low': float(parts[34]),
                'change_pct': day_change_pct,
                'volume': float(parts[36]),  # 成交量（手）
                'turnover': float(parts[37]), # 成交额（万）
                'cost': cost,
                'shares': shares,
                'profit': profit,
                'profit_pct': cost_change_pct,
                'market_value': price * shares,
                'cost_value': cost * shares,
                'type': stock.get('type', 'individual'),
                'note': stock.get('note', ''),
            }
        except Exception as e:
            return {'code': stock['code'], 'name': stock['name'], 'error': str(e)}
    
    def fetch_all(self):
        """获取全部持仓数据"""
        self.results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(self.fetch_stock_data, stock): stock for stock in PORTFOLIO}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    self.results.append(result)
        return [r for r in self.results if 'error' not in r]
    
    def generate_pre_market_report(self):
        """盘前简报 (8:30)"""
        now = datetime.now()
        
        report_lines = [
            "=" * 70,
            "🌅 盘前简报",
            "=" * 70,
            f"📅 日期: {now.strftime('%Y年%m月%d日')} 星期{'一二三四五六日'[now.weekday()]}\n",
            "📊 今日交易提示:",
            f"   A股开盘时间: 09:30",
            f"   集合竞价: 09:15-09:25",
            f"   上午收盘: 11:30",
            f"   下午开盘: 13:00",
            f"   下午收盘: 15:00\n",
        ]
        
        # 获取当前持仓状态
        stocks = self.fetch_all()
        
        # 计算整体情况
        total_cost = sum(s['cost_value'] for s in stocks)
        total_value = sum(s['market_value'] for s in stocks)
        total_profit = total_value - total_cost
        total_profit_pct = (total_profit / total_cost * 100) if total_cost > 0 else 0
        
        report_lines.extend([
            "💰 当前持仓概况:",
            f"   总成本:   ¥{total_cost:>15,.2f}",
            f"   总市值:   ¥{total_value:>15,.2f}",
            f"   总盈亏:   {'🔴' if total_profit >= 0 else '🟢'}¥{total_profit:>+15,.2f} ({total_profit_pct:+.2f}%)",
            "",
            "⚠️ 重点关注股票:",
        ])
        
        # 找出需要关注的股票
        alerts = []
        for s in stocks:
            if s['profit_pct'] <= -50:  # 亏损超50%
                alerts.append(f"   🚨 {s['name']}: 深套 {s['profit_pct']:.1f}%，建议关注止损机会")
            elif s['profit_pct'] <= -15:  # 亏损超15%
                alerts.append(f"   ⚠️  {s['name']}: 浮亏 {s['profit_pct']:.1f}%，关注反弹")
            elif s['profit_pct'] >= 5:  # 盈利超5%
                alerts.append(f"   ✅ {s['name']}: 浮盈 {s['profit_pct']:.1f}%，关注止盈")
        
        if alerts:
            report_lines.extend(alerts)
        else:
            report_lines.append("   当前持仓相对平稳，暂无重大风险")
        
        # 操作建议
        report_lines.extend([
            "",
            "💡 今日操作建议:",
        ])
        
        # 深套股票建议
        deep_loss = [s for s in stocks if s['profit_pct'] <= -50]
        if deep_loss:
            report_lines.append(f"   1. 深套股票({len(deep_loss)}只): 建议观望，暂不加仓摊薄")
        
        # 接近补仓点的股票
        buy_opps = []
        for s in stocks:
            alerts = s.get('alerts', {})
            if alerts.get('target_buy') and s['price'] <= alerts['target_buy'] * 1.05:
                buy_opps.append(s['name'])
        if buy_opps:
            report_lines.append(f"   2. 关注机会: {', '.join(buy_opps)} 接近补仓区间")
        
        report_lines.extend([
            "   3. 整体策略: 控制仓位，等待市场企稳信号",
            "   4. 风险控制: 单票亏损超15%谨慎加仓",
            "",
            "⏰ 盘中将每10分钟扫描一次，重大变动实时提醒",
            "=" * 70,
        ])
        
        return "\n".join(report_lines)
    
    def generate_open_advice(self):
        """开盘建议 (9:15)"""
        stocks = self.fetch_all()
        
        report_lines = [
            "=" * 70,
            "📈 开盘操作建议",
            "=" * 70,
            f"📅 时间: {datetime.now().strftime('%H:%M:%S')}\n",
            "集合竞价阶段建议:\n",
        ]
        
        # 分析每只股票的竞价情况
        for s in stocks:
            pre_change = s['change_pct']
            
            if pre_change > 3:
                advice = "高开较多，可考虑部分减仓锁定利润"
            elif pre_change > 1:
                advice = "小幅高开，观望为主"
            elif pre_change < -3:
                advice = "低开较多，谨慎观察，暂不建议抄底"
            elif pre_change < -1:
                advice = "小幅低开，关注支撑位"
            else:
                advice = "平开附近，按原有策略执行"
            
            report_lines.append(f"📌 {s['name']:8s}: {pre_change:+.2f}% - {advice}")
        
        report_lines.extend([
            "",
            "💡 总体建议:",
            "   - 9:30开盘后观察15分钟再决定操作",
            "   - 避免集合竞价冲动交易",
            "   - 关注成交量变化",
            "=" * 70,
        ])
        
        return "\n".join(report_lines)
    
    def generate_intraday_check(self):
        """盘中监控检查"""
        stocks = self.fetch_all()
        
        # 计算汇总
        total_cost = sum(s['cost_value'] for s in stocks)
        total_value = sum(s['market_value'] for s in stocks)
        total_profit = total_value - total_cost
        total_profit_pct = (total_profit / total_cost * 100) if total_cost > 0 else 0
        
        # 找出日内异动
        alerts = []
        for s in stocks:
            if abs(s['change_pct']) >= 5:
                direction = "📈 大涨" if s['change_pct'] > 0 else "📉 大跌"
                alerts.append(f"{direction} {s['name']:8s} {s['change_pct']:+.2f}%")
            
            # 检查买卖点
            alerts_config = next((p.get('alerts', {}) for p in PORTFOLIO if p['code'] == s['code']), {})
            
            if alerts_config.get('target_buy') and s['price'] <= alerts_config['target_buy']:
                alerts.append(f"🛒 触及买点 {s['name']:8s} ¥{s['price']:.2f}")
            
            if alerts_config.get('target_reduce') and s['price'] >= alerts_config['target_reduce']:
                alerts.append(f"💰 触及减仓点 {s['name']:8s} ¥{s['price']:.2f}")
        
        report_lines = [
            "=" * 70,
            f"📊 盘中监控 [{datetime.now().strftime('%H:%M:%S')}]",
            "=" * 70,
            f"💰 总盈亏: {'🔴' if total_profit >= 0 else '🟢'}¥{total_profit:>+12,.0f} ({total_profit_pct:+.2f}%)",
        ]
        
        if alerts:
            report_lines.extend([
                "",
                "🚨 异动提醒:",
            ])
            for alert in alerts:
                report_lines.append(f"   {alert}")
        else:
            report_lines.append("   暂无重大异动")
        
        # 显示关键持仓
        report_lines.extend([
            "",
            "📋 重点持仓:",
        ])
        for s in sorted(stocks, key=lambda x: abs(x['profit']), reverse=True)[:5]:
            icon = "🔴" if s['profit'] >= 0 else "🟢"
            report_lines.append(
                f"   {s['name']:8s} ¥{s['price']:>7.2f} {icon}¥{s['profit']:>+10,.0f} ({s['profit_pct']:>+6.2f}%)"
            )
        
        report_lines.append("=" * 70)
        return "\n".join(report_lines)
    
    def generate_close_summary(self):
        """收盘复盘 (15:30)"""
        stocks = self.fetch_all()
        
        # 计算汇总
        total_cost = sum(s['cost_value'] for s in stocks)
        total_value = sum(s['market_value'] for s in stocks)
        total_profit = total_value - total_cost
        total_profit_pct = (total_profit / total_cost * 100) if total_cost > 0 else 0
        
        # 统计涨跌
        gainers = [s for s in stocks if s['change_pct'] > 0]
        losers = [s for s in stocks if s['change_pct'] < 0]
        
        # 最大涨跌
        max_gainer = max(gainers, key=lambda x: x['change_pct']) if gainers else None
        max_loser = min(losers, key=lambda x: x['change_pct']) if losers else None
        
        report_lines = [
            "=" * 70,
            "🌙 收盘复盘总结",
            "=" * 70,
            f"📅 日期: {datetime.now().strftime('%Y年%m月%d日')}\n",
            "📊 账户概况:",
            f"   总成本:   ¥{total_cost:>15,.2f}",
            f"   总市值:   ¥{total_value:>15,.2f}",
            f"   当日盈亏: {'🔴' if total_profit >= 0 else '🟢'}¥{total_profit:>+15,.2f} ({total_profit_pct:+.2f}%)",
            f"   涨跌分布: 🔴{len(gainers)}只 🟢{len(losers)}只",
            "",
        ]
        
        if max_gainer:
            report_lines.append(f"📈 今日最佳: {max_gainer['name']} +{max_gainer['change_pct']:.2f}%")
        if max_loser:
            report_lines.append(f"📉 今日最差: {max_loser['name']} {max_loser['change_pct']:.2f}%")
        
        # 操作建议
        report_lines.extend([
            "",
            "💡 明日操作建议:",
        ])
        
        # 找出需要操作的股票
        for s in stocks:
            if s['profit_pct'] <= -50:
                report_lines.append(f"   🚨 {s['name']}: 深套状态，考虑止损或长期持有策略")
            elif s['change_pct'] >= 5:
                report_lines.append(f"   ✅ {s['name']}: 今日大涨，明日关注是否延续")
            elif s['change_pct'] <= -5:
                report_lines.append(f"   ⚠️  {s['name']}: 今日大跌，关注是否超跌反弹")
        
        report_lines.extend([
            "",
            "📋 持仓明细:",
            "-" * 70,
        ])
        
        for s in sorted(stocks, key=lambda x: x['market_value'], reverse=True):
            icon = "🔴" if s['profit'] >= 0 else "🟢"
            day_icon = "📈" if s['change_pct'] > 0 else ("📉" if s['change_pct'] < 0 else "➖")
            report_lines.append(
                f"{icon}{day_icon} {s['name']:8s} | 持仓{s['shares']:>6,}股 | "
                f"现价¥{s['price']:>7.2f} | 日涨跌{s['change_pct']:>+6.2f}% | "
                f"盈亏{s['profit_pct']:>+6.2f}%"
            )
        
        report_lines.extend([
            "-" * 70,
            "",
            f"⏰ 下次监控: 明日 {GLOBAL_ALERTS.get('pre_market_time', '08:30')}",
            "=" * 70,
        ])
        
        return "\n".join(report_lines)

def main():
    monitor = TradingDayMonitor()
    
    if len(sys.argv) < 2:
        print("Usage: python portfolio_trading_day.py [pre_market|open|intraday|close]")
        return
    
    mode = sys.argv[1]
    
    if mode == "pre_market":
        print(monitor.generate_pre_market_report())
    elif mode == "open":
        print(monitor.generate_open_advice())
    elif mode == "intraday":
        print(monitor.generate_intraday_check())
    elif mode == "close":
        print(monitor.generate_close_summary())
    else:
        print(f"Unknown mode: {mode}")

if __name__ == "__main__":
    main()
