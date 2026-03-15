#!/usr/bin/env python3
"""
ETHUSDT永续合约交易机器人主程序
- 实时监控价格
- 多指标信号生成
- 飞书通知
"""

import sys
import os
import time
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from strategies.binance_client import BinanceFuturesClient, klines_to_arrays
from strategies.signal_generator import SignalGenerator, TradingSignal, SignalType
from strategies.indicators import TechnicalIndicators
from config.strategy_config import CONFIG


class TradingEngine:
    """交易引擎"""
    
    def __init__(self):
        self.client = BinanceFuturesClient()
        self.signal_generator = SignalGenerator()
        self.current_position = None  # "long", "short", None
        self.position_entry_price = 0
        self.position_size = 0
        self.trade_history = []
        self.daily_stats = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'trades': 0,
            'profit': 0.0,
            'wins': 0,
            'losses': 0
        }
        
        # 飞书通知配置
        self.feishu_webhook = os.getenv('FEISHU_WEBHOOK', '')
    
    def send_feishu_notification(self, title: str, content: str, urgent: bool = False):
        """发送飞书通知"""
        try:
            # 尝试导入飞书通知模块
            notify_path = Path(__file__).parent.parent.parent / "stock-monitor-pro" / "scripts"
            if notify_path.exists():
                sys.path.insert(0, str(notify_path))
                from notify_feishu import send_stock_alert
                
                if urgent:
                    title = f"🚨 {title}"
                
                return send_stock_alert(title, content)
            else:
                # 备用：使用系统通知
                print(f"📱 通知: {title}")
                print(content)
                return True
        except Exception as e:
            print(f"⚠️ 通知发送失败: {e}")
            return False
    
    def check_position_exit(self, current_price: float) -> Optional[str]:
        """
        检查是否需要平仓
        
        Returns:
            平仓原因或None
        """
        if not self.current_position or self.position_entry_price == 0:
            return None
        
        # 计算盈亏
        if self.current_position == "long":
            pnl_pct = (current_price - self.position_entry_price) / self.position_entry_price
        else:  # short
            pnl_pct = (self.position_entry_price - current_price) / self.position_entry_price
        
        # 检查止损
        if pnl_pct <= -CONFIG.risk.stop_loss_pct:
            return f"止损触发 (亏损 {pnl_pct*100:.2f}%)"
        
        # 检查移动止盈
        if pnl_pct >= CONFIG.risk.trailing_stop_pct * 2:
            # 已实现2倍移动止损距离，开启移动止盈
            # 简化处理：盈利超过2%后，回撤0.5%止盈
            return None  # 实际需要追踪最高价
        
        return None
    
    def execute_signal(self, signal: TradingSignal):
        """执行交易信号"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        # 信号类型emoji
        emoji_map = {
            SignalType.LONG: "🟢",
            SignalType.SHORT: "🔴",
            SignalType.CLOSE_LONG: "📗",
            SignalType.CLOSE_SHORT: "📕",
            SignalType.HOLD: "⏸️"
        }
        emoji = emoji_map.get(signal.type, "⚪")
        
        print(f"\n{'='*60}")
        print(f"{emoji} 交易信号 [{timestamp}]")
        print(f"{'='*60}")
        print(f"类型: {signal.type.value}")
        print(f"强度: {signal.strength:.0f}/100")
        print(f"价格: {signal.price:.2f} USDT")
        print(f"理由: {signal.reason}")
        
        if signal.position_size > 0:
            print(f"建议仓位: {signal.position_size:.4f} ETH")
        
        # 处理持仓
        if signal.type == SignalType.LONG:
            if self.current_position == "short":
                # 平空开多
                self._close_position("反手平空", signal.price)
                self._open_position("long", signal)
            elif self.current_position is None:
                self._open_position("long", signal)
            
        elif signal.type == SignalType.SHORT:
            if self.current_position == "long":
                # 平多开空
                self._close_position("反手平多", signal.price)
                self._open_position("short", signal)
            elif self.current_position is None:
                self._open_position("short", signal)
            
        elif signal.type == SignalType.CLOSE_LONG:
            if self.current_position == "long":
                self._close_position("信号平多", signal.price)
            
        elif signal.type == SignalType.CLOSE_SHORT:
            if self.current_position == "short":
                self._close_position("信号平空", signal.price)
        
        else:
            print(f"💡 维持观望")
        
        # 发送通知（重要信号）
        if signal.type in [SignalType.LONG, SignalType.SHORT] and signal.strength >= 80:
            self._send_signal_notification(signal)
    
    def _open_position(self, position_type: str, signal: TradingSignal):
        """开仓"""
        self.current_position = position_type
        self.position_entry_price = signal.price
        self.position_size = signal.position_size
        
        print(f"\n✅ 开仓 [{position_type.upper()}]")
        print(f"   价格: {signal.price:.2f}")
        print(f"   数量: {signal.position_size:.4f} ETH")
        print(f"   杠杆: {CONFIG.leverage.leverage}x")
        
        if signal.targets:
            print(f"   止盈: {signal.targets.get('take_profit', 0):.2f}")
            print(f"   止损: {signal.targets.get('stop_loss', 0):.2f}")
            print(f"   目标收益: {signal.targets.get('leveraged_return', 0)*100:.1f}%")
    
    def _close_position(self, reason: str, exit_price: float):
        """平仓"""
        if not self.current_position:
            return
        
        # 计算盈亏
        if self.current_position == "long":
            pnl_pct = (exit_price - self.position_entry_price) / self.position_entry_price
        else:
            pnl_pct = (self.position_entry_price - exit_price) / self.position_entry_price
        
        leveraged_pnl = pnl_pct * CONFIG.leverage.leverage
        
        print(f"\n📕 平仓 [{reason}]")
        print(f"   方向: {self.current_position}")
        print(f"   入场: {self.position_entry_price:.2f}")
        print(f"   出场: {exit_price:.2f}")
        print(f"   盈亏: {pnl_pct*100:+.2f}% (杠杆后: {leveraged_pnl*100:+.2f}%)")
        
        # 记录交易
        self.trade_history.append({
            'time': datetime.now().isoformat(),
            'type': self.current_position,
            'entry': self.position_entry_price,
            'exit': exit_price,
            'pnl': pnl_pct,
            'leveraged_pnl': leveraged_pnl,
            'reason': reason
        })
        
        # 更新统计
        self.daily_stats['trades'] += 1
        self.daily_stats['profit'] += leveraged_pnl
        if leveraged_pnl > 0:
            self.daily_stats['wins'] += 1
        else:
            self.daily_stats['losses'] += 1
        
        # 重置持仓
        self.current_position = None
        self.position_entry_price = 0
        self.position_size = 0
    
    def _send_signal_notification(self, signal: TradingSignal):
        """发送信号通知"""
        direction = "做多" if signal.type == SignalType.LONG else "做空"
        
        content = f"""**ETHUSDT 交易信号**

💡 **方向**: {direction}
📊 **信号强度**: {signal.strength:.0f}/100
💰 **建议价格**: {signal.price:.2f} USDT
📦 **建议仓位**: {signal.position_size:.4f} ETH ({CONFIG.leverage.leverage}x杠杆)

**信号理由**:
{signal.reason}

**目标设置**:
"""
        if signal.targets:
            content += f"🎯 止盈: {signal.targets.get('take_profit', 0):.2f}\n"
            content += f"🛑 止损: {signal.targets.get('stop_loss', 0):.2f}\n"
            content += f"📈 目标收益: {signal.targets.get('leveraged_return', 0)*100:.1f}%\n"
        
        content += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        self.send_feishu_notification(
            f"ETHUSDT {direction}信号",
            content,
            urgent=signal.strength >= 85
        )
    
    def run_cycle(self):
        """运行一个交易周期"""
        try:
            # 获取数据
            print(f"\n{'='*60}")
            print(f"📊 ETHUSDT 交易扫描 [{datetime.now().strftime('%H:%M:%S')}]")
            print(f"{'='*60}")
            
            data = self.client.get_realtime_data_for_strategy("ETHUSDT")
            if not data:
                print("❌ 无法获取数据，跳过本次扫描")
                return
            
            klines = data['klines_15m']
            ticker = data['ticker_24h']
            current_price = data['current_price']
            
            # 更新日内数据
            self.signal_generator.daily_high = ticker.high_price
            self.signal_generator.daily_low = ticker.low_price
            self.signal_generator.daily_open = ticker.open_price
            
            # 检查持仓平仓条件
            exit_reason = self.check_position_exit(current_price)
            if exit_reason:
                self._close_position(exit_reason, current_price)
            
            # 转换K线为数组
            opens, highs, lows, closes, volumes = klines_to_arrays(klines)
            
            # 生成信号
            signal = self.signal_generator.generate_signal(
                opens, highs, lows, closes, volumes,
                current_position=self.current_position
            )
            
            # 执行信号
            self.execute_signal(signal)
            
            # 显示当前状态
            self._print_status(current_price, ticker)
            
        except Exception as e:
            print(f"❌ 交易周期异常: {e}")
            import traceback
            traceback.print_exc()
    
    def _print_status(self, current_price: float, ticker):
        """打印当前状态"""
        print(f"\n📈 当前状态:")
        print(f"   价格: {current_price:.2f} USDT")
        print(f"   24h: {ticker.price_change_percent:+.2f}%")
        print(f"   区间: {ticker.low_price:.2f} - {ticker.high_price:.2f}")
        
        if self.current_position:
            if self.current_position == "long":
                pnl = (current_price - self.position_entry_price) / self.position_entry_price
            else:
                pnl = (self.position_entry_price - current_price) / self.position_entry_price
            leveraged_pnl = pnl * CONFIG.leverage.leverage
            
            emoji = "🟢" if leveraged_pnl > 0 else "🔴"
            print(f"   持仓: {self.current_position.upper()} | "
                  f"入场:{self.position_entry_price:.2f} | "
                  f"盈亏:{emoji} {leveraged_pnl*100:+.2f}%")
        else:
            print(f"   持仓: 空仓")
        
        print(f"\n📊 今日统计:")
        print(f"   交易次数: {self.daily_stats['trades']}")
        print(f"   累计盈亏: {self.daily_stats['profit']*100:+.2f}%")
        print(f"   胜率: {self.daily_stats['wins']}/{self.daily_stats['trades']} "
              f"({self.daily_stats['wins']/max(self.daily_stats['trades'],1)*100:.0f}%)")
    
    def run_backtest(self, days: int = 7):
        """
        运行回测
        
        Args:
            days: 回测天数
        """
        print(f"\n{'='*60}")
        print(f"📊 ETHUSDT 策略回测 ({days}天)")
        print(f"{'='*60}")
        
        # 获取历史数据
        end_time = int(datetime.now().timestamp() * 1000)
        start_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
        
        print(f"\n获取历史数据...")
        klines = self.client.get_klines(
            "ETHUSDT", "15m", limit=1000,
            start_time=start_time, end_time=end_time
        )
        
        if not klines:
            print("❌ 无法获取历史数据")
            return
        
        print(f"✅ 获取 {len(klines)} 条15分钟K线")
        
        # 模拟交易
        opens, highs, lows, closes, volumes = klines_to_arrays(klines)
        
        # 分批处理（滑动窗口）
        window_size = 100
        signals_generated = []
        
        for i in range(window_size, len(klines)):
            # 获取窗口数据
            w_opens = opens[i-window_size:i]
            w_highs = highs[i-window_size:i]
            w_lows = lows[i-window_size:i]
            w_closes = closes[i-window_size:i]
            w_volumes = volumes[i-window_size:i]
            
            # 更新日内数据
            day_high = max(w_highs[-20:])  # 最近20根K线的高低点
            day_low = min(w_lows[-20:])
            self.signal_generator.daily_high = day_high
            self.signal_generator.daily_low = day_low
            
            # 生成信号
            signal = self.signal_generator.generate_signal(
                w_opens, w_highs, w_lows, w_closes, w_volumes,
                current_position=self.current_position
            )
            
            if signal.type not in [SignalType.HOLD]:
                signals_generated.append({
                    'time': klines[i].open_time.strftime('%m-%d %H:%M'),
                    'type': signal.type.value,
                    'price': signal.price,
                    'strength': signal.strength,
                    'reason': signal.reason[:50]
                })
        
        print(f"\n✅ 回测完成")
        print(f"   生成信号: {len(signals_generated)} 个")
        
        # 显示部分信号
        if signals_generated:
            print(f"\n最近10个信号:")
            for sig in signals_generated[-10:]:
                emoji = "🟢" if "多" in sig['type'] else "🔴" if "空" in sig['type'] else "⚪"
                print(f"   {emoji} {sig['time']} | {sig['type']} | "
                      f"价格:{sig['price']:.2f} | 强度:{sig['strength']:.0f}")
    
    def run_continuous(self, interval_seconds: int = 60):
        """
        持续运行
        
        Args:
            interval_seconds: 扫描间隔（秒）
        """
        print(f"\n{'='*60}")
        print(f"🚀 ETHUSDT 交易机器人启动")
        print(f"{'='*60}")
        print(f"策略: 10倍杠杆日内反转")
        print(f"周期: 15分钟K线")
        print(f"扫描间隔: {interval_seconds}秒")
        print(f"{'='*60}")
        
        try:
            while True:
                self.run_cycle()
                
                print(f"\n💤 等待 {interval_seconds} 秒后下一次扫描...")
                time.sleep(interval_seconds)
                
        except KeyboardInterrupt:
            print(f"\n\n⏹️  交易机器人已停止")
            self._print_summary()
    
    def _print_summary(self):
        """打印交易总结"""
        print(f"\n{'='*60}")
        print(f"📊 交易总结")
        print(f"{'='*60}")
        print(f"今日交易: {self.daily_stats['trades']} 笔")
        print(f"累计盈亏: {self.daily_stats['profit']*100:+.2f}%")
        print(f"胜/负: {self.daily_stats['wins']}/{self.daily_stats['losses']}")
        
        if self.trade_history:
            print(f"\n交易明细:")
            for trade in self.trade_history[-5:]:
                emoji = "🟢" if trade['leveraged_pnl'] > 0 else "🔴"
                print(f"   {emoji} {trade['type']} | "
                      f"{trade['leveraged_pnl']*100:+.2f}% | {trade['reason']}")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='ETHUSDT永续合约交易机器人')
    parser.add_argument('--backtest', type=int, metavar='DAYS',
                       help='运行回测（指定天数）')
    parser.add_argument('--interval', type=int, default=300,
                       help='扫描间隔（秒），默认300（5分钟）')
    parser.add_argument('--once', action='store_true',
                       help='只运行一次扫描')
    
    args = parser.parse_args()
    
    engine = TradingEngine()
    
    if args.backtest:
        engine.run_backtest(args.backtest)
    elif args.once:
        engine.run_cycle()
    else:
        engine.run_continuous(args.interval)


if __name__ == "__main__":
    main()
