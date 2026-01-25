from datetime import datetime
from .extensions import db

class SystemConfig(db.Model):
    """系统配置表（对应管理员端配置）"""
    __tablename__ = 'system_config'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    is_open = db.Column(db.Boolean, default=True, comment='系统开启/关闭')
    campuses = db.Column(db.String(500), default="主校区,新校区", comment='可参观区域，逗号分隔')
    visit_times = db.Column(db.String(500), default="09:00-11:00,14:00-16:00", comment='参观时间段')
    daily_limit = db.Column(db.Integer, default=50, comment='每日限额')
    privacy_policy = db.Column(db.Text, default="<p>欢迎使用预约系统，请遵守相关规定...</p>", comment='隐私政策')

class User(db.Model):
    """用户表"""
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_type = db.Column(db.String(50), default="身份证", nullable=False, comment='证件类型')
    id_card = db.Column(db.String(50), unique=True, nullable=False, index=True, comment='证件号码')
    name = db.Column(db.String(50), nullable=False, comment='姓名')
    phone = db.Column(db.String(20), nullable=False, comment='手机号')
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')

class Admin(db.Model):
    """管理员表"""
    __tablename__ = 'admin'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True, comment='用户名')
    password_hash = db.Column(db.String(255), nullable=False, comment='密码哈希')
    is_super = db.Column(db.Boolean, default=False, comment='是否超级管理员')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')

class Announcement(db.Model):
    """公告表"""
    __tablename__ = 'announcement'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String(100), nullable=False, comment='公告标题')
    content = db.Column(db.Text, nullable=False, comment='公告内容，最大5000字符')
    is_pinned = db.Column(db.Boolean, default=False, index=True, comment='是否顶置')
    is_hidden = db.Column(db.Boolean, default=False, index=True, comment='是否隐藏')
    created_at = db.Column(db.DateTime, default=datetime.now, index=True, comment='创建时间')

class Reservation(db.Model):
    """预约记录表"""
    __tablename__ = 'reservation'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True, comment='用户ID')
    area = db.Column(db.String(50), comment='参观区域')
    visit_date = db.Column(db.Date, index=True, comment='参观日期')  # 修改为Date类型
    visit_time = db.Column(db.String(50), comment='参观时间')
    reason = db.Column(db.Text, comment='预约原因')
    res_type = db.Column(db.String(10), comment='预约类型：个人/团队')
    identity = db.Column(db.String(50), comment='身份')
    status = db.Column(db.String(20), default="待审核", index=True, comment='状态：待审核, 已同意, 已拒绝')
    reject_reason = db.Column(db.Text, comment='拒绝原因')
    created_at = db.Column(db.DateTime, default=datetime.now, index=True, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')

    user = db.relationship("User", backref=db.backref("reservations", lazy=True))