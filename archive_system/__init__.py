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
    
    # 创建默认场馆和校区子类别
    if not Venue.query.first():
        # 创建父场馆：校史馆
        xiaoshi_venue = Venue(
            name="校史馆",
            category="校史馆",
            description="河南农业大学校史馆是展示学校历史发展、办学成就和校园文化的重要窗口。馆内收藏了大量珍贵的历史文物、照片和文献资料，生动再现了学校自1902年创建以来的发展历程。",
            is_active=True
        )
        db.session.add(xiaoshi_venue)
        db.session.flush()  # 获取xiaoshi_venue的ID
        
        # 为校史馆创建校区子类别
        db.session.add(
            Venue(
                name="校史馆-文化路校区",
                category="校史馆",
                parent_venue_id=xiaoshi_venue.id,
                campus="文化路校区",
                description="河南农业大学校史馆文化路校区分馆",
                address="河南省郑州市金水区农业路63号河南农业大学文化路校区",
                open_hours="09:00-11:00,14:00-16:00",
                daily_limit=50,
                individual_limit=20,
                group_limit=30,
                group_min_size=2,
                group_max_size=50,
                advance_days=7,
                cutoff_time="16:00",
                is_active=True
            )
        )
        db.session.add(
            Venue(
                name="校史馆-龙子湖校区",
                category="校史馆",
                parent_venue_id=xiaoshi_venue.id,
                campus="龙子湖校区",
                description="河南农业大学校史馆龙子湖校区分馆",
                address="河南省郑州市郑东新区平安大道218号河南农业大学龙子湖校区",
                open_hours="09:00-11:00,14:00-16:00",
                daily_limit=50,
                individual_limit=20,
                group_limit=30,
                group_min_size=2,
                group_max_size=50,
                advance_days=7,
                cutoff_time="16:00",
                is_active=True
            )
        )
        
        # 创建父场馆：标本馆
        biaoben_venue = Venue(
            name="标本馆",
            category="标本馆",
            description="中原农业博物馆是展示农业生物多样性和农业文明的重要场所，馆内收藏了大量珍贵的标本和展品。",
            is_active=True
        )
        db.session.add(biaoben_venue)
        db.session.flush()  # 获取biaoben_venue的ID
        
        # 为标本馆创建校区子类别
        db.session.add(
            Venue(
                name="标本馆-文化路校区",
                category="标本馆",
                parent_venue_id=biaoben_venue.id,
                campus="文化路校区",
                description="中原农业博物馆文化路校区分馆，建有'百年农大厅'、'农业文明厅'、'昆虫王国厅'和'鸟类世界厅'四大主题展厅。",
                address="河南省郑州市金水区农业路63号河南农业大学文化路校区",
                open_hours="09:00-11:00,14:00-16:00",
                daily_limit=50,
                individual_limit=20,
                group_limit=30,
                group_min_size=2,
                group_max_size=50,
                advance_days=7,
                cutoff_time="16:00",
                is_active=True
            )
        )
        db.session.add(
            Venue(
                name="标本馆-龙子湖校区",
                category="标本馆",
                parent_venue_id=biaoben_venue.id,
                campus="龙子湖校区",
                description="中原农业博物馆龙子湖校区分馆",
                address="河南省郑州市郑东新区平安大道218号河南农业大学龙子湖校区",
                open_hours="09:00-11:00,14:00-16:00",
                daily_limit=50,
                individual_limit=20,
                group_limit=30,
                group_min_size=2,
                group_max_size=50,
                advance_days=7,
                cutoff_time="16:00",
                is_active=True
            )
        )
        
        # 为所有场馆添加默认时间段设置
        all_venues = Venue.query.all()
        time_slots = ["09:00-10:30", "10:30-12:00", "14:00-15:30", "15:30-17:00"]
        
        for venue in all_venues:
            # 只为校区子类别添加时间段设置
            if venue.parent_venue_id:
                for day in range(7):  # 0-6，0表示周日
                    for time_slot in time_slots:
                        db.session.add(
                            VenueTimeSlot(
                                venue_id=venue.id,
                                day_of_week=day,
                                time_slot=time_slot,
                                individual_capacity=20,
                                is_group_active=True,
                                is_active=True
                            )
                        )
    
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
