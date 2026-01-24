from flask import Flask
from werkzeug.security import generate_password_hash
from .config import Config
from .extensions import db
from .models import Admin, SystemConfig, Announcement

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

    # 初始化数据库（仅用于开发环境，生产环境应使用 Flask-Migrate）
    with app.app_context():
        # 只创建表，不删除已有数据
        db.create_all()
        init_data()

    return app

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
    
    # 创建默认公告（仅当没有公告时）
    if not Announcement.query.first():
        db.session.add(
            Announcement(
                title="欢迎访问档案馆预约系统",
                content="请各位访客遵守相关规定，提前预约。",
            )
        )
    # 提交所有更改
    db.session.commit()
