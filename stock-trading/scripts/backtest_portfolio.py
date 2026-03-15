#!/usr/bin/env python3
"""
股票投资组合回测系统 V1.0
结合交易理论：均线策略、RSI、MACD、波动率过滤、Kelly仓位管理
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

# 尝试导入yfinance获取数据
try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False
    print("警告: yfinance未安装，将使用模拟数据")

# 导入持仓配置
sys.path.append(str(Path(__file__).parent.parent))
from config.my_portfolio import PORTFOLIO


class StockBacktestEngine:
    """股票回测引擎"""
    
    def __init__(self, initial_capital: float = 1000000.0):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.positions = {}  # 当前持仓
        self.trades = []     # 交易记录
        self.daily_returns = []  # 每日收益
        self.equity_curve = []   # 权益曲线
        
    def fetch_stock_data(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        """获取股票历史数据"""
        if not YF_AVAILABLE:
            return self._generate_mock_data(symbol)
        
        try:
            # A股代码转换
            if symbol.startswith('6'):
                ticker = f"{symbol}.SS"  # 上海
            elif symbol.startswith('0') or symbol.startswith('3'):
                ticker = f"{symbol}.SZ"  # 深圳
            else:
                ticker = symbol
            
            stock = yf.Ticker(ticker)
            df = stock.history(period=period)
            
            if df.empty:
                return self._generate_mock_data(symbol)
            
            return df
        except Exception as e:
            print(f"获取{symbol}数据失败: {e}")
            return self._generate_mock_data(symbol)
    
    def _generate_mock_data(self, symbol: str, days: int = 252) -> pd.DataFrame:
        """生成模拟数据用于测试"""
        np.random.seed(hash(symbol) % 1000)
        
        dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
        
        # 根据股票特征生成不同的模拟数据
        base_price = np.random.uniform(10, 100)
        volatility = np.random.uniform(0.01, 0.03)
        drift = np.random.uniform(-0.0002, 0.0005)
        
        returns = np.random.normal(drift, volatility, days)
        prices = base_price * np.exp(np.cumsum(returns))
        
        volume = np.random.randint(1000000, 10000000, days)
        
        df = pd.DataFrame({
            'Open': prices * (1 + np.random.normal(0, 0.001, days)),
            'High': prices * (1 + np.abs(np.random.normal(0, 0.01, days))),
            'Low': prices * (1 - np.abs(np.random.normal(0, 0.01, days))),
            'Close': prices,
            'Volume': volume
        }, index=dates)
        
        return df
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标"""
        df = df.copy()
        
        # 1. 均线系统 (MA)
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA10'] = df['Close'].rolling(window=10).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        
        # 2. RSI (相对强弱指标)
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # 3. MACD
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']
        
        # 4. 布林带 (Bollinger Bands)
        df['BB_Middle'] = df['Close'].rolling(window=20).mean()
        bb_std = df['Close'].rolling(window=20).std()
        df['BB_Upper'] = df['BB_Middle'] + (bb_std * 2)
        df['BB_Lower'] = df['BB_Middle'] - (bb_std * 2)
        df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / df['BB_Middle']
        
        # 5. ATR (平均真实波幅)
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['ATR'] = true_range.rolling(14).mean()
        df['ATR_Pct'] = df['ATR'] / df['Close'] * 100
        
        # 6. 成交量指标
        df['Volume_MA'] = df['Volume'].rolling(window=20).mean()
        df['Volume_Ratio'] = df['Volume'] / df['Volume_MA']
        
        # 7. 动量指标
        df['Momentum'] = df['Close'] / df['Close'].shift(10) - 1
        
        return df
    
    def generate_signals(self, df: pd.DataFrame, strategy_type: str = "combined") -> pd.DataFrame:
        """生成交易信号"""
        df = df.copy()
        df['Signal'] = 0
        df['Signal_Strength'] = 0
        
        if strategy_type == "ma_cross":
            # 均线金叉死叉策略
            df['Signal'] = np.where(
                (df['MA5'] > df['MA10']) & (df['MA5'].shift(1) <= df['MA10'].shift(1)), 1,
                np.where((df['MA5'] < df['MA10']) & (df['MA5'].shift(1) >= df['MA10'].shift(1)), -1, 0)
            )
            
        elif strategy_type == "rsi":
            # RSI超买超卖策略
            df['Signal'] = np.where(
                (df['RSI'] < 30) & (df['RSI'].shift(1) >= 30), 1,
                np.where((df['RSI'] > 70) & (df['RSI'].shift(1) <= 70), -1, 0)
            )
            
        elif strategy_type == "macd":
            # MACD策略
            df['Signal'] = np.where(
                (df['MACD'] > df['MACD_Signal']) & (df['MACD'].shift(1) <= df['MACD_Signal'].shift(1)), 1,
                np.where((df['MACD'] < df['MACD_Signal']) & (df['MACD'].shift(1) >= df['MACD_Signal'].shift(1)), -1, 0)
            )
            
        elif strategy_type == "bollinger":
            # 布林带均值回归策略
            df['Signal'] = np.where(
                (df['Close'] < df['BB_Lower']) & (df['Close'].shift(1) >= df['BB_Lower'].shift(1)), 1,
                np.where((df['Close'] > df['BB_Upper']) & (df['Close'].shift(1) <= df['BB_Upper'].shift(1)), -1, 0)
            )
            
        elif strategy_type == "combined":
            # 多因子综合策略 (推荐)
            buy_score = 0
            sell_score = 0
            
            # 均线多头 (MA5 > MA10 > MA20)
            buy_score += np.where((df['MA5'] > df['MA10']) & (df['MA10'] > df['MA20']), 1, 0)
            sell_score += np.where((df['MA5'] < df['MA10']) & (df['MA10'] < df['MA20']), 1, 0)
            
            # RSI not overbought/oversold
            buy_score += np.where(df['RSI'] < 65, 1, 0)
            sell_score += np.where(df['RSI'] > 35, 1, 0)
            
            # MACD bullish/bearish
            buy_score += np.where(df['MACD'] > df['MACD_Signal'], 1, 0)
            sell_score += np.where(df['MACD'] < df['MACD_Signal'], 1, 0)
            
            # 成交量确认
            buy_score += np.where(df['Volume_Ratio'] > 1.2, 1, 0)
            sell_score += np.where(df['Volume_Ratio'] > 1.2, 1, 0)
            
            # 低波动率环境更可靠
            buy_score += np.where(df['ATR_Pct'] < 3, 1, 0)
            sell_score += np.where(df['ATR_Pct'] < 3, 1, 0)
            
            df['Signal_Strength'] = buy_score - sell_score
            df['Signal'] = np.where(buy_score >= 4, 1, np.where(sell_score >= 4, -1, 0))
        
        return df
    
    def kelly_position_size(self, win_rate: float, avg_win: float, avg_loss: float) -> float:
        """Kelly公式计算最优仓位比例"""
        if avg_loss == 0:
            return 0.1  # 默认10%
        
        b = avg_win / avg_loss  # 盈亏比
        p = win_rate
        q = 1 - p
        
        kelly = (b * p - q) / b
        return max(0.05, min(0.5, kelly))  # 限制在5%-50%
    
    def run_backtest(self, stock_config: Dict, strategy: str = "combined", 
                     period: str = "1y") -> Dict:
        """运行单只股票回测"""
        symbol = stock_config['code']
        name = stock_config['name']
        
        print(f"\n{'='*70}")
        print(f"回测股票: {name} ({symbol})")
        print(f"策略: {strategy}")
        print(f"{'='*70}")
        
        # 获取数据
        df = self.fetch_stock_data(symbol, period)
        df = self.calculate_indicators(df)
        df = self.generate_signals(df, strategy)
        
        # 回测参数
        initial_cash = self.initial_capital
        cash = initial_cash
        position = 0
        position_size = 0
        trades = []
        equity = []
        
        # 交易统计
        wins = 0
        losses = 0
        total_wins = 0
        total_losses = 0
        
        for i in range(60, len(df)):  # 从第60天开始（指标计算需要历史数据）
            date = df.index[i]
            price = df['Close'].iloc[i]
            signal = df['Signal'].iloc[i]
            
            # 计算当前权益
            current_equity = cash + position * price
            equity.append({'date': date, 'equity': current_equity})
            
            # 买入信号
            if signal == 1 and position == 0:
                # 计算仓位大小
                win_rate = wins / (wins + losses) if (wins + losses) > 0 else 0.5
                avg_win = total_wins / wins if wins > 0 else price * 0.05
                avg_loss = total_losses / losses if losses > 0 else price * 0.03
                
                position_pct = self.kelly_position_size(win_rate, avg_win, avg_loss)
                position_size = (current_equity * position_pct) / price
                
                cost = position_size * price
                if cost <= cash:
                    position = position_size
                    cash -= cost
                    entry_price = price
                    
                    trades.append({
                        'date': date,
                        'type': 'BUY',
                        'price': price,
                        'shares': position_size,
                        'value': cost
                    })
                    print(f"📈 买入 [{date.strftime('%Y-%m-%d')}] {name} @ ¥{price:.2f} x {position_size:.0f}股")
            
            # 卖出信号
            elif signal == -1 and position > 0:
                sell_value = position * price
                profit = sell_value - (position * entry_price)
                
                if profit > 0:
                    wins += 1
                    total_wins += profit
                else:
                    losses += 1
                    total_losses += abs(profit)
                
                cash += sell_value
                
                trades.append({
                    'date': date,
                    'type': 'SELL',
                    'price': price,
                    'shares': position,
                    'value': sell_value,
                    'profit': profit,
                    'return_pct': profit / (position * entry_price) * 100
                })
                
                print(f"📉 卖出 [{date.strftime('%Y-%m-%d')}] {name} @ ¥{price:.2f} | 盈亏: {'🔴' if profit > 0 else '🟢'}¥{profit:,.2f} ({profit/(position*entry_price)*100:+.2f}%)")
                
                position = 0
        
        # 计算最终收益
        final_price = df['Close'].iloc[-1]
        final_equity = cash + position * final_price
        total_return = (final_equity - initial_cash) / initial_cash * 100
        
        # 计算最大回撤
        equity_df = pd.DataFrame(equity)
        if not equity_df.empty:
            equity_df['cummax'] = equity_df['equity'].cummax()
            equity_df['drawdown'] = (equity_df['equity'] - equity_df['cummax']) / equity_df['cummax'] * 100
            max_drawdown = equity_df['drawdown'].min()
        else:
            max_drawdown = 0
        
        # 计算夏普比率 (假设无风险利率3%)
        if len(equity) > 1:
            returns = pd.Series([e['equity'] for e in equity]).pct_change().dropna()
            sharpe = (returns.mean() * 252 - 0.03) / (returns.std() * np.sqrt(252)) if returns.std() > 0 else 0
        else:
            sharpe = 0
        
        result = {
            'symbol': symbol,
            'name': name,
            'strategy': strategy,
            'initial_capital': initial_cash,
            'final_equity': final_equity,
            'total_return_pct': total_return,
            'max_drawdown_pct': max_drawdown,
            'sharpe_ratio': sharpe,
            'total_trades': len(trades),
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
        print(f"📊 回测报告: {result['name']} ({result['symbol']})")
        print(f"{'='*70}")
        print(f"策略类型: {result['strategy']}")
        print(f"初始资金: ¥{result['initial_capital']:,.2f}")
        print(f"最终权益: ¥{result['final_equity']:,.2f}")
        print(f"总收益率: {'🔴' if result['total_return_pct'] > 0 else '🟢'}{result['total_return_pct']:+.2f}%")
        print(f"最大回撤: {result['max_drawdown_pct']:.2f}%")
        print(f"夏普比率: {result['sharpe_ratio']:.2f}")
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
    print("股票投资组合回测系统 V1.0")
    print("交易策略: 多因子综合策略 + Kelly仓位管理")
    print("="*70)
    
    # 创建回测引擎
    engine = StockBacktestEngine(initial_capital=100000)
    
    # 选择要回测的股票（选择几只代表性的）
    test_stocks = [
        PORTFOLIO[0],   # 兆易创新
        PORTFOLIO[1],   # 汉得信息
        PORTFOLIO[2],   # 卫星ETF
        PORTFOLIO[7],   # 蓝色光标
    ]
    
    results = []
    
    # 测试不同策略
    strategies = ["combined", "ma_cross", "rsi", "macd", "bollinger"]
    
    for stock in test_stocks:
        print(f"\n\n🎯 回测股票: {stock['name']} ({stock['code']})")
        print("-" * 70)
        
        stock_results = {}
        for strategy in strategies:
            result = engine.run_backtest(stock, strategy=strategy, period="1y")
            stock_results[strategy] = result
            engine.print_report(result)
        
        results.append(stock_results)
        
        # 找出最佳策略
        best_strategy = max(stock_results.items(), key=lambda x: x[1]['total_return_pct'])
        print(f"\n🏆 {stock['name']} 最佳策略: {best_strategy[0]} (收益: {best_strategy[1]['total_return_pct']:+.2f}%)")
    
    # 总结报告
    print(f"\n\n{'='*70}")
    print("📊 投资组合回测总结")
    print(f"{'='*70}")
    
    for stock_results in results:
        for symbol, result in list(stock_results.items())[:1]:  # 只显示combined策略
            print(f"\n{result['name']} ({result['symbol']}):")
            print(f"  综合策略收益: {'🔴' if result['total_return_pct'] > 0 else '🟢'}{result['total_return_pct']:+.2f}%")
            print(f"  最大回撤: {result['max_drawdown_pct']:.2f}%")
            print(f"  胜率: {result['win_rate']:.1f}%")
    
    print(f"\n{'='*70}")


if __name__ == "__main__":
    main()
