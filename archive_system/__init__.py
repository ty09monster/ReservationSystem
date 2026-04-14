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
    """使用原子文件创建锁，防止多进程并发初始化。
    使用 open(..., 'x') 模式原子性地创建文件，避免 TOCTOU 竞争条件。
    """
    import tempfile
    import atexit
    import time

    lock_file_path = os.path.join(tempfile.gettempdir(), 'db_init_lock')

    try:
        # 原子创建锁文件：若已存在则抛异常，避免竞争条件
        with open(lock_file_path, 'x') as f:
            f.write(str(os.getpid()))

        def cleanup_lock():
            if os.path.exists(lock_file_path):
                os.remove(lock_file_path)
        atexit.register(cleanup_lock)

        print("正在初始化数据库...")
        db.create_all()
        init_data()
        print("数据库初始化完成")

    except FileExistsError:
        # 其他进程已拿到锁，等待其初始化完成
        max_wait = 30
        for _ in range(max_wait):
            if not os.path.exists(lock_file_path):
                break
            time.sleep(1)
        print("检测到数据库已初始化，跳过初始化步骤")

    except Exception as e:
        print(f"数据库初始化失败: {e}")
        if os.path.exists(lock_file_path):
            os.remove(lock_file_path)
        raise

def init_data():
    """初始化默认数据：管理员、系统配置、公告、场馆、时段"""
    import logging
    logger = logging.getLogger(__name__)

    # 创建默认管理员
    if not Admin.query.filter_by(username="admin").first():
        admin = Admin(
            username="admin", 
            password_hash=generate_password_hash("admin"),
            is_super=True
        )
        db.session.add(admin)
        logger.info("已创建默认管理员 admin")
    
    # 创建默认系统配置
    if not SystemConfig.query.first():
        db.session.add(SystemConfig())
        logger.info("已创建默认系统配置")
    
    # 创建默认公告
    if not Announcement.query.first():
        db.session.add(
            Announcement(
                title="欢迎访问档案馆预约系统",
                content="请各位访客遵守相关规定，提前预约。",
            )
        )
        logger.info("已创建默认公告")

    # 创建默认场馆（如果没有任何场馆）
    if not Venue.query.first():
        # 校史馆父场馆
        xiaoshi_parent = Venue(
            name="校史馆", category="校史馆",
            description="河南农业大学校史馆", is_active=True
        )
        db.session.add(xiaoshi_parent)
        db.session.flush()

        # 校史馆-龙子湖校区
        xiaoshi_lzh = Venue(
            name="校史馆（龙子湖校区）", category="校史馆",
            parent_venue_id=xiaoshi_parent.id, campus="龙子湖校区",
            address="龙子湖校区图书馆二楼", advance_days=7, cutoff_time="16:00",
            is_active=True
        )
        # 校史馆-文化路校区
        xiaoshi_whl = Venue(
            name="校史馆（文化路校区）", category="校史馆",
            parent_venue_id=xiaoshi_parent.id, campus="文化路校区",
            address="文化路校区行政楼一楼", advance_days=7, cutoff_time="16:00",
            is_active=True
        )
        db.session.add_all([xiaoshi_lzh, xiaoshi_whl])

        # 标本馆父场馆
        biaoben_parent = Venue(
            name="标本馆", category="标本馆",
            description="河南农业大学农业资源标本馆", is_active=True
        )
        db.session.add(biaoben_parent)
        db.session.flush()

        # 标本馆-龙子湖校区
        biaoben_lzh = Venue(
            name="标本馆（龙子湖校区）", category="标本馆",
            parent_venue_id=biaoben_parent.id, campus="龙子湖校区",
            address="龙子湖校区理科实验楼", advance_days=7, cutoff_time="16:00",
            is_active=True
        )
        # 标本馆-文化路校区
        biaoben_whl = Venue(
            name="标本馆（文化路校区）", category="标本馆",
            parent_venue_id=biaoben_parent.id, campus="文化路校区",
            address="文化路校区生物楼", advance_days=7, cutoff_time="16:00",
            is_active=True
        )
        db.session.add_all([biaoben_lzh, biaoben_whl])

        # 档案馆（用于邮件查询）
        archive_venue = Venue(
            name="档案馆", category="档案馆",
            description="河南农业大学档案馆", campus="龙子湖校区",
            advance_days=7, cutoff_time="16:00", is_active=True
        )
        db.session.add(archive_venue)
        db.session.flush()

        # 为所有子场馆创建工作日时段（day_of_week: 0=周日, 1=周一, ..., 5=周五, 6=周六）
        child_venues = [xiaoshi_lzh, xiaoshi_whl, biaoben_lzh, biaoben_whl]
        time_slots = ["09:00-10:30", "10:30-12:00", "14:00-15:30", "15:30-17:00"]

        for venue in child_venues:
            for dow in range(1, 6):  # 周一(1)到周五(5)
                for ts in time_slots:
                    slot = VenueTimeSlot(
                        venue_id=venue.id,
                        day_of_week=dow,
                        time_slot=ts,
                        individual_capacity=20,
                        is_group_active=True,
                        is_active=True
                    )
                    db.session.add(slot)

        logger.info("已创建默认场馆和时段数据")

    db.session.commit()

