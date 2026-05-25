from flask import Flask
from werkzeug.security import generate_password_hash
from .config import Config
from .extensions import db
from .models import Admin, SystemConfig, Announcement, Venue, VenueTimeSlot, Attachment, ApprovalStaff
import os

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # 初始化扩展
    db.init_app(app)

    # 注册蓝图
    from .routes.h5 import h5_bp
    from .routes.admin import admin_bp
    from .routes.teacher import teacher_bp
    from .routes.archive import archive_bp
    app.register_blueprint(h5_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(teacher_bp)
    app.register_blueprint(archive_bp)

    # 避免多进程并发数据库操作 - 只在特定情况下初始化数据库
    # 使用环境变量控制是否初始化数据库，防止Gunicorn多worker同时执行
    if _is_init_enabled():
        with app.app_context():
            init_database_with_lock()

    return app

def _is_init_enabled():
    """检查是否应该执行数据库初始化"""
    env_val = os.environ.get('FLASK_INITDB', '')
    if env_val.lower() in ('1', 'true', 'yes'):
        return True
    if env_val in ('0', 'false', 'no', ''):
        return False
    return False

def _get_init_lock_path():
    """获取初始化锁文件的路径，使用应用专属目录"""
    app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    lock_dir = os.path.join(app_root, 'data')
    os.makedirs(lock_dir, exist_ok=True)
    return os.path.join(lock_dir, 'db_init.lock')

def init_database_with_lock():
    """使用原子文件创建锁，防止多进程并发初始化"""
    import atexit
    import time
    import sys

    lock_file_path = _get_init_lock_path()

    try:
        with open(lock_file_path, 'x') as f:
            f.write(str(os.getpid()))
            f.flush()
            os.fsync(f.fileno())

        def cleanup_lock():
            try:
                if os.path.exists(lock_file_path):
                    os.remove(lock_file_path)
            except Exception:
                pass
        atexit.register(cleanup_lock)

        sys.stdout.write("正在初始化数据库...\n")
        sys.stdout.flush()
        db.create_all()
        init_data()
        sys.stdout.write("数据库初始化完成\n")
        sys.stdout.flush()

    except FileExistsError:
        max_wait = 30
        for _ in range(max_wait):
            if not os.path.exists(lock_file_path):
                break
            time.sleep(1)
        sys.stdout.write("检测到数据库已初始化，跳过初始化步骤\n")
        sys.stdout.flush()

    except Exception as e:
        sys.stderr.write(f"数据库初始化失败: {e}\n")
        sys.stderr.flush()
        if os.path.exists(lock_file_path):
            try:
                os.remove(lock_file_path)
            except Exception:
                pass
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

        # 档案馆父场馆
        archive_parent = Venue(
            name="档案馆", category="档案馆",
            description="河南农业大学档案馆", is_active=True
        )
        db.session.add(archive_parent)
        db.session.flush()

        # 档案馆-龙子湖校区
        archive_lzh = Venue(
            name="档案馆（龙子湖校区）", category="档案馆",
            parent_venue_id=archive_parent.id, campus="龙子湖校区",
            address="龙子湖校区图书馆三楼", advance_days=7, cutoff_time="16:00",
            is_active=True
        )
        # 档案馆-文化路校区
        archive_whl = Venue(
            name="档案馆（文化路校区）", category="档案馆",
            parent_venue_id=archive_parent.id, campus="文化路校区",
            address="文化路校区行政楼二楼", advance_days=7, cutoff_time="16:00",
            is_active=True
        )
        db.session.add_all([archive_lzh, archive_whl])
        db.session.flush()

        # 为所有子场馆创建工作日时段（day_of_week: 0=周日, 1=周一, ..., 5=周五, 6=周六）
        child_venues = [xiaoshi_lzh, xiaoshi_whl, biaoben_lzh, biaoben_whl, archive_lzh, archive_whl]
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

    # 创建默认审批人员账号
    if not ApprovalStaff.query.first():
        import json
        archive_venues = Venue.query.filter_by(category="档案馆", parent_venue_id=None).all()
        archive_child_ids = [v.id for v in Venue.query.filter(Venue.parent_venue_id.in_([av.id for av in archive_venues])).all()] if archive_venues else []
        xiaoshi_parents = Venue.query.filter(Venue.category.in_(["校史馆", "标本馆"]), Venue.parent_venue_id == None).all()
        xiaoshi_child_ids = []
        if xiaoshi_parents:
            xiaoshi_child_ids = [v.id for v in Venue.query.filter(Venue.parent_venue_id.in_([p.id for p in xiaoshi_parents])).all()]

        default_staffs = [
            ApprovalStaff(
                username="admin", password_hash=generate_password_hash("admin"),
                name="档案馆领导", staff_id="LD001", department="档案馆",
                phone="13800000001", assigned_venue_ids=json.dumps(archive_child_ids),
                staff_type="leader", is_active=True
            ),
            ApprovalStaff(
                username="archive", password_hash=generate_password_hash("admin"),
                name="档案馆教师", staff_id="JS001", department="档案馆",
                phone="13800000002", assigned_venue_ids=json.dumps(archive_child_ids),
                staff_type="approval", is_active=True
            ),
            ApprovalStaff(
                username="xiaoshi_leader", password_hash=generate_password_hash("admin"),
                name="校史馆领导", staff_id="LD002", department="校史馆",
                phone="13800000003", assigned_venue_ids=json.dumps(xiaoshi_child_ids),
                staff_type="leader", is_active=True
            ),
            ApprovalStaff(
                username="xiaoshi_teacher", password_hash=generate_password_hash("admin"),
                name="校史馆教师", staff_id="JS002", department="校史馆",
                phone="13800000004", assigned_venue_ids=json.dumps(xiaoshi_child_ids),
                staff_type="approval", is_active=True
            ),
        ]
        db.session.add_all(default_staffs)
        logger.info("已创建默认审批人员账号")

    db.session.commit()

