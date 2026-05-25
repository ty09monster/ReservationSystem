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
    archive_types = db.Column(db.Text, comment='档案类型列表，逗号分隔')
    guide_list = db.Column(db.Text, comment='讲解员列表，JSON数组格式')

    def get_guide_list(self):
        import json
        try:
            return json.loads(self.guide_list) if self.guide_list else []
        except (json.JSONDecodeError, TypeError):
            return []

class User(db.Model):
    """用户表"""
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_type = db.Column(db.String(50), default="身份证", nullable=False, comment='证件类型')
    id_card = db.Column(db.String(50), unique=True, nullable=False, index=True, comment='证件号码')
    name = db.Column(db.String(50), nullable=False, comment='姓名')
    phone = db.Column(db.String(20), nullable=False, comment='手机号')
    email = db.Column(db.String(120), comment='邮箱地址')
    is_blacklisted = db.Column(db.Boolean, default=False, comment='是否在黑名单中')
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')

class Admin(db.Model):
    """管理员表"""
    __tablename__ = 'admin'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True, comment='用户名')
    password_hash = db.Column(db.String(255), nullable=False, comment='密码哈希')
    is_super = db.Column(db.Boolean, default=False, comment='是否超级管理员')
    role_id = db.Column(db.Integer, db.ForeignKey('role.id'), nullable=True, comment='角色ID')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')

    role = db.relationship('Role', backref=db.backref('admins', lazy=True))

class Announcement(db.Model):
    """公告表"""
    __tablename__ = 'announcement'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String(100), nullable=False, comment='公告标题')
    content = db.Column(db.Text, nullable=False, comment='公告内容，最大5000字符')
    is_pinned = db.Column(db.Boolean, default=False, index=True, comment='是否顶置')
    is_hidden = db.Column(db.Boolean, default=False, index=True, comment='是否隐藏')
    created_at = db.Column(db.DateTime, default=datetime.now, index=True, comment='创建时间')

class Venue(db.Model):
    """场馆表"""
    __tablename__ = 'venue'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False, comment='场馆名称')
    category = db.Column(db.String(50), nullable=False, comment='场馆分类：校史馆/标本馆')
    parent_venue_id = db.Column(db.Integer, db.ForeignKey('venue.id'), nullable=True, comment='父场馆ID，用于表示场馆-校区的层级关系')
    campus = db.Column(db.String(100), comment='校区')
    description = db.Column(db.Text, comment='场馆描述')
    address = db.Column(db.String(200), comment='场馆地址')
    open_hours = db.Column(db.String(200), default="09:00-11:00,14:00-16:00", comment='开放时间')
    daily_limit = db.Column(db.Integer, default=50, comment='每日限额')
    individual_limit = db.Column(db.Integer, default=20, comment='个人预约限额')
    group_limit = db.Column(db.Integer, default=30, comment='团体预约限额')
    group_min_size = db.Column(db.Integer, default=2, comment='团体最小人数')
    group_max_size = db.Column(db.Integer, default=50, comment='团体最大人数')
    advance_days = db.Column(db.Integer, default=7, comment='可提前预约天数')
    cutoff_time = db.Column(db.String(10), default="16:00", comment='当日预约截止时间')
    is_active = db.Column(db.Boolean, default=True, comment='是否启用')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')

    # 自引用关系，用于表示场馆-校区的层级关系
    parent_venue = db.relationship('Venue', remote_side=[id], backref=db.backref('child_venues', lazy=True))

class Reservation(db.Model):
    """预约记录表"""
    __tablename__ = 'reservation'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True, comment='用户ID')
    venue_id = db.Column(db.Integer, db.ForeignKey("venue.id"), nullable=False, index=True, comment='场馆ID')
    visit_date = db.Column(db.Date, index=True, comment='参观日期')
    visit_time = db.Column(db.String(50), comment='参观时间')
    reason = db.Column(db.Text, comment='预约原因')
    archive_name = db.Column(db.String(200), comment='档案名称')
    archive_number = db.Column(db.String(100), comment='档号')
    archive_purpose = db.Column(db.Text, comment='查阅目的')
    res_type = db.Column(db.String(10), default="个人", comment='预约类型：个人/单位')
    visit_type = db.Column(db.String(20), default="线下", comment='查阅类型：线上/线下')
    group_name = db.Column(db.String(100), comment='预约单位')
    group_contact = db.Column(db.String(50), comment='单位联系人')
    group_size = db.Column(db.Integer, default=1, comment='团体人数')
    visitor_count = db.Column(db.Integer, default=1, comment='参观人数')
    license_plate = db.Column(db.String(50), comment='车辆牌号')
    need_guide = db.Column(db.Boolean, default=False, comment='是否需要讲解')
    visiting_unit = db.Column(db.String(100), comment='参观单位')
    contact_phone = db.Column(db.String(20), comment='联系电话')
    identity = db.Column(db.String(50), comment='身份')
    campus = db.Column(db.String(100), comment='校区')
    status = db.Column(db.String(20), default="待部门领导指定审批人", index=True, comment='状态：待部门领导指定审批人, 待审核, 已同意, 已拒绝, 已核销, 已完成, 已取消')
    reject_reason = db.Column(db.Text, comment='拒绝原因/审批意见')
    verified_at = db.Column(db.DateTime, comment='核销时间')
    verified_by = db.Column(db.Integer, db.ForeignKey("admin.id"), nullable=True, comment='核销人ID')
    approval_teacher_id = db.Column(db.Integer, db.ForeignKey("approval_staff.id"), nullable=True, comment='指定审批教师ID')
    leader_id = db.Column(db.Integer, db.ForeignKey("approval_staff.id"), nullable=True, comment='处理部门领导ID')
    leader_opinion = db.Column(db.Text, comment='部门领导审批意见')
    verify_note = db.Column(db.Text, comment='核销备注')
    assigned_at = db.Column(db.DateTime, comment='指定审批教师时间')
    guide_info = db.Column(db.String(100), comment='讲解员信息')
    created_at = db.Column(db.DateTime, default=datetime.now, index=True, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')

    user = db.relationship("User", backref=db.backref("reservations", lazy=True))
    venue = db.relationship("Venue", backref=db.backref("reservations", lazy=True))
    approval_teacher = db.relationship("ApprovalStaff", foreign_keys=[approval_teacher_id], backref=db.backref("assigned_reservations", lazy=True))
    leader = db.relationship("ApprovalStaff", foreign_keys=[leader_id], backref=db.backref("handled_reservations", lazy=True))

class VenueTimeSlot(db.Model):
    """场馆时段表"""
    __tablename__ = 'venue_time_slot'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    venue_id = db.Column(db.Integer, db.ForeignKey('venue.id'), nullable=False, index=True, comment='场馆ID')
    day_of_week = db.Column(db.Integer, nullable=False, comment='星期几（0-6，0=周日，1=周一，...，6=周六）')
    time_slot = db.Column(db.String(50), nullable=False, comment='时间段（如09:00-10:30）')
    individual_capacity = db.Column(db.Integer, default=20, comment='个人预约最大容量')
    is_group_active = db.Column(db.Boolean, default=True, comment='团体预约是否启用')
    is_active = db.Column(db.Boolean, default=True, comment='是否启用')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')

    venue = db.relationship('Venue', backref=db.backref('time_slots', lazy=True))

class VenueTimeSlotDisabledDate(db.Model):
    """场馆时段禁用日期表"""
    __tablename__ = 'venue_time_slot_disabled_date'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    venue_id = db.Column(db.Integer, db.ForeignKey('venue.id'), nullable=False, index=True, comment='场馆ID')
    time_slot = db.Column(db.String(50), nullable=False, comment='时间段（如09:00-10:30）')
    disabled_date = db.Column(db.Date, nullable=False, index=True, comment='禁用的日期')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')

    venue = db.relationship('Venue', backref=db.backref('disabled_dates', lazy=True))

class Attachment(db.Model):
    """附件表"""
    __tablename__ = 'attachment'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    reservation_id = db.Column(db.Integer, db.ForeignKey("reservation.id"), nullable=False, index=True, comment='预约ID')
    filename = db.Column(db.String(255), nullable=False, comment='文件名')
    filepath = db.Column(db.String(255), nullable=False, comment='文件路径')
    file_size = db.Column(db.Integer, nullable=False, comment='文件大小（字节）')
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')

    reservation = db.relationship("Reservation", backref=db.backref("attachments", lazy=True))

class ArchiveRequest(db.Model):
    """档案查询申请表"""
    __tablename__ = 'archive_request'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True, comment='用户ID')
    email = db.Column(db.String(120), nullable=False, comment='用于接收档案信息的邮箱')
    status = db.Column(db.String(20), default="待处理", index=True, comment='状态：待处理, 已处理, 已拒绝')
    admin_remark = db.Column(db.Text, comment='管理员备注/处理结果')
    created_at = db.Column(db.DateTime, default=datetime.now, index=True, comment='申请时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')

    user = db.relationship("User", backref=db.backref("archive_requests", lazy=True))

class CancelRequest(db.Model):
    """预约撤销申请表"""
    __tablename__ = 'cancel_request'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    reservation_id = db.Column(db.Integer, db.ForeignKey("reservation.id"), nullable=False, index=True, comment='预约ID')
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True, comment='用户ID')
    reason = db.Column(db.Text, comment='撤销原因')
    status = db.Column(db.String(20), default="待处理", index=True, comment='状态：待处理, 已同意, 已拒绝')
    admin_remark = db.Column(db.Text, comment='管理员备注')
    processed_at = db.Column(db.DateTime, comment='处理时间')
    created_at = db.Column(db.DateTime, default=datetime.now, index=True, comment='申请时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')

    reservation = db.relationship("Reservation", backref=db.backref("cancel_requests", lazy=True))
    user = db.relationship("User", backref=db.backref("cancel_requests", lazy=True))

class Role(db.Model):
    """角色表"""
    __tablename__ = 'role'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), unique=True, nullable=False, comment='角色名称')
    permissions = db.Column(db.Text, default='[]', comment='权限列表，JSON数组格式')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')

    def get_permissions(self):
        import json
        try:
            return json.loads(self.permissions) if self.permissions else []
        except (json.JSONDecodeError, TypeError):
            return []

    def has_permission(self, perm_key):
        perms = self.get_permissions()
        return perm_key in perms

class ApprovalStaff(db.Model):
    """审批人员表（审批教师/部门领导）"""
    __tablename__ = 'approval_staff'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True, comment='登录用户名')
    password_hash = db.Column(db.String(255), nullable=False, comment='密码哈希')
    name = db.Column(db.String(50), nullable=False, comment='姓名')
    staff_id = db.Column(db.String(50), comment='工号')
    department = db.Column(db.String(100), comment='所属部门')
    phone = db.Column(db.String(20), comment='联系电话')
    assigned_venue_ids = db.Column(db.Text, default='[]', comment='负责场馆ID列表，JSON数组格式')
    staff_type = db.Column(db.String(20), default='approval', index=True, comment='人员类型：approval=审批教师, leader=部门领导')
    is_active = db.Column(db.Boolean, default=True, comment='是否启用')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    def get_assigned_venue_ids(self):
        import json
        try:
            return json.loads(self.assigned_venue_ids) if self.assigned_venue_ids else []
        except (json.JSONDecodeError, TypeError):
            return []


class SystemLog(db.Model):
    """系统日志表"""
    __tablename__ = 'system_log'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    log_type = db.Column(db.String(30), nullable=False, index=True, comment='日志类型：operation=操作日志, login=登录日志, error=错误日志, access=通行权限下发日志')
    operator = db.Column(db.String(50), comment='操作人')
    operator_ip = db.Column(db.String(50), comment='操作IP')
    module = db.Column(db.String(50), comment='操作模块')
    action = db.Column(db.String(100), comment='操作动作')
    detail = db.Column(db.Text, comment='详细内容')
    result = db.Column(db.String(20), default='成功', comment='操作结果：成功/失败')
    created_at = db.Column(db.DateTime, default=datetime.now, index=True, comment='创建时间')

class Guide(db.Model):
    """讲解员表"""
    __tablename__ = 'guide'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), nullable=False, comment='姓名')
    staff_id = db.Column(db.String(50), comment='工号')
    phone = db.Column(db.String(20), comment='联系电话')
    expertise = db.Column(db.String(200), comment='擅长讲解内容')
    status = db.Column(db.String(20), default='在岗', comment='状态：在岗/离岗')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')