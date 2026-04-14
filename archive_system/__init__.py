from flask import Flask
from werkzeug.security import generate_password_hash
from .config import Config
from .extensions import db
from .models import Admin, SystemConfig, Announcement, Venue, VenueTimeSlot, Attachment
import os

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # 初始化扩展
    db.init_app(app)

    # 注册蓝图
    from .routes.h5 import h5_bp
    from .routes.admin import admin_bp
    app.register_blueprint(h5_bp)
    app.register_blueprint(admin_bp)

    # 避免多进程并发数据库操作 - 只在特定情况下初始化数据库
    # 使用环境变量控制是否初始化数据库，防止Gunicorn多worker同时执行
    if os.environ.get('FLASK_INITDB') or app.config.get('INIT_DB_ON_STARTUP'):
        with app.app_context():
            # 添加锁机制或检查是否已经初始化过
            init_database_with_lock()

    return app

def init_database_with_lock():
    """使用简单的锁机制防止多进程并发初始化"""
    import tempfile
    import atexit
    
    lock_file_path = os.path.join(tempfile.gettempdir(), 'db_init_lock')
    
    # 尝试获取锁
    if not os.path.exists(lock_file_path):
        # 第一个进程获得锁并执行初始化
        try:
            # 创建锁文件
            with open(lock_file_path, 'w') as f:
                f.write('locked')
            
            # 注册退出清理函数
            def cleanup_lock():
                if os.path.exists(lock_file_path):
                    os.remove(lock_file_path)
            atexit.register(cleanup_lock)
            
            # 执行数据库初始化
            print("正在初始化数据库...")
            db.create_all()
            init_data()
            print("数据库初始化完成")
            
        except Exception as e:
            print(f"数据库初始化失败: {e}")
            # 确保即使失败也清理锁
            if os.path.exists(lock_file_path):
                os.remove(lock_file_path)
            raise
    else:
        # 其他进程等待直到初始化完成
        import time
        wait_count = 0
        max_wait = 30  # 最多等待30秒
        while os.path.exists(lock_file_path) and wait_count < max_wait:
            time.sleep(1)
            wait_count += 1
        print("检测到数据库已初始化，跳过初始化步骤")

def init_data():
    """初始化默认数据"""
    # 创建默认管理员
    if not Admin.query.filter_by(username="admin").first():
        admin = Admin(
            username="admin", 
            password_hash=generate_password_hash("admin"),
            is_super=True
        )
        db.session.add(admin)
    
    # 创建默认系统配置
    if not SystemConfig.query.first():
        db.session.add(SystemConfig())
    
    # 创建默认公告
    if not Announcement.query.first():
        db.session.add(
            Announcement(
                title="欢迎访问档案馆预约系统",
                content="请各位访客遵守相关规定，提前预约。",
            )
        )
    db.session.commit()
