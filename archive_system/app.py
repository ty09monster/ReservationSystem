import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here' # 用于Session加密
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///archive.db' # 数据库文件
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- 数据库模型 ---

class SystemConfig(db.Model):
    """系统配置表（对应管理员端配置）"""
    id = db.Column(db.Integer, primary_key=True)
    is_open = db.Column(db.Boolean, default=True) # 系统开启/关闭
    campuses = db.Column(db.String(500), default="主校区,新校区") # 可参观区域，逗号分隔
    visit_times = db.Column(db.String(500), default="09:00-11:00,14:00-16:00") # 参观时间段
    daily_limit = db.Column(db.Integer, default=50) # 每日限额

# class User(db.Model):
#     """用户表"""
#     id = db.Column(db.Integer, primary_key=True)
#     id_card = db.Column(db.String(20), unique=True, nullable=False)
#     name = db.Column(db.String(50), nullable=False)
#     phone = db.Column(db.String(20), nullable=False)
    
class User(db.Model):
    """用户表"""
    id = db.Column(db.Integer, primary_key=True)
    # 新增字段：证件类型，默认为身份证
    id_type = db.Column(db.String(50), default='身份证', nullable=False)
    # id_card 字段含义变为“证件号码”
    id_card = db.Column(db.String(50), unique=True, nullable=False) 
    name = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(20), nullable=False)


class Admin(db.Model):
    """管理员表"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))

class Announcement(db.Model):
    """公告表"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

class Reservation(db.Model):
    """预约记录表"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    area = db.Column(db.String(50))
    visit_date = db.Column(db.String(20)) # 简化为字符串，实际项目可用Date类型
    visit_time = db.Column(db.String(50))
    reason = db.Column(db.String(200))
    res_type = db.Column(db.String(10)) # 个人/团队
    identity = db.Column(db.String(50))
    status = db.Column(db.String(20), default='待审核') # 待审核, 已同意, 已拒绝
    reject_reason = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    user = db.relationship('User', backref=db.backref('reservations', lazy=True))

# --- 初始化数据 ---
def init_db():
    with app.app_context():
        db.create_all()
        # 创建默认管理员 (账号: admin, 密码: admin)
        if not Admin.query.filter_by(username='admin').first():
            admin = Admin(username='admin', password_hash=generate_password_hash('admin'))
            db.session.add(admin)
        # 创建默认系统配置
        if not SystemConfig.query.first():
            db.session.add(SystemConfig())
        # 创建一条默认公告
        if not Announcement.query.first():
            db.session.add(Announcement(title="欢迎访问档案馆预约系统", content="请各位访客遵守相关规定，提前预约。"))
        db.session.commit()

# --- 路由：用户端 (H5) ---

@app.route('/')
def index():
    return redirect(url_for('h5_login'))

# @app.route('/h5/login', methods=['GET', 'POST'])
# def h5_login():
#     if 'user_id' in session:
#         return redirect(url_for('h5_home'))
    
#     if request.method == 'POST':
#         id_card = request.form.get('id_card')
#         name = request.form.get('name')
#         phone = request.form.get('phone')
        
#         user = User.query.filter_by(id_card=id_card).first()
#         if not user:
#             user = User(id_card=id_card, name=name, phone=phone)
#             db.session.add(user)
#             db.session.commit()
#         else:
#             # 更新信息
#             user.name = name
#             user.phone = phone
#             db.session.commit()
        
#         session['user_id'] = user.id
#         return redirect(url_for('h5_home'))
        
#     return render_template('h5_login.html')

@app.route('/h5/login', methods=['GET', 'POST'])
def h5_login():
    if 'user_id' in session:
        return redirect(url_for('h5_home'))
    
    if request.method == 'POST':
        # 获取表单提交的数据
        id_type = request.form.get('id_type') # 获取证件类型
        id_card = request.form.get('id_card') # 获取证件号码
        name = request.form.get('name')
        phone = request.form.get('phone')
        
        # 简单校验
        if not id_type or not id_card:
            flash("请完善证件信息")
            return redirect(url_for('h5_login'))

        # 查询用户是否存在
        user = User.query.filter_by(id_card=id_card).first()
        
        if not user:
            # 注册新用户：同时保存证件类型和号码
            user = User(id_type=id_type, id_card=id_card, name=name, phone=phone)
            db.session.add(user)
            db.session.commit()
        else:
            # 更新信息：如果用户换了证件类型，这里也更新一下
            user.name = name
            user.phone = phone
            user.id_type = id_type 
            db.session.commit()
        
        session['user_id'] = user.id
        return redirect(url_for('h5_home'))
        
    return render_template('h5_login.html')


@app.route('/h5/home')
def h5_home():
    if 'user_id' not in session:
        return redirect(url_for('h5_login'))
    
    user = User.query.get(session['user_id'])
    announcements = Announcement.query.order_by(Announcement.created_at.desc()).limit(5).all()
    config = SystemConfig.query.first()
    return render_template('h5_home.html', user=user, announcements=announcements, config=config)

@app.route('/h5/reserve', methods=['GET', 'POST'])
def h5_reserve():
    if 'user_id' not in session: return redirect(url_for('h5_login'))
    
    config = SystemConfig.query.first()
    if not config.is_open:
        flash("系统维护中，暂时关闭预约")
        return redirect(url_for('h5_home'))

    if request.method == 'POST':
        # 收集表单信息
        area = request.form.get('area')
        visit_date = request.form.get('visit_date')
        visit_time = request.form.get('visit_time')
        reason = request.form.get('reason')
        res_type = request.form.get('res_type')
        identity = request.form.get('identity')
        
        res = Reservation(
            user_id=session['user_id'],
            area=area, visit_date=visit_date, visit_time=visit_time,
            reason=reason, res_type=res_type, identity=identity
        )
        db.session.add(res)
        db.session.commit()
        
        # 模拟微信通知
        print(f"【模拟微信通知】用户 {session['user_id']} 预约提交成功，等待审核。")
        flash("预约提交成功，请等待审核通知")
        return redirect(url_for('h5_history'))
        
    campuses = config.campuses.split(',')
    times = config.visit_times.split(',')
    user = User.query.get(session['user_id'])
    return render_template('h5_reserve.html', user=user, campuses=campuses, times=times)

@app.route('/h5/history')
def h5_history():
    if 'user_id' not in session: return redirect(url_for('h5_login'))
    reservations = Reservation.query.filter_by(user_id=session['user_id']).order_by(Reservation.created_at.desc()).all()
    return render_template('h5_history.html', reservations=reservations)

@app.route('/h5/profile', methods=['GET', 'POST'])
def h5_profile():
    if 'user_id' not in session: return redirect(url_for('h5_login'))
    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        user.name = request.form.get('name')
        user.phone = request.form.get('phone')
        db.session.commit()
        flash("个人信息已更新")
        return redirect(url_for('h5_home'))
        
    return render_template('h5_profile.html', user=user)

# --- 路由：后台管理端 (Web) ---

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        admin = Admin.query.filter_by(username=username).first()
        if admin and check_password_hash(admin.password_hash, password):
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        flash("用户名或密码错误")
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    
    # 获取数据
    reservations = Reservation.query.order_by(Reservation.created_at.desc()).all()
    # announcements = Announcement.query.order_by(Reservation.created_at.desc()).all()
    announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()
    config = SystemConfig.query.first()
    
    return render_template('admin_dashboard.html', 
                           reservations=reservations, 
                           announcements=announcements, 
                           config=config)

# 后台操作接口
@app.route('/admin/audit/<int:res_id>', methods=['POST'])
def admin_audit(res_id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    action = request.form.get('action') # approve or reject
    reject_reason = request.form.get('reject_reason', '')
    
    res = Reservation.query.get(res_id)
    if action == 'approve':
        res.status = '已同意'
        # 模拟微信通知
        print(f"【模拟微信通知】预约已同意。注意事项：请携带身份证入馆。")
    elif action == 'reject':
        res.status = '已拒绝'
        res.reject_reason = reject_reason
        print(f"【模拟微信通知】预约被拒绝。原因：{reject_reason}")
        
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/config', methods=['POST'])
def admin_config():
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    
    config = SystemConfig.query.first()
    
    # 系统开关
    if 'toggle_system' in request.form:
        config.is_open = not config.is_open
        
    # 修改配置
    if 'update_config' in request.form:
        config.campuses = request.form.get('campuses')
        config.visit_times = request.form.get('visit_times')
        config.daily_limit = request.form.get('daily_limit')
        
    # 发布公告
    if 'publish_notice' in request.form:
        title = request.form.get('title')
        content = request.form.get('content')
        new_notice = Announcement(title=title, content=content)
        db.session.add(new_notice)
        
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    init_db() # 初始化数据库
    app.run(debug=True, host='0.0.0.0', port=5000)