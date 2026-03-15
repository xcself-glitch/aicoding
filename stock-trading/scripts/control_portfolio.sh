#!/bin/bash
# 持仓股池监控控制脚本

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$HOME/.stock_monitor"
PID_FILE="$LOG_DIR/portfolio_monitor.pid"
PYTHON_SCRIPT="$SCRIPT_DIR/monitor_portfolio.py"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

case "$1" in
    start)
        if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
            echo -e "${YELLOW}⚠️  监控进程已在运行 (PID: $(cat $PID_FILE))${NC}"
            exit 1
        fi
        
        echo -e "${GREEN}🚀 启动持仓股池监控后台进程...${NC}"
        mkdir -p "$LOG_DIR"
        
        # 创建监控循环脚本
        echo "#!/bin/bash
PYTHON=\"$PYTHON_SCRIPT\"
LOG_DIR=\"$LOG_DIR\"

while true; do
    HOUR=\$(TZ=Asia/Shanghai date +%H)
    MINUTE=\$(TZ=Asia/Shanghai date +%M)
    TIME_VAL=\$((HOUR * 100 + MINUTE))
    WEEKDAY=\$(TZ=Asia/Shanghai date +%w)
    
    # 交易时间判断
    if [ \"\$WEEKDAY\" -ge 1 ] && [ \"\$WEEKDAY\" -le 5 ]; then
        if { [ \"\$TIME_VAL\" -ge 930 ] && [ \"\$TIME_VAL\" -le 1130 ]; } || { [ \"\$TIME_VAL\" -ge 1300 ] && [ \"\$TIME_VAL\" -le 1500 ]; }; then
            # 交易时间：每10分钟检查一次
            echo \"[\$(date '+%Y-%m-%d %H:%M:%S')] 交易时间检查...\" >> \"\$LOG_DIR/portfolio.log\"
            python3 \"\$PYTHON\" >> \"\$LOG_DIR/portfolio.log\" 2>&1
            sleep 600
        elif [ \"\$TIME_VAL\" -gt 1130 ] && [ \"\$TIME_VAL\" -lt 1300 ]; then
            # 午休
            python3 \"\$PYTHON\" >> \"\$LOG_DIR/portfolio.log\" 2>&1
            sleep 900
        elif [ \"\$TIME_VAL\" -gt 1500 ] && [ \"\$TIME_VAL\" -le 2359 ]; then
            # 收盘后
            python3 \"\$PYTHON\" >> \"\$LOG_DIR/portfolio.log\" 2>&1
            sleep 3600
        else
            python3 \"\$PYTHON\" >> \"\$LOG_DIR/portfolio.log\" 2>&1
            sleep 3600
        fi
    else
        python3 \"\$PYTHON\" >> \"\$LOG_DIR/portfolio.log\" 2>&1
        sleep 3600
    fi
done" > "$LOG_DIR/portfolio_loop.sh"
        
        chmod +x "$LOG_DIR/portfolio_loop.sh"
        
        # 启动后台进程
        nohup bash "$LOG_DIR/portfolio_loop.sh" > "$LOG_DIR/portfolio_daemon.log" 2>&1 &
        echo $! > "$PID_FILE"
        
        echo -e "${GREEN}✅ 已启动 (PID: $!)${NC}"
        echo -e "📋 日志: $LOG_DIR/portfolio.log"
        echo ""
        echo -e "📊 监控股池: 11只股票"
        echo "  • 交易时间: 每10分钟扫描一次"
        echo "  • 预警规则: 成本±10-15%、日内涨跌±5%、买卖点提醒"
        ;;
        
    stop)
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            if kill -0 "$PID" 2>/dev/null; then
                echo -e "${YELLOW}🛑 停止监控进程 (PID: $PID)...${NC}"
                kill "$PID" 2>/dev/null
                pkill -f "portfolio_loop.sh" 2>/dev/null
                rm -f "$PID_FILE"
                echo -e "${GREEN}✅ 已停止${NC}"
            else
                echo -e "${YELLOW}⚠️  进程不存在${NC}"
                rm -f "$PID_FILE"
            fi
        else
            echo -e "${YELLOW}⚠️  没有运行中的进程${NC}"
        fi
        ;;
        
    status)
        if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
            echo -e "${GREEN}✅ 持仓监控运行中 (PID: $(cat $PID_FILE))${NC}"
            echo ""
            echo "📊 最近检查记录:"
            tail -20 "$LOG_DIR/portfolio.log" 2>/dev/null | grep -E "(时间:|总盈亏|预警汇总)" | tail -6 || echo "  暂无最新记录"
        else
            echo -e "${RED}⏹️  监控未运行${NC}"
        fi
        ;;
        
    log)
        if [ -f "$LOG_DIR/portfolio.log" ]; then
            tail -f "$LOG_DIR/portfolio.log"
        else
            echo -e "${YELLOW}暂无日志文件${NC}"
        fi
        ;;
        
    check)
        echo -e "${BLUE}🔍 执行即时全仓检查...${NC}"
        echo ""
        python3 "$PYTHON_SCRIPT"
        ;;
        
    summary)
        echo -e "${BLUE}📊 生成持仓汇总...${NC}"
        echo ""
        if [ -f "$LOG_DIR/portfolio.log" ]; then
            # 提取最后一次完整的报告
            tac "$LOG_DIR/portfolio.log" | grep -A 50 "持仓监控报告" | head -50 | tac
        else
            python3 "$PYTHON_SCRIPT"
        fi
        ;;
        
    *)
        echo "持仓股池监控控制脚本"
        echo ""
        echo "用法: ./control_portfolio.sh [start|stop|status|log|check|summary]"
        echo ""
        echo "  start   - 启动后台监控"
        echo "  stop    - 停止监控"
        echo "  status  - 查看运行状态"
        echo "  log     - 查看实时日志"
        echo "  check   - 执行一次即时检查"
        echo "  summary - 显示最新持仓汇总"
        ;;
esac
