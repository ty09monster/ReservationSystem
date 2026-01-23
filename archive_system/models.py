from datetime import datetime
from .extensions import db

class SystemConfig(db.Model):
    """系统配置表（对应管理员端配置）"""
    id = db.Column(db.Integer, primary_key=True)
    is_open = db.Column(db.Boolean, default=True)  # 系统开启/关闭
    campuses = db.Column(db.String(500), default="主校区,新校区")  # 可参观区域，逗号分隔
    visit_times = db.Column(db.String(500), default="09:00-11:00,14:00-16:00")  # 参观时间段
    daily_limit = db.Column(db.Integer, default=50)  # 每日限额
    privacy_policy = db.Column(db.Text, default="<p>欢迎使用预约系统，请遵守相关规定...</p>")

class User(db.Model):
    """用户表"""
    id = db.Column(db.Integer, primary_key=True)
    id_type = db.Column(db.String(50), default="身份证", nullable=False)
    id_card = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(20), nullable=False)

class Admin(db.Model):
    """管理员表"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    is_super = db.Column(db.Boolean, default=False)

class Announcement(db.Model):
    """公告表"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

class Reservation(db.Model):
    """预约记录表"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    area = db.Column(db.String(50))
    visit_date = db.Column(db.String(20))  # 建议后续改为 Date 类型
    visit_time = db.Column(db.String(50))
    reason = db.Column(db.String(200))
    res_type = db.Column(db.String(10))  # 个人/团队
    identity = db.Column(db.String(50))
    status = db.Column(db.String(20), default="待审核")  # 待审核, 已同意, 已拒绝
    reject_reason = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.now)

    user = db.relationship("User", backref=db.backref("reservations", lazy=True))
