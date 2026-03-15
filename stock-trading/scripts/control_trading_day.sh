#!/bin/bash
# 交易日全流程监控控制脚本
# 时间节奏：
#   8:30  - 盘前简报
#   9:15  - 开盘建议
#   9:30-11:30 - 盘中监控（每10分钟）
#   13:00-15:00 - 盘中监控（每10分钟）
#   15:30 - 收盘复盘

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$HOME/.stock_monitor"
PID_FILE="$LOG_DIR/trading_day.pid"
PYTHON_SCRIPT="$SCRIPT_DIR/portfolio_trading_day.py"
INTRADAY_SCRIPT="$SCRIPT_DIR/monitor_portfolio.py"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 创建日志目录
mkdir -p "$LOG_DIR"

# 交易日判断函数
is_trading_day() {
    local weekday=$(TZ=Asia/Shanghai date +%w)
    # 1-5 是周一到周五
    if [ "$weekday" -ge 1 ] && [ "$weekday" -le 5 ]; then
        return 0
    else
        return 1
    fi
}

# 获取当前时间 HHMM 格式
get_time_val() {
    TZ=Asia/Shanghai date +%H%M
}

case "$1" in
    start)
        if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
            echo -e "${YELLOW}⚠️  交易日监控已在运行 (PID: $(cat $PID_FILE))${NC}"
            exit 1
        fi
        
        if ! is_trading_day; then
            echo -e "${YELLOW}⚠️  今天是周末，是否继续启动？(y/N)${NC}"
            read -t 5 -n 1 answer || answer="N"
            echo
            if [ "$answer" != "y" ] && [ "$answer" != "Y" ]; then
                echo "已取消启动"
                exit 1
            fi
        fi
        
        echo -e "${GREEN}🚀 启动交易日全流程监控...${NC}"
        
        # 创建监控循环脚本
        cat > "$LOG_DIR/trading_loop.sh" << 'LOOPSCRIPT'
#!/bin/bash
SCRIPT_DIR="REPLACE_SCRIPT_DIR"
LOG_DIR="REPLACE_LOG_DIR"
PYTHON_SCRIPT="$SCRIPT_DIR/portfolio_trading_day.py"
INTRADAY_SCRIPT="$SCRIPT_DIR/monitor_portfolio.py"

# 记录今日已执行的标记文件
touch "$LOG_DIR/today_$(TZ=Asia/Shanghai date +%Y%m%d).lock"

# 今日已执行标记
PRE_MARKET_DONE=0
OPEN_DONE=0
CLOSE_DONE=0

log_msg() {
    echo "[$(TZ=Asia/Shanghai date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_DIR/trading.log"
    echo "$1"
}

while true; do
    TIME_VAL=$(TZ=Asia/Shanghai date +%H%M)
    WEEKDAY=$(TZ=Asia/Shanghai date +%w)
    
    # 周末只记录日志
    if [ "$WEEKDAY" -eq 0 ] || [ "$WEEKDAY" -eq 6 ]; then
        log_msg "今天是周末，监控休眠中..."
        sleep 3600
        continue
    fi
    
    # 盘前简报 8:30
    if [ "$TIME_VAL" -ge 830 ] && [ "$TIME_VAL" -lt 900 ] && [ $PRE_MARKET_DONE -eq 0 ]; then
        log_msg "=" 
        log_msg "🌅 生成盘前简报..."
        echo "" >> "$LOG_DIR/trading.log"
        python3 "$PYTHON_SCRIPT" pre_market >> "$LOG_DIR/trading.log" 2>&1
        PRE_MARKET_DONE=1
        log_msg "盘前简报完成"
        sleep 60
        continue
    fi
    
    # 开盘建议 9:15-9:25
    if [ "$TIME_VAL" -ge 915 ] && [ "$TIME_VAL" -lt 925 ] && [ $OPEN_DONE -eq 0 ]; then
        log_msg "=" 
        log_msg "📈 生成开盘建议..."
        echo "" >> "$LOG_DIR/trading.log"
        python3 "$PYTHON_SCRIPT" open >> "$LOG_DIR/trading.log" 2>&1
        OPEN_DONE=1
        log_msg "开盘建议完成"
        sleep 60
        continue
    fi
    
    # 午休时间 11:31-12:59 (A股不开盘)
    if [ "$TIME_VAL" -gt 1130 ] && [ "$TIME_VAL" -lt 1300 ]; then
        if [ "$TIME_VAL" -eq 1131 ]; then
            log_msg "⏸️ 午休时间，暂停监控 (11:30-13:00)..."
        fi
        sleep 60
        continue
    fi
    
    # 盘中监控 9:30-11:30, 13:00-15:00 (A股交易时间)
    if { [ "$TIME_VAL" -ge 930 ] && [ "$TIME_VAL" -le 1130 ]; } || { [ "$TIME_VAL" -ge 1300 ] && [ "$TIME_VAL" -le 1500 ]; }; then
        log_msg "🔍 盘中检查..."
        echo "" >> "$LOG_DIR/trading.log"
        python3 "$INTRADAY_SCRIPT" >> "$LOG_DIR/trading.log" 2>&1
        
        # 检查是否有重大预警（退出码>0表示有预警）
        if [ $? -gt 0 ]; then
            log_msg "⚠️  发现预警，请查看日志"
        fi
        
        # 交易时间每10分钟检查一次
        sleep 600
        continue
    fi
    
    # 收盘复盘 15:30
    if [ "$TIME_VAL" -ge 1530 ] && [ "$TIME_VAL" -lt 1600 ] && [ $CLOSE_DONE -eq 0 ]; then
        log_msg "=" 
        log_msg "🌙 生成收盘复盘..."
        echo "" >> "$LOG_DIR/trading.log"
        python3 "$PYTHON_SCRIPT" close >> "$LOG_DIR/trading.log" 2>&1
        CLOSE_DONE=1
        log_msg "收盘复盘完成"
        log_msg "今日监控结束，等待下个交易日..."
        sleep 3600
        continue
    fi
    
    # 收盘后到次日开盘前
    if [ "$TIME_VAL" -ge 1600 ] || [ "$TIME_VAL" -lt 830 ]; then
        if [ "$TIME_VAL" -eq 1600 ] || [ "$TIME_VAL" -eq 0 ]; then
            # 重置标记（新的一天）
            PRE_MARKET_DONE=0
            OPEN_DONE=0
            CLOSE_DONE=0
        fi
        sleep 300  # 5分钟检查一次时间
        continue
    fi
    
    # 默认休眠
    sleep 30
done
LOOPSCRIPT
        
        # 替换变量
        sed -i "s|REPLACE_SCRIPT_DIR|$SCRIPT_DIR|g" "$LOG_DIR/trading_loop.sh"
        sed -i "s|REPLACE_LOG_DIR|$LOG_DIR|g" "$LOG_DIR/trading_loop.sh"
        chmod +x "$LOG_DIR/trading_loop.sh"
        
        # 启动后台进程
        nohup bash "$LOG_DIR/trading_loop.sh" > "$LOG_DIR/trading_daemon.log" 2>&1 &
        echo $! > "$PID_FILE"
        
        echo -e "${GREEN}✅ 交易日监控已启动 (PID: $!)${NC}"
        echo ""
        echo -e "📋 日志: $LOG_DIR/trading.log"
        echo ""
        echo -e "📅 ${CYAN}交易日监控节奏:${NC}"
        echo "   08:30 - 🌅 盘前简报 (持仓概况+风险提示+操作建议)"
        echo "   09:15 - 📈 开盘建议 (集合竞价分析+操作策略)"
        echo "   09:30-11:30 - 🔍 盘中监控 (每10分钟扫描)"
        echo "   11:31-12:59 - ⏸️ 午休暂停"
        echo "   13:00-15:00 - 🔍 盘中监控 (每10分钟扫描)"
        echo "   15:30 - 🌙 收盘复盘 (当日总结+明日建议)"
        ;;
        
    stop)
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            if kill -0 "$PID" 2>/dev/null; then
                echo -e "${YELLOW}🛑 停止交易日监控 (PID: $PID)...${NC}"
                kill "$PID" 2>/dev/null
                pkill -f "trading_loop.sh" 2>/dev/null
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
            echo -e "${GREEN}✅ 交易日监控运行中 (PID: $(cat $PID_FILE))${NC}"
            echo ""
            echo "📅 监控节奏:"
            echo "   08:30 盘前简报 | 09:15 开盘建议 | 09:30-15:00 盘中监控 | 15:30 收盘复盘"
            echo ""
            echo "📊 最近执行记录:"
            grep -E "(盘前简报|开盘建议|盘中检查|收盘复盘)" "$LOG_DIR/trading.log" 2>/dev/null | tail -5 || echo "  暂无记录"
        else
            echo -e "${RED}⏹️  交易日监控未运行${NC}"
        fi
        ;;
        
    log)
        if [ -f "$LOG_DIR/trading.log" ]; then
            tail -f "$LOG_DIR/trading.log"
        else
            echo -e "${YELLOW}暂无日志文件${NC}"
        fi
        ;;
        
    pre-market)
        echo -e "${BLUE}🌅 生成盘前简报...${NC}"
        echo ""
        python3 "$PYTHON_SCRIPT" pre_market
        ;;
        
    open)
        echo -e "${BLUE}📈 生成开盘建议...${NC}"
        echo ""
        python3 "$PYTHON_SCRIPT" open
        ;;
        
    intraday)
        echo -e "${BLUE}🔍 执行盘中检查...${NC}"
        echo ""
        python3 "$INTRADAY_SCRIPT"
        ;;
        
    close)
        echo -e "${BLUE}🌙 生成收盘复盘...${NC}"
        echo ""
        python3 "$PYTHON_SCRIPT" close
        ;;
        
    check)
        echo -e "${BLUE}🔍 执行即时持仓检查...${NC}"
        echo ""
        python3 "$INTRADAY_SCRIPT"
        ;;
        
    summary)
        if [ -f "$LOG_DIR/trading.log" ]; then
            # 提取最后一次收盘复盘或盘中报告
            tac "$LOG_DIR/trading.log" | grep -A 60 "收盘复盘总结\|盘中监控" | head -60 | tac
        else
            echo -e "${YELLOW}暂无日志${NC}"
        fi
        ;;
        
    *)
        echo "交易日全流程监控控制脚本"
        echo ""
        echo "用法: ./control_trading_day.sh [命令]"
        echo ""
        echo "${CYAN}后台监控:${NC}"
        echo "  start     - 启动交易日自动监控"
        echo "  stop      - 停止监控"
        echo "  status    - 查看运行状态"
        echo "  log       - 查看实时日志"
        echo ""
        echo "${CYAN}手动执行:${NC}"
        echo "  pre-market - 生成盘前简报"
        echo "  open       - 生成开盘建议"
        echo "  intraday   - 执行盘中检查"
        echo "  close      - 生成收盘复盘"
        echo "  check      - 即时持仓检查"
        echo "  summary    - 查看最新汇总"
        echo ""
        echo "${CYAN}监控节奏:${NC}"
        echo "  08:30  🌅 盘前简报 (持仓概况+风险提示+操作建议)"
        echo "  09:15  📈 开盘建议 (集合竞价分析+操作策略)"
        echo "  09:30-11:30  🔍 盘中监控 (每10分钟)"
        echo "  11:31-12:59  ⏸️ 午休暂停"
        echo "  13:00-15:00  🔍 盘中监控 (每10分钟)"
        echo "  15:30  🌙 收盘复盘 (当日总结+明日建议)"
        ;;
esac
