#!/usr/bin/env python3
"""
个人持仓股池监控脚本
同时监控所有持仓股票，生成持仓报告
支持多数据源：腾讯财经(主) + AKShare(备用)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
import json
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# AKShare 备用数据源（如未安装则跳过）
try:
    import akshare as ak
    import pandas as pd
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False
    pd = None

# 导入持仓配置
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'config'))
from my_portfolio import PORTFOLIO, GLOBAL_ALERTS

class PortfolioMonitor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        self.results = []
        self.data_source_stats = {'tencent': 0, 'akshare': 0, 'failed': 0}
        
    def fetch_stock_data(self, stock):
        """获取单只股票数据（带备用数据源）"""
        code = stock['code']
        market = stock['market']
        
        # 主数据源：腾讯财经
        result = self._fetch_from_tencent(stock)
        
        # 如果腾讯失败或数据异常，尝试AKShare
        if result is None or result.get('error') or result.get('data_warning'):
            if AKSHARE_AVAILABLE:
                ak_result = self._fetch_from_akshare(stock)
                if ak_result and not ak_result.get('error'):
                    # 合并数据标记
                    if result and result.get('data_warning'):
                        ak_result['data_warning'] = f"腾讯: {result['data_warning']}; 已切换AKShare"
                    else:
                        ak_result['data_source'] = 'akshare'
                    return ak_result
        
        return result
    
    def _fetch_from_tencent(self, stock):
        """从腾讯财经获取数据"""
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
                return {'code': code, 'name': stock['name'], 'error': '数据字段不足'}
            
            price = float(parts[3])
            prev_close = float(parts[4])
            day_change_pct = float(parts[32])
            update_time = parts[30] if len(parts) > 30 else ''
            
            # 数据校验
            expected_change = (price - prev_close) / prev_close * 100 if prev_close > 0 else 0
            data_warning = None
            
            # 检查涨跌幅是否一致
            if abs(expected_change - day_change_pct) > 0.5:
                data_warning = f"涨跌幅不一致:计算{expected_change:.2f}% vs 接口{day_change_pct:.2f}%"
            
            # 检查数据时间（如果是昨天的数据，给出警告）
            if update_time:
                try:
                    data_time = datetime.strptime(update_time, '%Y%m%d%H%M%S')
                    now = datetime.now()
                    time_diff = (now - data_time).total_seconds() / 3600  # 小时
                    
                    # 如果数据超过6小时，可能是旧数据
                    if time_diff > 6:
                        if data_warning:
                            data_warning += f"; 数据延迟{time_diff:.1f}小时"
                        else:
                            data_warning = f"数据延迟{time_diff:.1f}小时"
                except:
                    pass
            
            cost = stock['cost']
            shares = stock['shares']
            cost_change_pct = (price - cost) / cost * 100
            profit = (price - cost) * shares
            
            self.data_source_stats['tencent'] += 1
            
            return {
                'code': code,
                'name': stock['name'],
                'price': price,
                'prev_close': prev_close,
                'change_pct': day_change_pct,
                'cost': cost,
                'shares': shares,
                'profit': profit,
                'profit_pct': cost_change_pct,
                'market_value': price * shares,
                'cost_value': cost * shares,
                'type': stock.get('type', 'individual'),
                'note': stock.get('note', ''),
                'data_source': 'tencent',
                'update_time': update_time,
                'data_warning': data_warning,
                'alerts': self.check_alerts(stock, price, cost_change_pct, day_change_pct)
            }
        except Exception as e:
            return {'code': stock['code'], 'name': stock['name'], 'error': f'腾讯: {str(e)}'}
    
    def _fetch_from_akshare(self, stock):
        """从AKShare获取数据（东方财富源）"""
        try:
            if not AKSHARE_AVAILABLE:
                return {'code': stock['code'], 'name': stock['name'], 'error': 'AKShare未安装'}
            
            code = stock['code']
            market = stock['market']
            
            # 判断是A股还是ETF
            stock_type = stock.get('type', 'individual')
            
            if stock_type == 'etf':
                # ETF数据
                df = ak.fund_etf_spot_em()
                row = df[df['代码'] == code]
            else:
                # A股数据
                df = ak.stock_zh_a_spot_em()
                row = df[df['代码'] == code]
            
            if row.empty:
                return {'code': code, 'name': stock['name'], 'error': 'AKShare未找到该股票'}
            
            row = row.iloc[0]
            
            price = float(row['最新价']) if pd.notna(row['最新价']) else 0
            prev_close = float(row['昨收']) if pd.notna(row['昨收']) else 0
            day_change_pct = float(row['涨跌幅']) if pd.notna(row['涨跌幅']) else 0
            
            cost = stock['cost']
            shares = stock['shares']
            cost_change_pct = (price - cost) / cost * 100
            profit = (price - cost) * shares
            
            self.data_source_stats['akshare'] += 1
            
            return {
                'code': code,
                'name': stock['name'],
                'price': price,
                'prev_close': prev_close,
                'change_pct': day_change_pct,
                'cost': cost,
                'shares': shares,
                'profit': profit,
                'profit_pct': cost_change_pct,
                'market_value': price * shares,
                'cost_value': cost * shares,
                'type': stock_type,
                'note': stock.get('note', ''),
                'data_source': 'akshare',
                'data_warning': None,
                'alerts': self.check_alerts(stock, price, cost_change_pct, day_change_pct)
            }
        except Exception as e:
            self.data_source_stats['failed'] += 1
            return {'code': stock['code'], 'name': stock['name'], 'error': f'AKShare: {str(e)}'}
    
    def check_alerts(self, stock, price, profit_pct, change_pct):
        """检查预警条件"""
        alerts = []
        config = stock.get('alerts', {})
        
        # 成本百分比预警
        if config.get('cost_pct_above') and profit_pct >= config['cost_pct_above']:
            alerts.append({'level': 'warning', 'type': '盈利达标', 'message': f"盈利 {profit_pct:.1f}%"})
        
        if config.get('cost_pct_below') and profit_pct <= -config['cost_pct_below']:
            alerts.append({'level': 'warning', 'type': '亏损扩大', 'message': f"亏损 {abs(profit_pct):.1f}%"})
        
        # 买卖点预警
        if config.get('target_buy') and price <= config['target_buy']:
            alerts.append({'level': 'warning', 'type': '买入信号', 'message': f"触及补仓价 ¥{config['target_buy']}"})
        
        if config.get('target_reduce') and price >= config['target_reduce']:
            alerts.append({'level': 'caution', 'type': '减仓信号', 'message': f"触及减仓价 ¥{config['target_reduce']}"})
        
        if config.get('stop_loss') and price <= config['stop_loss']:
            alerts.append({'level': 'warning', 'type': '止损信号', 'message': f"跌破止损价 ¥{config['stop_loss']}"})
        
        # 日内异动
        if config.get('change_pct_above') and change_pct >= config['change_pct_above']:
            alerts.append({'level': 'caution', 'type': '大涨提醒', 'message': f"日内大涨 {change_pct:.1f}%"})
        
        if config.get('change_pct_below') and change_pct <= -config['change_pct_below']:
            alerts.append({'level': 'caution', 'type': '大跌提醒', 'message': f"日内大跌 {change_pct:.1f}%"})
        
        return alerts
    
    def run(self):
        """执行全仓监控"""
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始扫描 {len(PORTFOLIO)} 只持仓股票...")
        print(f"数据源: 腾讯财经 (主) + AKShare/东方财富 (备用)\n")
        
        # 并发获取数据
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(self.fetch_stock_data, stock): stock for stock in PORTFOLIO}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    self.results.append(result)
        
        return self.generate_report()
    
    def generate_report(self):
        """生成持仓报告"""
        # 过滤掉错误数据
        valid_results = [r for r in self.results if 'error' not in r]
        errors = [r for r in self.results if 'error' in r]
        
        # 计算汇总
        total_cost = sum(r['cost_value'] for r in valid_results)
        total_value = sum(r['market_value'] for r in valid_results)
        total_profit = total_value - total_cost
        total_profit_pct = (total_profit / total_cost * 100) if total_cost > 0 else 0
        
        # 统计预警
        all_alerts = []
        data_warnings = []
        for r in valid_results:
            if r['alerts']:
                all_alerts.append({'name': r['name'], 'alerts': r['alerts']})
            if r.get('data_warning'):
                data_warnings.append({'name': r['name'], 'warning': r['data_warning'], 'source': r.get('data_source', 'unknown')})
        
        # 生成报告
        report_lines = [
            "=" * 70,
            "📊 持仓监控报告",
            "=" * 70,
            f"📅 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"📈 持仓: {len(valid_results)} 只股票",
            f"📡 数据源: 腾讯{self.data_source_stats['tencent']}只, AKShare{self.data_source_stats['akshare']}只",
            "",
            "💰 资产汇总:",
            f"   总成本:   ¥{total_cost:>15,.2f}",
            f"   总市值:   ¥{total_value:>15,.2f}",
            f"   总盈亏:   {'🔴' if total_profit >= 0 else '🟢'}¥{total_profit:>+15,.2f} ({total_profit_pct:+.2f}%)",
            "",
            "📋 持仓明细:",
            "-" * 70,
        ]
        
        # 按盈亏排序
        sorted_results = sorted(valid_results, key=lambda x: x['profit_pct'], reverse=True)
        
        for r in sorted_results:
            icon = "🔴" if r['profit'] >= 0 else "🟢"
            alert_icon = "⚠️" if r['alerts'] else "  "
            source_tag = "[AK]" if r.get('data_source') == 'akshare' else ""
            report_lines.append(
                f"{alert_icon} {r['name']:8s} ({r['code']}) {source_tag:5s}| "
                f"{r['shares']:>6,}股 | "
                f"现价¥{r['price']:>8.2f} | "
                f"盈亏{icon}¥{r['profit']:>+10,.0f} ({r['profit_pct']:>+6.2f}%)"
            )
        
        report_lines.append("-" * 70)
        
        # 数据警告
        if data_warnings:
            report_lines.extend([
                "",
                f"⚠️ 数据警告 (共 {len(data_warnings)} 条):",
                "-" * 70,
            ])
            for item in data_warnings:
                report_lines.append(f"   📌 {item['name']} [{item['source']}]: {item['warning']}")
        
        # 预警汇总
        if all_alerts:
            report_lines.extend([
                "",
                f"🚨 预警汇总 (共 {sum(len(a['alerts']) for a in all_alerts)} 条):",
                "-" * 70,
            ])
            for item in all_alerts:
                report_lines.append(f"\n📌 {item['name']}:")
                for alert in item['alerts']:
                    icon = "🚨" if alert['level'] == 'warning' else "⚠️"
                    report_lines.append(f"   {icon} [{alert['type']}] {alert['message']}")
        else:
            report_lines.extend([
                "",
                "✅ 当前无预警，持仓正常",
            ])
        
        if errors:
            report_lines.extend([
                "",
                f"❌ 获取失败 ({len(errors)} 只):",
            ])
            for e in errors:
                report_lines.append(f"   - {e['name']} ({e['code']}): {e['error']}")
        
        report_lines.append("=" * 70)
        
        report = "\n".join(report_lines)
        return report, total_profit, len(all_alerts)

def main():
    monitor = PortfolioMonitor()
    report, total_profit, alert_count = monitor.run()
    print(report)
    return alert_count

if __name__ == "__main__":
    alert_count = main()
    exit(alert_count)
