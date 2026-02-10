#!/bin/bash

# 创建日志目录
mkdir -p logs

# 激活虚拟环境
source ~/Flask/bin/activate

# 启动Gunicorn服务器
exec gunicorn -c gunicorn_config.py run:app
