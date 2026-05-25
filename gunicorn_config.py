# Gunicorn配置文件

# 绑定地址和端口
bind = '0.0.0.0:8000'

# 工作进程数
workers = 4

# 工作线程数
threads = 2

# 工作进程类型
worker_class = 'gthread'

# 最大请求数
max_requests = 1000

# 最大请求数后重启进程
max_requests_jitter = 50

# 超时时间
timeout = 30

# 访问日志
accesslog = 'logs/gunicorn_access.log'

# 错误日志
errorlog = 'logs/gunicorn_error.log'

# 日志级别
loglevel = 'info'

# 进程名称
proc_name = 'reservation_system'
