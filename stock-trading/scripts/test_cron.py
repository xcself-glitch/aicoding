#!/usr/bin/env python3
"""
Cron 定时任务测试和验证脚本
- 验证 cron 表达式是否正确
- 模拟任务触发时间
- 测试交易日判断
"""

import json
from datetime import datetime, timedelta
from croniter import croniter


def is_trading_day(date: datetime) -> bool:
    """判断是否为交易日（周一到周五）"""
    return date.weekday() < 5  # 0-4 是周一到周五


def get_next_trigger_times(cron_expr: str, tz: str = "Asia/Shanghai", count: int = 5) -> list:
    """获取未来 N 次触发时间"""
    try:
        iter = croniter(cron_expr, datetime.now())
        times = []
        for _ in range(count):
            next_time = iter.get_next(datetime)
            times.append(next_time)
        return times
    except Exception as e:
        return [f"Error: {e}"]


def test_cron_expression(name: str, expr: str, expected_desc: str):
    """测试单个 cron 表达式"""
    print(f"\n{'='*60}")
    print(f"📋 任务: {name}")
    print(f"🕐 Cron: {expr}")
    print(f"📝 说明: {expected_desc}")
    print(f"{'='*60}")
    
    next_times = get_next_trigger_times(expr, count=5)
    
    print("\n未来5次触发时间:")
    for i, t in enumerate(next_times, 1):
        if isinstance(t, str):
            print(f"  {i}. {t}")
        else:
            is_trade = is_trading_day(t)
            trade_mark = "✅ 交易日" if is_trade else "❌ 非交易日"
            print(f"  {i}. {t.strftime('%Y-%m-%d %H:%M:%S')} ({t.strftime('%A')}) {trade_mark}")


def test_all_jobs():
    """测试所有定时任务"""
    
    print("\n" + "="*60)
    print("🦞 OpenClaw 定时任务测试")
    print("="*60)
    print(f"\n当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"今天是: {datetime.now().strftime('%A')}")
    print(f"是否交易日: {'✅ 是' if is_trading_day(datetime.now()) else '❌ 否'}")
    
    # 任务列表
    jobs = [
        {
            "name": "strategy-daily-update",
            "expr": "25 9 * * 1-5",
            "desc": "每日早盘9:25更新买卖策略（仅工作日）"
        },
        {
            "name": "price-monitor-regular", 
            "expr": "*/5 9-11,13-14 * * 1-5",
            "desc": "普通股票5分钟监控（9-11点，13-14点，仅工作日）"
        },
        {
            "name": "price-monitor-key-am",
            "expr": "* 9-11 * * 1-5", 
            "desc": "重点股票1分钟监控（早盘9-11点，仅工作日）"
        },
        {
            "name": "price-monitor-key-pm",
            "expr": "* 13-14 * * 1-5",
            "desc": "重点股票1分钟监控（午盘13-14点，仅工作日）"
        },
        {
            "name": "daily-report",
            "expr": "5 15 * * 1-5",
            "desc": "收盘日报（15:05，仅工作日）"
        }
    ]
    
    for job in jobs:
        test_cron_expression(job["name"], job["expr"], job["desc"])
    
    # 交易日说明
    print("\n" + "="*60)
    print("📅 交易日说明")
    print("="*60)
    print("Cron 表达式中的 1-5 表示周一到周五（星期一到星期五）")
    print("0=周日, 1=周一, 2=周二, 3=周三, 4=周四, 5=周五, 6=周六")
    print("\n示例:")
    print("  * * * * 1-5  = 每分钟执行，但只在周一到周五")
    print("  0 9 * * 1-5  = 每天早上9点，但只在周一到周五")


def simulate_trading_week():
    """模拟一周的交易时间触发情况"""
    print("\n" + "="*60)
    print("📊 模拟一周交易时间触发情况")
    print("="*60)
    
    # 假设今天是某个交易日
    base_date = datetime(2026, 3, 16)  # 假设是周一
    
    for i in range(7):  # 一周7天
        date = base_date + timedelta(days=i)
        is_trade = is_trading_day(date)
        
        print(f"\n{date.strftime('%Y-%m-%d %A')}: {'✅ 交易日' if is_trade else '❌ 休息日'}")
        
        if is_trade:
            # 计算当天的触发次数
            # 重点股票: 9-11点(120分钟) + 13-14点(60分钟) = 180次
            # 普通股票: (2小时*60分钟/5) + (1小时*60分钟/5) = 24 + 12 = 36次
            print(f"  - 重点股票监控: 180次 (1分钟间隔)")
            print(f"  - 普通股票监控: 36次 (5分钟间隔)")


if __name__ == "__main__":
    try:
        from croniter import croniter
    except ImportError:
        print("Installing croniter...")
        import subprocess
        subprocess.run(["pip3", "install", "croniter", "-q"], check=True)
        from croniter import croniter
    
    test_all_jobs()
    simulate_trading_week()
    
    print("\n" + "="*60)
    print("✅ 测试完成！")
    print("="*60)
