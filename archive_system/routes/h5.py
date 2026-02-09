from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime
import os
import uuid
from ..extensions import db
from ..models import User, SystemConfig, Announcement, Reservation, Venue, VenueTimeSlot, Attachment
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

    # 获取默认场馆（第一个启用的场馆）
    default_venue = venues[0] if venues else None

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
            return render_template(f"h5_reserve_{venue_category}_{res_type}.html", user=user, venues=venues, venue=default_venue)

        # 验证预约日期
        is_date_valid, date_msg = validate_visit_date(visit_date)
        if not is_date_valid:
            flash(date_msg)
            return render_template(f"h5_reserve_{venue_category}_{res_type}.html", user=user, venues=venues, venue=default_venue)

        # 验证团体信息
        if res_type == "团队":
            if not group_name:
                flash("请输入团体名称")
                return render_template(f"h5_reserve_{venue_category}_{res_type}.html", user=user, venues=venues, venue=default_venue)
            if not group_contact:
                flash("请输入团体联系人")
                return render_template(f"h5_reserve_{venue_category}_{res_type}.html", user=user, venues=venues, venue=default_venue)

        # 检查用户当天是否已经有该场馆的申请（审核中或已批准）
        visit_date_obj = datetime.strptime(visit_date, "%Y-%m-%d").date()
        existing_reservations = Reservation.query.filter_by(
            user_id=session["user_id"],
            venue_id=campus_venue_id,
            visit_date=visit_date_obj
        ).filter(
            Reservation.status.in_(["待审核", "已同意"])
        ).count()
        
        if existing_reservations > 0:
            flash("您当天已经有该场馆的预约申请，请等待审核结果或选择其他日期")
            return render_template(f"h5_reserve_{venue_category}_{res_type}.html", user=user, venues=venues, venue=default_venue)

        # 获取该时段的容量配置
        day_of_week = visit_date_obj.weekday()
        time_slot_config = VenueTimeSlot.query.filter_by(
            venue_id=campus_venue_id,
            day_of_week=day_of_week,
            time_slot=visit_time,
            is_active=True
        ).first()
        
        if not time_slot_config:
            flash("所选时段未开放，请选择其他时段")
            return render_template(f"h5_reserve_{venue_category}_{res_type}.html", user=user, venues=venues, venue=default_venue)
        
        # 使用事务确保并发安全
        from sqlalchemy.exc import SQLAlchemyError
        
        try:
            
            # 重新获取时段配置（加锁）
            time_slot_config = VenueTimeSlot.query.filter_by(
                venue_id=campus_venue_id,
                day_of_week=day_of_week,
                time_slot=visit_time,
                is_active=True
            ).with_for_update().first()
            
            if not time_slot_config:
                db.session.rollback()
                flash("所选时段未开放，请选择其他时段")
                return render_template(f"h5_reserve_{venue_category}_{res_type}.html", user=user, venues=venues, venue=default_venue)
            
            # 只有个人预约需要检查名额
            if res_type == "个人":
                # 检查所选时段是否已满（包括已同意和审核中的申请），加锁
                time_slot_reservations = Reservation.query.filter_by(
                    venue_id=campus_venue_id,
                    visit_date=visit_date_obj,
                    visit_time=visit_time,
                    res_type="个人"
                ).filter(
                    Reservation.status.in_(["待审核", "已同意"])
                ).with_for_update().all()
                
                # 计算已预约人数
                reserved_individual = 0
                for res in time_slot_reservations:
                    reserved_individual += res.group_size
                
                if reserved_individual + group_size > time_slot_config.individual_capacity:
                    db.session.rollback()
                    flash(f"所选时段个人预约人数已满，请选择其他时段")
                    return render_template(f"h5_reserve_{venue_category}_{res_type}.html", user=user, venues=venues, venue=default_venue)

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
            db.session.flush()  # 获取res的ID，用于附件关联
            
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
                            db.session.rollback()
                            flash(f"文件 {file.filename} 超过15MB限制")
                            return render_template(f"h5_reserve_{venue_category}_{res_type}.html", user=user, venues=venues, venue=default_venue)
                        
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
            
            # 提交所有更改
            db.session.commit()
            
        except SQLAlchemyError as e:
            db.session.rollback()
            print(f"Error during reservation: {e}")
            flash("预约提交失败，请稍后重试")
            return render_template(f"h5_reserve_{venue_category}_{res_type}.html", user=user, venues=venues, venue=default_venue)

        print(f"【模拟微信通知】用户 {session['user_id']} 预约提交成功，等待审核。")
        flash("预约提交成功，请等待审核通知")
        return redirect(url_for("h5.history"))

    # GET请求时显示预约表单
    return render_template(f"h5_reserve_{venue_category}_{res_type}.html", user=user, venues=venues, venue=default_venue)

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

@h5_bp.route("/h5/api/available-slots")
@login_required
def get_available_slots():
    """获取可用时段和剩余名额"""
    try:
        venue_id = request.args.get("venue_id", type=int)
        visit_date = request.args.get("visit_date")
        
        if not venue_id or not visit_date:
            return {"error": "缺少必要参数"}, 400
        
        # 解析日期
        visit_date_obj = datetime.strptime(visit_date, "%Y-%m-%d").date()
        day_of_week = visit_date_obj.weekday()  # 0-6，0表示周一
        
        # 获取该场馆在该日期的所有时段
        time_slots = VenueTimeSlot.query.filter_by(
            venue_id=venue_id,
            day_of_week=day_of_week,
            is_active=True
        ).all()
        
        # 获取该场馆在该日期的已预约人数（已同意和待审核的）
        reservations = Reservation.query.filter_by(
            venue_id=venue_id,
            visit_date=visit_date_obj
        ).filter(
            Reservation.status.in_(["已同意", "待审核"])
        ).all()
        
        # 统计每个时段的已预约人数（只统计个人预约）
        slot_counts = {}
        for res in reservations:
            if res.res_type == "个人":
                if res.visit_time not in slot_counts:
                    slot_counts[res.visit_time] = 0
                slot_counts[res.visit_time] += res.group_size
        
        # 生成可用时段和剩余名额
        available_slots = []
        for slot in time_slots:
            used_individual = slot_counts.get(slot.time_slot, 0)
            remaining_individual = slot.individual_capacity - used_individual
            available_slots.append({
                "time_slot": slot.time_slot,
                "individual_capacity": slot.individual_capacity,
                "used_individual": used_individual,
                "remaining_individual": remaining_individual,
                "available_individual": remaining_individual > 0,
                "available_group": getattr(slot, 'is_group_active', True)  # 检查团体预约是否启用
            })
        
        return {"slots": available_slots}
    except Exception as e:
        print(f"Error in get_available_slots: {e}")
        return {"error": "获取可用时段失败"}, 500
