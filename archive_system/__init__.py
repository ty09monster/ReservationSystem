from flask import Flask
from werkzeug.security import generate_password_hash
from .config import Config
from .extensions import db
from .models import Admin, SystemConfig, Announcement, Venue, VenueTimeSlot, Attachment

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
        # 删除现有表，重新创建（用于开发环境，解决字段添加问题）
        db.drop_all()
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
