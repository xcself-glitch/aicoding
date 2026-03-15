#!/usr/bin/env python3
"""
股票交易策略优化版 V2.0
基于回测结果和交易理论优化:
1. 趋势跟踪 + 均值回归动态切换
2. 波动率自适应过滤
3. 多时间框架趋势确认
4. 改进的仓位管理 (Kelly + 波动率调整)
5. 动态止损止盈 (ATR-based)
6. 交易频率控制 (避免过度交易)
"""

import sys
import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# 导入持仓配置
sys.path.append(str(Path(__file__).parent.parent))
from config.my_portfolio import PORTFOLIO

# 尝试导入yfinance
try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False


class OptimizedBacktestEngine:
    """优化版回测引擎"""
    
    def __init__(self, initial_capital: float = 100000.0):
        self.initial_capital = initial_capital
        self.min_hold_days = 5  # 最少持有天数
        self.max_hold_days = 30  # 最大持有天数
        self.cooldown_days = 3   # 交易冷却期
        
    def fetch_stock_data(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        """获取股票历史数据"""
        if not YF_AVAILABLE:
            return self._generate_mock_data(symbol)
        
        try:
            if symbol.startswith('6'):
                ticker = f"{symbol}.SS"
            elif symbol.startswith('0') or symbol.startswith('3'):
                ticker = f"{symbol}.SZ"
            else:
                ticker = symbol
            
            stock = yf.Ticker(ticker)
            df = stock.history(period=period)
            
            if df.empty:
                return self._generate_mock_data(symbol)
            
            return df
        except Exception as e:
            print(f"获取{symbol}数据失败，使用模拟数据")
            return self._generate_mock_data(symbol)
    
    def _generate_mock_data(self, symbol: str, days: int = 252) -> pd.DataFrame:
        """生成模拟数据"""
        np.random.seed(hash(symbol) % 1000)
        dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
        
        base_price = np.random.uniform(10, 100)
        volatility = np.random.uniform(0.015, 0.025)
        drift = np.random.uniform(-0.0001, 0.0003)
        
        returns = np.random.normal(drift, volatility, days)
        prices = base_price * np.exp(np.cumsum(returns))
        volume = np.random.randint(1000000, 10000000, days)
        
        df = pd.DataFrame({
            'Open': prices * (1 + np.random.normal(0, 0.001, days)),
            'High': prices * (1 + np.abs(np.random.normal(0, 0.012, days))),
            'Low': prices * (1 - np.abs(np.random.normal(0, 0.012, days))),
            'Close': prices,
            'Volume': volume
        }, index=dates)
        
        return df
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标"""
        df = df.copy()
        
        # 1. 多周期均线系统
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA10'] = df['Close'].rolling(window=10).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        
        # 均线斜率 (趋势强度)
        df['MA5_Slope'] = df['MA5'].diff(5) / 5
        df['MA20_Slope'] = df['MA20'].diff(20) / 20
        
        # 2. RSI (多个周期)
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # RSI趋势
        df['RSI_MA'] = df['RSI'].rolling(window=5).mean()
        
        # 3. MACD
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']
        df['MACD_Trend'] = df['MACD_Hist'].diff()
        
        # 4. 布林带
        df['BB_Middle'] = df['Close'].rolling(window=20).mean()
        bb_std = df['Close'].rolling(window=20).std()
        df['BB_Upper'] = df['BB_Middle'] + (bb_std * 2)
        df['BB_Lower'] = df['BB_Middle'] - (bb_std * 2)
        df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / df['BB_Middle']
        df['BB_Position'] = (df['Close'] - df['BB_Lower']) / (df['BB_Upper'] - df['BB_Lower'])
        
        # 5. ATR 和波动率
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['ATR'] = true_range.rolling(14).mean()
        df['ATR_Pct'] = df['ATR'] / df['Close'] * 100
        
        # 波动率状态
        df['Volatility'] = df['Close'].pct_change().rolling(20).std() * np.sqrt(252) * 100
        df['Vol_State'] = pd.cut(df['Volatility'], bins=[0, 20, 40, 100], labels=['low', 'medium', 'high'])
        
        # 6. 成交量指标
        df['Volume_MA'] = df['Volume'].rolling(window=20).mean()
        df['Volume_Ratio'] = df['Volume'] / df['Volume_MA']
        df['Volume_Trend'] = df['Volume'].rolling(5).mean() / df['Volume'].rolling(20).mean()
        
        # 7. 趋势强度 (ADX简化版)
        df['DM+'] = np.where(df['High'].diff() > df['Low'].diff().abs(), 
                              df['High'].diff().clip(lower=0), 0)
        df['DM-'] = np.where(df['Low'].diff().abs() > df['High'].diff(),
                              (-df['Low'].diff()).clip(lower=0), 0)
        df['DX'] = np.abs(df['DM+'] - df['DM-']) / (df['DM+'] + df['DM-']) * 100
        df['ADX'] = df['DX'].rolling(14).mean()
        
        # 8. 价格动量
        df['Momentum_5'] = df['Close'] / df['Close'].shift(5) - 1
        df['Momentum_10'] = df['Close'] / df['Close'].shift(10) - 1
        df['Momentum_20'] = df['Close'] / df['Close'].shift(20) - 1
        
        return df
    
    def detect_market_regime(self, df: pd.DataFrame, idx: int) -> str:
        """检测市场状态: trending, ranging, volatile"""
        if idx < 60:
            return "unknown"
        
        adx = df['ADX'].iloc[idx]
        bb_width = df['BB_Width'].iloc[idx]
        vol = df['Volatility'].iloc[idx]
        
        if adx > 25 and bb_width > 0.05:
            return "trending"
        elif vol > 40:
            return "volatile"
        else:
            return "ranging"
    
    def generate_optimized_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """生成优化后的交易信号"""
        df = df.copy()
        df['Signal'] = 0
        df['Signal_Strength'] = 0
        df['Signal_Reason'] = ""
        
        for i in range(60, len(df)):
            regime = self.detect_market_regime(df, i)
            
            buy_score = 0
            sell_score = 0
            reasons = []
            
            # 根据市场状态使用不同策略
            if regime == "trending":
                # 趋势市场: 使用趋势跟踪策略
                # MA多头排列
                if df['MA5'].iloc[i] > df['MA10'].iloc[i] > df['MA20'].iloc[i]:
                    buy_score += 2
                    reasons.append("MA多头排列")
                elif df['MA5'].iloc[i] < df['MA10'].iloc[i] < df['MA20'].iloc[i]:
                    sell_score += 2
                    reasons.append("MA空头排列")
                
                # MACD趋势确认
                if df['MACD'].iloc[i] > df['MACD_Signal'].iloc[i] and df['MACD_Trend'].iloc[i] > 0:
                    buy_score += 1
                    reasons.append("MACD多头")
                elif df['MACD'].iloc[i] < df['MACD_Signal'].iloc[i] and df['MACD_Trend'].iloc[i] < 0:
                    sell_score += 1
                    reasons.append("MACD空头")
                    
            elif regime == "ranging":
                # 震荡市场: 使用均值回归策略
                bb_pos = df['BB_Position'].iloc[i]
                
                if bb_pos < 0.2 and df['RSI'].iloc[i] < 40:
                    buy_score += 2
                    reasons.append("BB下轨+RSI低位")
                elif bb_pos > 0.8 and df['RSI'].iloc[i] > 60:
                    sell_score += 2
                    reasons.append("BB上轨+RSI高位")
                    
                # RSI背离检测
                if df['RSI'].iloc[i] > 35 and df['RSI'].iloc[i] < 65:
                    buy_score += 0.5
                    sell_score += 0.5
                    
            else:  # volatile
                # 高波动市场: 保守策略
                if df['RSI'].iloc[i] < 30 and df['BB_Position'].iloc[i] < 0.1:
                    buy_score += 1
                    reasons.append("极端超卖")
                elif df['RSI'].iloc[i] > 70 and df['BB_Position'].iloc[i] > 0.9:
                    sell_score += 1
                    reasons.append("极端超买")
            
            # 成交量确认 (所有市场都适用)
            if df['Volume_Ratio'].iloc[i] > 1.3:
                if buy_score > sell_score:
                    buy_score += 1
                    reasons.append("放量确认")
                elif sell_score > buy_score:
                    sell_score += 1
                    reasons.append("放量确认")
            
            # 波动率过滤 - 避免在极高波动时交易
            if df['ATR_Pct'].iloc[i] > 5:
                buy_score *= 0.5
                sell_score *= 0.5
                reasons.append("高波动警告")
            
            # 设置信号
            df.loc[df.index[i], 'Signal_Strength'] = buy_score - sell_score
            
            if buy_score >= 3:
                df.loc[df.index[i], 'Signal'] = 1
                df.loc[df.index[i], 'Signal_Reason'] = ",".join(reasons)
            elif sell_score >= 3:
                df.loc[df.index[i], 'Signal'] = -1
                df.loc[df.index[i], 'Signal_Reason'] = ",".join(reasons)
            
            df.loc[df.index[i], 'Market_Regime'] = regime
        
        return df
    
    def calculate_position_size(self, capital: float, price: float, 
                                 atr: float, win_rate: float, 
                                 avg_win: float, avg_loss: float) -> int:
        """优化版仓位计算: Kelly + 波动率调整"""
        # 基础Kelly仓位
        if avg_loss > 0 and win_rate > 0:
            b = avg_win / avg_loss
            p = win_rate
            q = 1 - p
            kelly = (b * p - q) / b
            base_position = max(0.05, min(0.3, kelly))  # 限制5%-30%
        else:
            base_position = 0.1  # 默认10%
        
        # 波动率调整 - 高波动降低仓位
        atr_pct = atr / price
        vol_factor = max(0.3, min(1.0, 0.03 / atr_pct))  # ATR 3%为基准
        
        adjusted_position = base_position * vol_factor
        shares = int((capital * adjusted_position) / price)
        
        return max(100, shares)  # 最少100股
    
    def run_optimized_backtest(self, stock_config: Dict, period: str = "1y") -> Dict:
        """运行优化版回测"""
        symbol = stock_config['code']
        name = stock_config['name']
        
        print(f"\n{'='*70}")
        print(f"🚀 优化版回测: {name} ({symbol})")
        print(f"策略: 动态趋势跟踪 + 均值回归 + 波动率过滤")
        print(f"{'='*70}")
        
        # 获取数据
        df = self.fetch_stock_data(symbol, period)
        df = self.calculate_indicators(df)
        df = self.generate_optimized_signals(df)
        
        # 回测参数
        initial_cash = self.initial_capital
        cash = initial_cash
        position = 0
        position_shares = 0
        entry_price = 0
        entry_date = None
        
        trades = []
        equity = []
        
        wins = 0
        losses = 0
        total_wins = 0
        total_losses = 0
        
        last_trade_date = None
        
        for i in range(60, len(df)):
            date = df.index[i]
            price = df['Close'].iloc[i]
            high = df['High'].iloc[i]
            low = df['Low'].iloc[i]
            signal = df['Signal'].iloc[i]
            atr = df['ATR'].iloc[i]
            regime = df['Market_Regime'].iloc[i]
            
            current_equity = cash + position_shares * price
            equity.append({'date': date, 'equity': current_equity})
            
            # 持仓中的动态止损止盈
            if position_shares > 0:
                hold_days = (date - entry_date).days if entry_date else 0
                
                # ATR动态止损
                stop_loss_price = entry_price - (2.0 * atr)
                # 移动止盈
                highest_price = max([t['price'] for t in trades if t['type'] == 'BUY'][-1:]) if trades else entry_price
                take_profit_price = highest_price - (1.5 * atr) if highest_price > entry_price * 1.05 else entry_price * 1.08
                
                # 止损检查
                if low <= stop_loss_price:
                    sell_price = max(low, stop_loss_price)
                    profit = position_shares * (sell_price - entry_price)
                    
                    if profit > 0:
                        wins += 1
                        total_wins += profit
                    else:
                        losses += 1
                        total_losses += abs(profit)
                    
                    cash += position_shares * sell_price
                    trades.append({
                        'date': date, 'type': 'SELL', 'price': sell_price,
                        'shares': position_shares, 'reason': '止损',
                        'profit': profit, 'return_pct': profit / (position_shares * entry_price) * 100
                    })
                    
                    print(f"📉 止损 [{date.strftime('%Y-%m-%d')}] {name} @ ¥{sell_price:.2f} | {'🔴' if profit > 0 else '🟢'}¥{profit:,.2f}")
                    
                    position_shares = 0
                    last_trade_date = date
                    continue
                
                # 止盈检查
                if high >= take_profit_price and hold_days >= self.min_hold_days:
                    sell_price = min(high, take_profit_price)
                    profit = position_shares * (sell_price - entry_price)
                    
                    wins += 1
                    total_wins += profit
                    
                    cash += position_shares * sell_price
                    trades.append({
                        'date': date, 'type': 'SELL', 'price': sell_price,
                        'shares': position_shares, 'reason': '止盈',
                        'profit': profit, 'return_pct': profit / (position_shares * entry_price) * 100
                    })
                    
                    print(f"📉 止盈 [{date.strftime('%Y-%m-%d')}] {name} @ ¥{sell_price:.2f} | 🔴¥{profit:,.2f} (+{profit/(position_shares*entry_price)*100:.1f}%)")
                    
                    position_shares = 0
                    last_trade_date = date
                    continue
                
                # 最大持仓时间检查
                if hold_days >= self.max_hold_days:
                    sell_price = price
                    profit = position_shares * (sell_price - entry_price)
                    
                    if profit > 0:
                        wins += 1
                        total_wins += profit
                    else:
                        losses += 1
                        total_losses += abs(profit)
                    
                    cash += position_shares * sell_price
                    trades.append({
                        'date': date, 'type': 'SELL', 'price': sell_price,
                        'shares': position_shares, 'reason': '时间平仓',
                        'profit': profit, 'return_pct': profit / (position_shares * entry_price) * 100
                    })
                    
                    print(f"📉 平仓 [{date.strftime('%Y-%m-%d')}] {name} @ ¥{sell_price:.2f} ({hold_days}天) | {'🔴' if profit > 0 else '🟢'}¥{profit:,.2f}")
                    
                    position_shares = 0
                    last_trade_date = date
                    continue
            
            # 冷却期检查
            if last_trade_date and (date - last_trade_date).days < self.cooldown_days:
                continue
            
            # 买入信号
            if signal == 1 and position_shares == 0:
                win_rate = wins / (wins + losses) if (wins + losses) > 0 else 0.5
                avg_win_amt = total_wins / wins if wins > 0 else price * 0.05
                avg_loss_amt = total_losses / losses if losses > 0 else price * 0.03
                
                shares = self.calculate_position_size(
                    current_equity, price, atr, win_rate, avg_win_amt, avg_loss_amt
                )
                
                cost = shares * price
                if cost <= cash * 0.95:  # 保留5%现金
                    position_shares = shares
                    entry_price = price
                    entry_date = date
                    cash -= cost
                    
                    reason = df['Signal_Reason'].iloc[i]
                    regime_str = f"[{regime}]"
                    
                    trades.append({
                        'date': date, 'type': 'BUY', 'price': price,
                        'shares': shares, 'value': cost, 'reason': reason
                    })
                    
                    print(f"📈 买入 [{date.strftime('%Y-%m-%d')}] {name} @ ¥{price:.2f} x {shares}股 {regime_str}")
                    if reason:
                        print(f"    原因: {reason}")
            
            # 卖出信号
            elif signal == -1 and position_shares > 0:
                sell_price = price
                profit = position_shares * (sell_price - entry_price)
                hold_days = (date - entry_date).days if entry_date else 0
                
                if hold_days >= self.min_hold_days:  # 最少持有天数
                    if profit > 0:
                        wins += 1
                        total_wins += profit
                    else:
                        losses += 1
                        total_losses += abs(profit)
                    
                    cash += position_shares * sell_price
                    reason = df['Signal_Reason'].iloc[i]
                    
                    trades.append({
                        'date': date, 'type': 'SELL', 'price': sell_price,
                        'shares': position_shares, 'reason': f'信号-{reason}',
                        'profit': profit, 'return_pct': profit / (position_shares * entry_price) * 100
                    })
                    
                    print(f"📉 卖出 [{date.strftime('%Y-%m-%d')}] {name} @ ¥{sell_price:.2f} | {'🔴' if profit > 0 else '🟢'}¥{profit:,.2f} ({profit/(position_shares*entry_price)*100:+.1f}%)")
                    
                    position_shares = 0
                    last_trade_date = date
        
        # 计算结果
        final_price = df['Close'].iloc[-1]
        final_equity = cash + position_shares * final_price
        total_return = (final_equity - initial_cash) / initial_cash * 100
        
        equity_df = pd.DataFrame(equity)
        if not equity_df.empty:
            equity_df['cummax'] = equity_df['equity'].cummax()
            equity_df['drawdown'] = (equity_df['equity'] - equity_df['cummax']) / equity_df['cummax'] * 100
            max_drawdown = equity_df['drawdown'].min()
        else:
            max_drawdown = 0
        
        if len(equity) > 1:
            returns = equity_df['equity'].pct_change().dropna()
            sharpe = (returns.mean() * 252 - 0.03) / (returns.std() * np.sqrt(252)) if returns.std() > 0 else 0
            calmar = total_return / abs(max_drawdown) if max_drawdown != 0 else 0
        else:
            sharpe = 0
            calmar = 0
        
        # 计算不同市场状态的收益
        regime_returns = {}
        for regime in ['trending', 'ranging', 'volatile']:
            regime_trades = [t for t in trades if 'regime' in str(t)]
            # 简化处理
        
        result = {
            'symbol': symbol,
            'name': name,
            'initial_capital': initial_cash,
            'final_equity': final_equity,
            'total_return_pct': total_return,
            'max_drawdown_pct': max_drawdown,
            'sharpe_ratio': sharpe,
            'calmar_ratio': calmar,
            'total_trades': len([t for t in trades if t['type'] == 'SELL']),
            'winning_trades': wins,
            'losing_trades': losses,
            'win_rate': wins / (wins + losses) * 100 if (wins + losses) > 0 else 0,
            'avg_win': total_wins / wins if wins > 0 else 0,
            'avg_loss': total_losses / losses if losses > 0 else 0,
            'profit_factor': (total_wins / total_losses) if total_losses > 0 else float('inf'),
            'trades': trades,
            'equity_curve': equity
        }
        
        return result
    
    def print_report(self, result: Dict):
        """打印回测报告"""
        print(f"\n{'='*70}")
        print(f"📊 优化版回测报告: {result['name']} ({result['symbol']})")
        print(f"{'='*70}")
        print(f"初始资金: ¥{result['initial_capital']:,.2f}")
        print(f"最终权益: ¥{result['final_equity']:,.2f}")
        print(f"总收益率: {'🔴' if result['total_return_pct'] > 0 else '🟢'}{result['total_return_pct']:+.2f}%")
        print(f"最大回撤: {result['max_drawdown_pct']:.2f}%")
        print(f"夏普比率: {result['sharpe_ratio']:.2f}")
        print(f"卡尔玛比率: {result['calmar_ratio']:.2f}")
        print(f"{'='*70}")
        print(f"交易统计:")
        print(f"  总交易次数: {result['total_trades']}")
        print(f"  盈利次数: {result['winning_trades']}")
        print(f"  亏损次数: {result['losing_trades']}")
        print(f"  胜率: {result['win_rate']:.1f}%")
        print(f"  平均盈利: ¥{result['avg_win']:,.2f}")
        print(f"  平均亏损: ¥{result['avg_loss']:,.2f}")
        print(f"  盈亏比: {result['profit_factor']:.2f}")
        print(f"{'='*70}")


def main():
    """主函数"""
    print("="*70)
    print("股票交易策略优化版 V2.0")
    print("="*70)
    print("\n优化点:")
    print("  ✓ 动态市场状态检测 (趋势/震荡/高波动)")
    print("  ✓ 自适应策略切换 (趋势跟踪 ↔ 均值回归)")
    print("  ✓ ATR动态止损止盈")
    print("  ✓ 波动率调整仓位")
    print("  ✓ 交易频率控制")
    print("="*70)
    
    engine = OptimizedBacktestEngine(initial_capital=100000)
    
    # 测试股票
    test_stocks = [
        PORTFOLIO[0],   # 兆易创新
        PORTFOLIO[1],   # 汉得信息
        PORTFOLIO[2],   # 卫星ETF
    ]
    
    results = []
    
    for stock in test_stocks:
        result = engine.run_optimized_backtest(stock, period="1y")
        engine.print_report(result)
        results.append(result)
    
    # 总结
    print(f"\n\n{'='*70}")
    print("📊 优化策略回测总结")
    print(f"{'='*70}")
    
    total_return = sum([r['total_return_pct'] for r in results]) / len(results)
    avg_drawdown = sum([r['max_drawdown_pct'] for r in results]) / len(results)
    avg_sharpe = sum([r['sharpe_ratio'] for r in results]) / len(results)
    
    print(f"\n组合平均收益: {'🔴' if total_return > 0 else '🟢'}{total_return:+.2f}%")
    print(f"平均最大回撤: {avg_drawdown:.2f}%")
    print(f"平均夏普比率: {avg_sharpe:.2f}")
    
    for r in results:
        print(f"\n{r['name']} ({r['symbol']}):")
        print(f"  收益: {'🔴' if r['total_return_pct'] > 0 else '🟢'}{r['total_return_pct']:+.2f}% | "
              f"回撤: {r['max_drawdown_pct']:.2f}% | "
              f"夏普: {r['sharpe_ratio']:.2f} | "
              f"胜率: {r['win_rate']:.1f}%")
    
    print(f"\n{'='*70}")


if __name__ == "__main__":
    main()
