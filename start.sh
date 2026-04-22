#!/bin/bash

# 创建日志目录
mkdir -p logs

# 激活虚拟环境
source ~/Flask/bin/activate

# 启动Gunicorn服务器（终端关闭后继续运行）
cd /var/www/ReservationSystem
nohup gunicorn -c gunicorn_config.py run:app > logs/gunicorn_stdout.log 2>&1 &
