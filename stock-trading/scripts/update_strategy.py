#!/usr/bin/env python3
"""
每日策略更新脚本
结合大盘走势、板块情况、个股技术面，自动更新买卖策略
"""

import requests
import json
import sys
from datetime import datetime
from pathlib import Path

# 添加配置目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "config"))

try:
    from my_portfolio import PORTFOLIO, PORTFOLIO_STATS
except ImportError:
    print("❌ 无法导入配置，请确保config/my_portfolio.py存在")
    sys.exit(1)


class StrategyUpdater:
    """策略更新器"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        self.strategy_changes = []
        
    def get_market_overview(self):
        """获取大盘概况"""
        print("\n📊 获取大盘概况...")
        
        indices = ["sh000001", "sz399001", "sz399006", "sh000688"]
        url = f"http://qt.gtimg.cn/q={','.join(indices)}"
        
        try:
            resp = self.session.get(url, timeout=10)
            resp.encoding = 'gb2312'
            
            market_data = {}
            for line in resp.text.strip().split(';'):
                if '~' in line:
                    parts = line.split('~')
                    if len(parts) > 45:
                        name = parts[1]
                        change_pct = float(parts[32])
                        market_data[name] = change_pct
            
            # 判断市场环境
            avg_change = sum(market_data.values()) / len(market_data)
            if avg_change > 1.0:
                condition = "强势上涨"
                bias = "多头"
            elif avg_change > 0.3:
                condition = "温和上涨"
                bias = "偏多"
            elif avg_change > -0.3:
                condition = "横盘震荡"
                bias = "中性"
            elif avg_change > -1.0:
                condition = "弱势下跌"
                bias = "偏空"
            else:
                condition = "大幅下跌"
                bias = "空头"
            
            return {
                "indices": market_data,
                "avg_change": avg_change,
                "condition": condition,
                "bias": bias
            }
        except Exception as e:
            print(f"⚠️ 大盘数据获取失败: {e}")
            return {"condition": "未知", "bias": "中性"}
    
    def get_stock_quote(self, stock):
        """获取个股行情"""
        prefix = "sh" if stock['market'] == 'sh' else "sz"
        url = f"http://qt.gtimg.cn/q={prefix}{stock['code']}"
        
        try:
            resp = self.session.get(url, timeout=5)
            resp.encoding = 'gb2312'
            
            for line in resp.text.strip().split(';'):
                if '~' in line:
                    parts = line.split('~')
                    if len(parts) > 45:
                        return {
                            'price': float(parts[3]),
                            'change_pct': float(parts[32]),
                            'high': float(parts[33]),
                            'low': float(parts[34]),
                        }
        except:
            pass
        return None
    
    def analyze_stock(self, stock, quote, market_bias):
        """分析个股并给出策略建议"""
        if not quote:
            return None
        
        price = quote['price']
        cost = stock['cost']
        pnl_pct = (price - cost) / cost * 100
        change_pct = quote['change_pct']
        
        alerts = stock.get('alerts', {})
        
        # 根据盈亏情况和市场环境调整策略
        strategy = {
            'code': stock['code'],
            'name': stock['name'],
            'current_price': price,
            'cost': cost,
            'pnl_pct': pnl_pct,
            'daily_change': change_pct,
            'action': 'HOLD',
            'reason': '',
            'new_target_buy': alerts.get('target_buy'),
            'new_target_reduce': alerts.get('target_reduce'),
        }
        
        # 动态调整策略
        if pnl_pct < -50:
            # 深度套牢
            strategy['action'] = '躺平'
            strategy['reason'] = '深度套牢，不建议割肉，等待反弹'
            if price < cost * 0.4:  # 跌到成本40%以下
                strategy['new_target_buy'] = round(price * 0.95, 2)
                strategy['reason'] += f'，极端低位可考虑补仓摊薄'
        
        elif pnl_pct < -15:
            # 重度浮亏
            if market_bias == "强势上涨":
                strategy['action'] = '持有'
                strategy['reason'] = '大盘强势，等待反弹'
            else:
                strategy['action'] = '观望'
                strategy['reason'] = '浮亏较大，等待企稳信号'
            # 更新加仓价为当前价下5%
            if alerts.get('target_buy'):
                strategy['new_target_buy'] = round(price * 0.95, 2)
        
        elif pnl_pct < -5:
            # 中度浮亏
            if change_pct > 3:
                strategy['action'] = '关注'
                strategy['reason'] = '反弹明显，关注持续性'
            elif market_bias == "强势上涨":
                strategy['action'] = '逢低加仓'
                strategy['reason'] = '大盘强势，可逢低加仓'
                strategy['new_target_buy'] = round(price * 0.97, 2)
            else:
                strategy['action'] = '持有'
                strategy['reason'] = '等待市场转暖'
        
        elif pnl_pct < 5:
            # 接近回本
            if pnl_pct > 0:
                strategy['action'] = '持有'
                strategy['reason'] = '已回本，可继续持有'
            else:
                strategy['action'] = '逢低加仓'
                strategy['reason'] = '接近回本，可逢低加仓摊薄'
                strategy['new_target_buy'] = round(price * 0.98, 2)
        
        else:
            # 盈利
            if pnl_pct > 15:
                strategy['action'] = '减仓'
                strategy['reason'] = '盈利可观，建议减仓锁定利润'
                strategy['new_target_reduce'] = round(price * 0.98, 2)
            else:
                strategy['action'] = '持有'
                strategy['reason'] = '盈利中，可持有观察'
        
        # 日内异动提醒
        if abs(change_pct) > 5:
            strategy['reason'] += f' | 今日{"大涨" if change_pct > 0 else "大跌"}{abs(change_pct):.1f}%，注意风险'
        
        return strategy
    
    def update_strategy(self):
        """更新策略"""
        print("=" * 70)
        print(f"📈 每日策略更新 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 70)
        
        # 1. 获取大盘环境
        market = self.get_market_overview()
        print(f"\n🏛️ 市场环境: {market['condition']} ({market['bias']})")
        
        # 2. 分析每只股票
        print("\n📊 个股策略分析:")
        print("-" * 70)
        
        strategies = []
        for stock in PORTFOLIO:
            quote = self.get_stock_quote(stock)
            strategy = self.analyze_stock(stock, quote, market['bias'])
            
            if strategy:
                strategies.append(strategy)
                
                action_emoji = {
                    '加仓': '🟢', '逢低加仓': '🟢', '买入': '🟢',
                    '持有': '🟡', '关注': '🟡', '观望': '🟡',
                    '减仓': '🔴', '卖出': '🔴',
                    '躺平': '⚪'
                }.get(strategy['action'], '➖')
                
                print(f"\n{action_emoji} {strategy['name']}({strategy['code']})")
                print(f"   现价: ¥{strategy['current_price']:.2f} | 成本: ¥{strategy['cost']:.3f}")
                print(f"   盈亏: {strategy['pnl_pct']:+.1f}% | 今日: {strategy['daily_change']:+.2f}%")
                print(f"   策略: {strategy['action']} | {strategy['reason']}")
                
                if strategy['new_target_buy'] != stock.get('alerts', {}).get('target_buy'):
                    old = stock.get('alerts', {}).get('target_buy')
                    print(f"   📝 加仓价调整: {old} → {strategy['new_target_buy']}")
                
                if strategy['new_target_reduce'] != stock.get('alerts', {}).get('target_reduce'):
                    old = stock.get('alerts', {}).get('target_reduce')
                    print(f"   📝 减仓价调整: {old} → {strategy['new_target_reduce']}")
        
        # 3. 保存策略报告
        report = {
            "date": datetime.now().strftime('%Y-%m-%d'),
            "market_condition": market['condition'],
            "market_bias": market['bias'],
            "strategies": strategies
        }
        
        report_path = Path(__file__).parent.parent / "reports"
        report_path.mkdir(exist_ok=True)
        
        report_file = report_path / f"strategy_{datetime.now().strftime('%Y%m%d')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print(f"\n" + "=" * 70)
        print(f"✅ 策略报告已保存: {report_file}")
        print("=" * 70)
        
        return strategies


def main():
    updater = StrategyUpdater()
    updater.update_strategy()


if __name__ == "__main__":
    main()
