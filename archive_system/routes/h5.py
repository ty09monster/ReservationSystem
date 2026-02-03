from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime
import os
import uuid
from ..extensions import db
from ..models import User, SystemConfig, Announcement, Reservation, Venue, Attachment
from ..validators import validate_certificate, validate_phone, validate_visit_date
from ..decorators import login_required

h5_bp = Blueprint('h5', __name__)

@h5_bp.route("/")
def index():
    """
    系统首页（A页面）
    无需登录即可访问
    """
    config = SystemConfig.query.first()
    # 获取最新的公告，优先展示顶置的公告，最多展示2条
    announcements = Announcement.query.filter_by(is_hidden=False).order_by(
        Announcement.is_pinned.desc(),
        Announcement.created_at.desc()
    ).limit(2).all()
    return render_template("index.html", config=config, announcements=announcements)

@h5_bp.route("/announcements")
def announcements():
    """
    公告列表（A页面）
    无需登录即可访问
    """
    announcements = Announcement.query.filter_by(is_hidden=False).order_by(
        Announcement.is_pinned.desc(),
        Announcement.created_at.desc()
    ).all()
    return render_template("announcements.html", announcements=announcements)

@h5_bp.route("/about")
def about():
    """
    关于我们（A页面）
    无需登录即可访问
    """
    config = SystemConfig.query.first()
    return render_template("about.html", config=config)

@h5_bp.route("/h5/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        # 获取原访问地址，如果没有则跳转到首页
        next_url = request.args.get('next')
        if next_url:
            return redirect(next_url)
        return redirect(url_for("h5.home"))

    if request.method == "POST":
        id_type = request.form.get("id_type")
        id_card = request.form.get("id_card").upper().strip()
        name = request.form.get("name")
        phone = request.form.get("phone").strip()

        is_phone_valid, phone_msg = validate_phone(phone)
        config = SystemConfig.query.first()
        if not is_phone_valid:
            flash(f"手机号错误：{phone_msg}")
            return render_template("h5_login.html", prev_name=name, prev_phone=phone, prev_id_card=id_card, prev_id_type=id_type, privacy_policy=config.privacy_policy)
        
        is_valid, err_msg = validate_certificate(id_type, id_card)
        if not is_valid:
            flash(f"证件错误：{err_msg}")
            return render_template("h5_login.html", prev_name=name, prev_phone=phone, prev_id_card=id_card, prev_id_type=id_type, privacy_policy=config.privacy_policy)
        
        user = User.query.filter_by(id_card=id_card).first()

        if not user:
            user = User(id_type=id_type, id_card=id_card, name=name, phone=phone)
            db.session.add(user)
            db.session.commit()
        else:
            user.name = name
            user.phone = phone
            user.id_type = id_type
            db.session.commit()

        session["user_id"] = user.id
        # 登录成功后跳转到原访问地址，优先使用POST参数
        next_url = request.form.get('next') or request.args.get('next')
        if next_url:
            return redirect(next_url)
        return redirect(url_for("h5.home"))

    config = SystemConfig.query.first()
    policy_text = config.privacy_policy if config else "<p>暂无内容</p>"
    return render_template("h5_login.html", privacy_policy=policy_text)

@h5_bp.route("/h5/home")
@login_required
def home():

    user = User.query.get(session["user_id"])
    config = SystemConfig.query.first()
    
    # 检查用户是否存在
    if not user:
        flash("用户信息不存在，请重新登录")
        session.clear()
        return redirect(url_for("h5.login"))
    
    return render_template(
        "h5_home.html", 
        user=user, 
        config=config
    )

# 预约基础函数
def _reserve_base(venue_category, res_type):
    # 检查用户是否存在
    user = User.query.get(session["user_id"])
    if not user:
        flash("用户信息不存在，请重新登录")
        session.clear()
        return redirect(url_for("h5.login"))

    config = SystemConfig.query.first()
    if not config.is_open:
        flash("系统维护中，暂时关闭预约")
        return redirect(url_for("h5.home"))

    # 获取所有启用的场馆（包括父场馆和子类别）
    venues = Venue.query.filter_by(is_active=True).all()
    if not venues:
        flash(f"暂无可用场馆")
        return redirect(url_for("h5.home"))

    if request.method == "POST":
        campus_venue_id = request.form.get("campus_venue_id")
        visit_date = request.form.get("visit_date")
        visit_time = request.form.get("visit_time")
        reason = request.form.get("reason")
        group_name = request.form.get("group_name")
        group_contact = request.form.get("group_contact")
        group_size = request.form.get("group_size", 1, type=int)
        identity = request.form.get("identity")

        # 验证场馆是否存在且启用
        venue = Venue.query.filter_by(id=campus_venue_id, is_active=True).first()
        if not venue:
            flash("选择的场馆不存在或未启用")
            return render_template(f"h5_reserve_{venue_category}_{res_type}.html", user=user, venues=venues)

        # 验证预约日期
        is_date_valid, date_msg = validate_visit_date(visit_date)
        if not is_date_valid:
            flash(date_msg)
            return render_template(f"h5_reserve_{venue_category}_{res_type}.html", user=user, venues=venues)

        # 验证团体信息
        if res_type == "团队":
            if not group_name:
                flash("请输入团体名称")
                return render_template(f"h5_reserve_{venue_category}_{res_type}.html", user=user, venues=venues)
            if not group_contact:
                flash("请输入团体联系人")
                return render_template(f"h5_reserve_{venue_category}_{res_type}.html", user=user, venues=venues)
            if group_size < venue.group_min_size:
                flash(f"团体人数至少为{venue.group_min_size}人")
                return render_template(f"h5_reserve_{venue_category}_{res_type}.html", user=user, venues=venues)
            if group_size > venue.group_max_size:
                flash(f"团体人数不能超过{venue.group_max_size}人")
                return render_template(f"h5_reserve_{venue_category}_{res_type}.html", user=user, venues=venues)

        # 检查场馆当日预约人数是否已满
        visit_date_obj = datetime.strptime(visit_date, "%Y-%m-%d").date()
        current_count = Reservation.query.filter_by(
            venue_id=campus_venue_id,
            visit_date=visit_date_obj,
            status="已同意"
        ).count()
        
        if current_count >= venue.daily_limit:
            flash(f"{venue.name} {visit_date} 预约人数已满，请选择其他日期")
            return render_template(f"h5_reserve_{venue_category}_{res_type}.html", user=user, venues=venues)

        # 创建预约记录
        res = Reservation(
            user_id=session["user_id"],
            venue_id=campus_venue_id,
            visit_date=visit_date_obj,
            visit_time=visit_time,
            reason=reason,
            res_type=res_type,
            group_name=group_name,
            group_contact=group_contact,
            group_size=group_size,
            identity=identity,
            campus=venue.campus,
        )
        db.session.add(res)
        db.session.commit()

        # 处理附件上传
        if 'attachments' in request.files:
            files = request.files.getlist('attachments')
            
            # 创建上传目录
            upload_dir = os.path.join(os.path.dirname(__file__), '..', 'static', 'uploads')
            if not os.path.exists(upload_dir):
                os.makedirs(upload_dir)
            
            # 处理上传的文件
            for file in files:
                if file and file.filename:
                    # 检查文件大小
                    if file.content_length > 15 * 1024 * 1024:
                        flash(f"文件 {file.filename} 超过15MB限制")
                        return render_template(f"h5_reserve_{venue_category}_{res_type}.html", user=user, venues=venues)
                    
                    # 生成唯一文件名
                    ext = os.path.splitext(file.filename)[1]
                    filename = f"{uuid.uuid4()}{ext}"
                    filepath = os.path.join(upload_dir, filename)
                    
                    # 保存文件
                    file.save(filepath)
                    
                    # 创建附件记录
                    attachment = Attachment(
                        reservation_id=res.id,
                        filename=file.filename,
                        filepath=os.path.join('uploads', filename),
                        file_size=file.content_length
                    )
                    db.session.add(attachment)
                    
                    print(f"【附件上传】用户 {user.id} 上传了文件: {file.filename}，保存为: {filename}")
            
            # 提交附件记录
            db.session.commit()

        print(f"【模拟微信通知】用户 {session['user_id']} 预约提交成功，等待审核。")
        flash("预约提交成功，请等待审核通知")
        return redirect(url_for("h5.history"))

    return render_template(f"h5_reserve_{venue_category}_{res_type}.html", user=user, venues=venues)

# 校史馆个人预约
@h5_bp.route("/h5/reserve/xiaoshi/individual", methods=["GET", "POST"])
@login_required
def reserve_xiaoshi_individual():
    return _reserve_base("校史馆", "个人")

# 标本馆个人预约
@h5_bp.route("/h5/reserve/biaoben/individual", methods=["GET", "POST"])
@login_required
def reserve_biaoben_individual():
    return _reserve_base("标本馆", "个人")

# 校史馆团体预约
@h5_bp.route("/h5/reserve/xiaoshi/group", methods=["GET", "POST"])
@login_required
def reserve_xiaoshi_group():
    return _reserve_base("校史馆", "团队")

# 标本馆团体预约
@h5_bp.route("/h5/reserve/biaoben/group", methods=["GET", "POST"])
@login_required
def reserve_biaoben_group():
    return _reserve_base("标本馆", "团队")

@h5_bp.route("/h5/history")
@login_required
def history():
    # 检查用户是否存在
    user = User.query.get(session["user_id"])
    if not user:
        flash("用户信息不存在，请重新登录")
        session.clear()
        return redirect(url_for("h5.login"))
    
    reservations = (
        Reservation.query.filter_by(user_id=session["user_id"])
        .order_by(Reservation.created_at.desc())
        .all()
    )
    return render_template("h5_history.html", reservations=reservations)

@h5_bp.route("/h5/profile", methods=["GET", "POST"])
@login_required
def profile():
    # 检查用户是否存在
    user = User.query.get(session["user_id"])
    if not user:
        flash("用户信息不存在，请重新登录")
        session.clear()
        return redirect(url_for("h5.login"))

    if request.method == "POST":
        name = request.form.get("name")
        phone = request.form.get("phone")
        
        is_phone_valid, phone_msg = validate_phone(phone)
        if not is_phone_valid:
            flash(f"手机号错误：{phone_msg}")
            return render_template("h5_profile.html", user=user)
        
        user.name = name
        user.phone = phone
        db.session.commit()
        flash("个人信息已更新")
        return redirect(url_for("h5.home"))

    return render_template("h5_profile.html", user=user)
