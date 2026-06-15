import os
import secrets
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 获取 SECRET_KEY，生产环境必须通过环境变量配置
_secret_key = os.environ.get("SECRET_KEY")
if not _secret_key:
    _env = os.environ.get("FLASK_ENV", "production")
    if _env == "production":
        raise RuntimeError(
            "[安全错误] 生产环境必须通过环境变量 SECRET_KEY 配置密钥，拒绝启动。"
            "请执行: export SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')"
        )
    else:
        # 开发环境生成随机临时密钥（每次重启会失效 session，属正常现象）
        import warnings
        _secret_key = secrets.token_hex(32)
        warnings.warn(
            "[安全警告] SECRET_KEY 未设置，已使用随机临时密钥（开发模式）。",
            UserWarning, stacklevel=2
        )

class Config:
    SECRET_KEY = _secret_key
    # 文件上传大小限制（支持最多7张、每张15MB）
    MAX_CONTENT_LENGTH = 200 * 1024 * 1024
    # MySQL连接配置
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or "mysql://henau:henau123456@localhost/archive_system"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # 连接池配置
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'pool_recycle': 3600,  # 连接回收时间（秒）
        'pool_pre_ping': True,  # 连接前健康检查
        'max_overflow': 20
    }