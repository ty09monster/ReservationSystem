from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime
from ..extensions import db
from ..models import User, SystemConfig, Announcement, Reservation
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

@h5_bp.route("/h5/reserve", methods=["GET", "POST"])
@login_required
def reserve():

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

    if request.method == "POST":
        area = request.form.get("area")
        visit_date = request.form.get("visit_date")
        visit_time = request.form.get("visit_time")
        reason = request.form.get("reason")
        res_type = request.form.get("res_type")
        identity = request.form.get("identity")

        is_date_valid, date_msg = validate_visit_date(visit_date)
        if not is_date_valid:
            flash(date_msg)
            campuses = config.campuses.split(",")
            times = config.visit_times.split(",")
            return render_template("h5_reserve.html", user=user, campuses=campuses, times=times)

        res = Reservation(
            user_id=session["user_id"],
            area=area,
            visit_date=datetime.strptime(visit_date, "%Y-%m-%d").date(),
            visit_time=visit_time,
            reason=reason,
            res_type=res_type,
            identity=identity,
        )
        db.session.add(res)
        db.session.commit()

        print(f"【模拟微信通知】用户 {session['user_id']} 预约提交成功，等待审核。")
        flash("预约提交成功，请等待审核通知")
        return redirect(url_for("h5.history"))

    campuses = config.campuses.split(",")
    times = config.visit_times.split(",")
    return render_template("h5_reserve.html", user=user, campuses=campuses, times=times)

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
