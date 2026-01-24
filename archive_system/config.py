import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "your_secret_key_here"
    # MySQL连接配置（使用新用户名和密码）
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or "mysql://henau:henau123456@localhost/archive_system"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # 添加连接池配置
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'pool_recycle': 3600,#连接回收时间
        'pool_pre_ping': True,#连接前检查
        'max_overflow': 20
    }