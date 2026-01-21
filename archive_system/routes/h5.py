from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from ..extensions import db
from ..models import User, SystemConfig, Announcement, Reservation
from ..validators import validate_certificate, validate_phone, validate_visit_date

h5_bp = Blueprint('h5', __name__)

@h5_bp.route("/")
def index():
    return redirect(url_for("h5.login"))

@h5_bp.route("/h5/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
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
        return redirect(url_for("h5.home"))

    config = SystemConfig.query.first()
    policy_text = config.privacy_policy if config else "<p>暂无内容</p>"
    return render_template("h5_login.html", privacy_policy=policy_text)

@h5_bp.route("/h5/home")
def home():
    if "user_id" not in session:
        return redirect(url_for("h5.login"))

    user = User.query.get(session["user_id"])
    all_announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()
    config = SystemConfig.query.first()
    return render_template(
        "h5_home.html", 
        user=user, 
        all_announcements=all_announcements,
        config=config
    )

@h5_bp.route("/h5/reserve", methods=["GET", "POST"])
def reserve():
    if "user_id" not in session:
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
            user = User.query.get(session["user_id"])
            return render_template("h5_reserve.html", user=user, campuses=campuses, times=times)

        res = Reservation(
            user_id=session["user_id"],
            area=area,
            visit_date=visit_date,
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
    user = User.query.get(session["user_id"])
    return render_template("h5_reserve.html", user=user, campuses=campuses, times=times)

@h5_bp.route("/h5/history")
def history():
    if "user_id" not in session:
        return redirect(url_for("h5.login"))
    reservations = (
        Reservation.query.filter_by(user_id=session["user_id"])
        .order_by(Reservation.created_at.desc())
        .all()
    )
    return render_template("h5_history.html", reservations=reservations)

@h5_bp.route("/h5/profile", methods=["GET", "POST"])
def profile():
    if "user_id" not in session:
        return redirect(url_for("h5.login"))
    user = User.query.get(session["user_id"])

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
