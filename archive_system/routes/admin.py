import logging
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import or_, case, func
from ..extensions import db
from ..models import Admin, Reservation, User, Announcement, SystemConfig, Venue, VenueTimeSlot, Attachment, ArchiveRequest, VenueTimeSlotDisabledDate, CancelRequest

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

MIN_PASSWORD_LENGTH = 8  # 管理员密码最小长度

@admin_bp.before_request
def check_admin_status():
    """统一的管理员认证拦截器，所有非白名单路由均需通过此处验证。"""
    whitelist = {'admin.login', 'admin.logout', 'static', 'admin.get_cancel_request_detail'}
    if request.endpoint in whitelist:
        return  # 白名单路由直接放行

    # 未登录：拦截并重定向到登录页
    if not session.get("admin_logged_in"):
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"error": "请先登录"}), 401
        return redirect(url_for('admin.login'))

    # 已登录：校验 security_token，防止密码变更后旧 session 仍有效
    admin_id = session.get("admin_id")
    security_token = session.get("security_token")
    current_admin = db.session.get(Admin, admin_id)

    if not current_admin:
        session.clear()
        flash("您的账号已被删除，会话中断")
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"error": "账号已被删除"}), 401
        return redirect(url_for('admin.login'))

    if current_admin.password_hash and current_admin.password_hash[-6:] != security_token:
        session.clear()
        flash("密码已变更，请重新登录")
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"error": "密码已变更"}), 401
        return redirect(url_for('admin.login'))

@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        admin = Admin.query.filter_by(username=username).first()
        
        if admin and check_password_hash(admin.password_hash, password):
            session["admin_logged_in"] = True
            session["admin_id"] = admin.id
            session["is_super"] = admin.is_super
            session["security_token"] = admin.password_hash[-6:] 
            return redirect(url_for("admin.dashboard"))
            
        flash("用户名或密码错误")
    return render_template("admin_login.html")

@admin_bp.route("/dashboard")
def dashboard():

    keyword = request.args.get('keyword', '').strip()
    status_filter = request.args.get('status', '').strip()
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()
    page = request.args.get('page', 1, type=int)
    active_tab = request.args.get('active_tab', '')

    query = Reservation.query.join(User)

    if keyword:
        query = query.filter(
            or_(
                User.name.contains(keyword),
                User.phone.contains(keyword)
            )
        )

    if status_filter:
        query = query.filter(Reservation.status == status_filter)

    if start_date:
        query = query.filter(Reservation.visit_date >= start_date)

    if end_date:
        query = query.filter(Reservation.visit_date <= end_date)

    status_order = case(
        (Reservation.status == '待审核', 0),
        else_=1
    )
    query = query.order_by(status_order.asc(), Reservation.created_at.desc())

    pagination = query.paginate(page=page, per_page=10, error_out=False)
    reservations = pagination.items

    announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()
    config = SystemConfig.query.first()
    venues = Venue.query.all()

    admin_list = []
    if session.get("is_super"):
        admin_list = Admin.query.all()

    cancel_requests = []
    if active_tab == "cancel":
        cancel_page = request.args.get('cancel_page', 1, type=int)
        cancel_query = CancelRequest.query.join(Reservation).join(User).order_by(
            case(
                (CancelRequest.status == '待处理', 0),
                else_=1
            ),
            CancelRequest.created_at.desc()
        )
        cancel_pagination = cancel_query.paginate(page=cancel_page, per_page=10, error_out=False)
        cancel_requests = cancel_pagination.items

    pending_reservation_count = Reservation.query.filter_by(status='待审核').count()
    pending_archive_count = ArchiveRequest.query.filter(ArchiveRequest.status.in_(['待审核', '待处理'])).count()
    pending_cancel_count = CancelRequest.query.filter_by(status='待处理').count()

    return render_template(
        "admin_dashboard.html",
        reservations=reservations,
        pagination=pagination,
        announcements=announcements,
        config=config,
        venues=venues,
        curr_keyword=keyword,
        curr_status=status_filter,
        curr_start_date=start_date,
        curr_end_date=end_date,
        admin_list=admin_list,
        active_tab=active_tab,
        cancel_requests=cancel_requests if active_tab == "cancel" else [],
        pending_reservation_count=pending_reservation_count,
        pending_archive_count=pending_archive_count,
        pending_cancel_count=pending_cancel_count
    )

@admin_bp.route("/audit/<int:res_id>", methods=["POST"])
def audit(res_id):
    action = request.form.get("action")
    reject_reason = request.form.get("reject_reason", "")

    res = db.session.get(Reservation, res_id)
    if not res:
        flash("预约记录不存在")
        return redirect(url_for("admin.dashboard"))

    if res.status != '待审核':
        flash(f"操作被忽略：该预约已被处理 (当前状态: {res.status})")
        return redirect(url_for("admin.dashboard"))

    if action == "approve":
        res.status = "已同意"
        logger.info("预约 %s 已同意，用户 %s", res_id, res.user_id)
    elif action == "reject":
        res.status = "已拒绝"
        res.reject_reason = reject_reason
        logger.info("预约 %s 已拒绝，原因: %s", res_id, reject_reason)

    db.session.commit()
    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/config", methods=["POST"])
def config():

    config = SystemConfig.query.first()
    active_tab = request.form.get("active_tab", "config")

    if "toggle_system" in request.form:
        config.is_open = not config.is_open



    if "update_policy" in request.form:
        config.privacy_policy = request.form.get("privacy_policy")
        flash("隐私声明已更新")

    if "publish_notice" in request.form:
        title = request.form.get("title")
        content = request.form.get("content")
        # 检查内容长度，限制在5000字符以内
        if len(content) > 5000:
            flash("公告内容不能超过5000字符")
            return redirect(url_for("admin.dashboard", active_tab="notice"))
        new_notice = Announcement(title=title, content=content)
        db.session.add(new_notice)

    # 场馆管理
    if "update_venue" in request.form:
        venue_id = request.form.get("venue_id", type=int)
        name = request.form.get("venue_name")
        description = request.form.get("venue_description")
        address = request.form.get("venue_address")
        campus = request.form.get("venue_campus")
        parent_id = request.form.get("venue_parent_id", type=int)
        advance_days = request.form.get("venue_advance_days", 7, type=int)
        cutoff_time = request.form.get("venue_cutoff_time", "16:00")
        is_active = "venue_is_active" in request.form
        
        venue = Venue.query.get(venue_id)
        if venue:
            venue.name = name
            venue.description = description
            venue.address = address
            venue.campus = campus
            venue.parent_venue_id = parent_id
            venue.advance_days = advance_days
            venue.cutoff_time = cutoff_time
            venue.is_active = is_active
            flash("场馆设置更新成功")
        else:
            flash("场馆不存在")

    db.session.commit()
    return redirect(url_for("admin.dashboard", active_tab=active_tab))

@admin_bp.route("/handle-cancel-request/<int:req_id>", methods=["POST"])
def handle_cancel_request(req_id):
    """处理撤销申请"""
    action = request.form.get("action")
    remark = request.form.get("remark", "")

    cancel_req = db.session.get(CancelRequest, req_id)
    if not cancel_req:
        flash("撤销申请不存在")
        return redirect(url_for("admin.dashboard", active_tab="archive"))

    if cancel_req.status != '待处理':
        flash(f"该申请已被处理 (当前状态: {cancel_req.status})")
        return redirect(url_for("admin.dashboard", active_tab="archive"))

    reservation = db.session.get(Reservation, cancel_req.reservation_id)
    if not reservation:
        flash("关联的预约记录不存在")
        return redirect(url_for("admin.dashboard", active_tab="archive"))

    if action == 'approve':
        reservation_id = cancel_req.reservation_id
        user_id = cancel_req.user_id

        cancel_req.status = "已同意"
        cancel_req.admin_remark = remark
        cancel_req.processed_at = datetime.now()

        other_cancel_requests = CancelRequest.query.filter(
            CancelRequest.reservation_id == reservation_id,
            CancelRequest.id != req_id
        ).all()
        for other_req in other_cancel_requests:
            other_req.status = "已拒绝"
            other_req.admin_remark = "因预约已被撤销，该申请被自动拒绝"
            other_req.processed_at = datetime.now()

        db.session.commit()

        db.session.execute(db.text("DELETE FROM cancel_request WHERE reservation_id = :rid"), {"rid": reservation_id})
        db.session.execute(db.text("DELETE FROM reservation WHERE id = :rid"), {"rid": reservation_id})
        db.session.commit()

        logger.info("撤销申请 %s 已同意，预约 %s 已撤销，用户 %s",
                    req_id, reservation_id, user_id)
    elif action == 'reject':
        cancel_req.status = "已拒绝"
        cancel_req.admin_remark = remark
        cancel_req.processed_at = datetime.now()
        logger.info("撤销申请 %s 已拒绝，原因: %s", req_id, remark)
    else:
        flash("无效的操作")
        return redirect(url_for("admin.dashboard", active_tab="archive"))

    db.session.commit()
    flash(f"撤销申请已{'同意' if action == 'approve' else '拒绝'}")
    return redirect(url_for("admin.dashboard", active_tab="cancel"))

@admin_bp.route("/cancel-request/<int:req_id>")
def get_cancel_request_detail(req_id):
    """获取撤销申请详情API"""
    if not session.get("admin_logged_in"):
        return jsonify({"error": "请先登录"}), 401

    cancel_req = db.session.get(CancelRequest, req_id)
    if not cancel_req:
        return jsonify({"error": "撤销申请不存在"}), 404

    reservation = db.session.get(Reservation, cancel_req.reservation_id)
    if not reservation:
        return jsonify({"error": "关联的预约记录不存在"}), 404

    venue = db.session.get(Venue, reservation.venue_id) if reservation.venue_id else None

    return jsonify({
        "cancel_request": {
            "id": cancel_req.id,
            "created_at": cancel_req.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            "status": cancel_req.status,
            "reason": cancel_req.reason,
            "admin_remark": cancel_req.admin_remark,
            "user_name": cancel_req.user.name,
            "user_id_type": cancel_req.user.id_type,
            "user_id_card": cancel_req.user.id_card,
            "user_phone": cancel_req.user.phone,
            "venue_name": venue.name if venue else "未知",
            "visit_date": reservation.visit_date.strftime('%Y-%m-%d') if reservation.visit_date else "",
            "visit_time": reservation.visit_time
        }
    })

@admin_bp.route("/announcement/<int:ann_id>/toggle-pin", methods=["POST"])
def toggle_announcement_pin(ann_id):
    announcement = db.session.get(Announcement, ann_id)
    if announcement:
        announcement.is_pinned = not announcement.is_pinned
        db.session.commit()
        flash(f"公告{'已顶置' if announcement.is_pinned else '已取消顶置'}")
    else:
        flash("公告不存在")
    return redirect(url_for("admin.dashboard", active_tab="notice"))

@admin_bp.route("/announcement/<int:ann_id>/toggle-hide", methods=["POST"])
def toggle_announcement_hide(ann_id):
    announcement = db.session.get(Announcement, ann_id)
    if announcement:
        announcement.is_hidden = not announcement.is_hidden
        db.session.commit()
        flash(f"公告{'已隐藏' if announcement.is_hidden else '已显示'}")
    else:
        flash("公告不存在")
    return redirect(url_for("admin.dashboard", active_tab="notice"))

@admin_bp.route("/announcement/<int:ann_id>/delete", methods=["POST"])
def delete_announcement(ann_id):
    announcement = db.session.get(Announcement, ann_id)
    if announcement:
        db.session.delete(announcement)
        db.session.commit()
        flash("公告已删除")
    else:
        flash("公告不存在")
    return redirect(url_for("admin.dashboard", active_tab="notice"))

@admin_bp.route("/announcement/<int:ann_id>/edit", methods=["POST"])
def edit_announcement(ann_id):
    announcement = db.session.get(Announcement, ann_id)
    if announcement:
        title = request.form.get("title")
        content = request.form.get("content")
        if len(content) > 5000:
            flash("公告内容不能超过5000字符")
            return redirect(url_for("admin.dashboard", active_tab="notice"))
        announcement.title = title
        announcement.content = content
        db.session.commit()
        flash("公告已更新")
    else:
        flash("公告不存在")
    return redirect(url_for("admin.dashboard", active_tab="notice"))

@admin_bp.route("/account", methods=["POST"])
def account():
    action = request.form.get("action")

    if action == "change_own_password":
        new_pass = request.form.get("new_password", "")
        if len(new_pass) < MIN_PASSWORD_LENGTH:
            flash(f"密码长度不能少于 {MIN_PASSWORD_LENGTH} 位")
            return redirect(url_for("admin.dashboard", active_tab="account"))
        admin_id = session.get("admin_id")
        current_admin = db.session.get(Admin, admin_id)
        if not current_admin:
            session.clear()
            flash("账号异常，请重新登录")
            return redirect(url_for("admin.login"))
        current_admin.password_hash = generate_password_hash(new_pass)
        db.session.commit()
        flash("您的密码已修改，请重新登录")
        session.clear()
        return redirect(url_for("admin.login"))

    if not session.get("is_super"):
        flash("无权操作")
        return redirect(url_for("admin.dashboard", active_tab="account"))

    if action == "create_admin":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if len(password) < MIN_PASSWORD_LENGTH:
            flash(f"密码长度不能少于 {MIN_PASSWORD_LENGTH} 位")
            return redirect(url_for("admin.dashboard", active_tab="account"))
        if Admin.query.filter_by(username=username).first():
            flash("该用户名已存在")
        else:
            new_admin = Admin(
                username=username,
                password_hash=generate_password_hash(password),
                is_super=False
            )
            db.session.add(new_admin)
            db.session.commit()
            flash(f"普通管理员 {username} 创建成功")

    elif action == "delete_admin":
        admin_id = request.form.get("admin_id")
        target = db.session.get(Admin, admin_id)
        if target and not target.is_super:
            db.session.delete(target)
            db.session.commit()
            flash("管理员已删除")
        else:
            flash("删除失败：无法删除超级管理员或用户不存在")

    elif action == "reset_password":
        admin_id = request.form.get("admin_id")
        new_pass = request.form.get("new_password", "")
        if len(new_pass) < MIN_PASSWORD_LENGTH:
            flash(f"密码长度不能少于 {MIN_PASSWORD_LENGTH} 位")
            return redirect(url_for("admin.dashboard", active_tab="account"))
        target = db.session.get(Admin, admin_id)
        if target:
            target.password_hash = generate_password_hash(new_pass)
            db.session.commit()
            flash(f"管理员 {target.username} 的密码已重置")

    return redirect(url_for("admin.dashboard", active_tab="account"))

@admin_bp.route("/logout")
def logout():
    session.clear()
    flash("您已安全退出")
    return redirect(url_for("admin.login"))

@admin_bp.route("/stats")
def stats():
    return render_template("admin_stats.html")

@admin_bp.route("/time-slot-config", methods=["POST"])
def time_slot_config():
    
    venue_id = request.form.get("venue_id", type=int)
    active_tab = request.form.get("active_tab", "venue")
    if not venue_id:
        flash("场馆ID无效")
        return redirect(url_for("admin.dashboard", active_tab=active_tab))
    
    # 获取所有表单字段
    form_data = request.form
    
    # 提取所有时间段值
    time_slot_values = set()
    for key in form_data:
        if key.startswith('individual_capacity_'):
            # 提取时间段值
            parts = key.split('_')
            if len(parts) > 3:
                # 重组时间段值（处理包含下划线的时间段，如 09:00-10:30）
                time_slot = '_'.join(parts[2:-1])
                time_slot_values.add(time_slot)
    
    # 如果没有找到时段值，保持空时段状态
    # 不再使用默认时段，这样管理员可以完全删除所有时段
    # if not time_slot_values:
    #     time_slot_values = {"09:00-10:30", "10:30-12:00", "14:00-15:30", "15:30-17:00"}
    
    # 先删除该场馆的所有现有时段设置
    VenueTimeSlot.query.filter_by(venue_id=venue_id).delete()
    
    # 为每个时段创建新的设置
    for time_slot in time_slot_values:
        for day in range(7):
            individual_capacity_key = f"individual_capacity_{time_slot}_{day}"
            active_key = f"active_{time_slot}_{day}"
            is_group_active_key = f"is_group_active_{time_slot}_{day}"
            
            individual_capacity = request.form.get(individual_capacity_key, type=int)
            is_active = active_key in request.form
            is_group_active = is_group_active_key in request.form
            
            if individual_capacity:
                # 创建新记录
                new_slot = VenueTimeSlot(
                    venue_id=venue_id,
                    day_of_week=day,
                    time_slot=time_slot,
                    individual_capacity=individual_capacity,
                    is_group_active=is_group_active,
                    is_active=is_active
                )
                db.session.add(new_slot)
    
    db.session.commit()
    flash("时段设置更新成功")
    return redirect(url_for("admin.dashboard", active_tab=active_tab))

@admin_bp.route("/get-time-slots/<int:venue_id>")
def get_time_slots(venue_id):
    """获取场馆的时段设置"""
    
    # 获取该场馆的所有时段设置
    time_slots = VenueTimeSlot.query.filter_by(venue_id=venue_id).all()
    
    # 整理时段设置数据
    slot_data = {}
    for slot in time_slots:
        if slot.time_slot not in slot_data:
            slot_data[slot.time_slot] = {}
        slot_data[slot.time_slot][slot.day_of_week] = {
            "individual_capacity": slot.individual_capacity,
            "is_active": slot.is_active,
            "is_group_active": slot.is_group_active
        }
    
    return {"slots": slot_data}

@admin_bp.route("/get-attachments/<int:res_id>")
def get_attachments(res_id):
    reservation = db.session.get(Reservation, res_id)
    if not reservation:
        return {"attachments": []}
    
    # 构建附件信息列表
    attachments = []
    for attachment in reservation.attachments:
        attachments.append({
            "filename": attachment.filename,
            "filepath": attachment.filepath,
            "file_size": attachment.file_size
        })
    
    return {"attachments": attachments}

@admin_bp.route("/get-venues")
def get_venues():
    
    # 获取所有场馆
    venues = Venue.query.all()
    
    # 构建场馆列表
    venue_list = []
    for venue in venues:
        venue_list.append({
            "id": venue.id,
            "name": venue.name
        })
    
    return {"venues": venue_list}

# 统计数据API
@admin_bp.route("/stats/reservation-trend")
def reservation_trend():
    # 获取时间范围
    time_range = request.args.get("time_range", "month")
    
    # 构建查询
    query = Reservation.query
    
    # 按时间范围分组
    if time_range == "day":
        result = db.session.query(
            func.date(Reservation.created_at).label('date'),
            func.count(Reservation.id).label('count')
        ).group_by(func.date(Reservation.created_at)).order_by('date').all()
        data = {
            "labels": [item.date.strftime('%Y-%m-%d') for item in result],
            "values": [item.count for item in result]
        }
    elif time_range == "week":
        result = db.session.query(
            func.date_format(Reservation.created_at, '%Y-%u').label('week'),
            func.count(Reservation.id).label('count')
        ).group_by('week').order_by('week').all()
        data = {
            "labels": [item.week for item in result],
            "values": [item.count for item in result]
        }
    else:  # month
        result = db.session.query(
            func.date_format(Reservation.created_at, '%Y-%m').label('month'),
            func.count(Reservation.id).label('count')
        ).group_by('month').order_by('month').all()
        data = {
            "labels": [item.month for item in result],
            "values": [item.count for item in result]
        }
    return data

@admin_bp.route("/stats/reservation-status")
def reservation_status():
    result = db.session.query(
        Reservation.status,
        func.count(Reservation.id).label('count')
    ).group_by(Reservation.status).all()
    data = {
        "labels": [item.status for item in result],
        "values": [item.count for item in result]
    }
    return data

@admin_bp.route("/stats/venue-comparison")
def venue_comparison():
    result = db.session.query(
        Venue.campus,
        func.count(Reservation.id).label('count')
    ).join(Reservation, Venue.id == Reservation.venue_id).group_by(Venue.campus).all()
    data = {
        "labels": [item.campus for item in result],
        "values": [item.count for item in result]
    }
    return data

@admin_bp.route("/stats/reservation-type")
def reservation_type():
    result = db.session.query(
        Reservation.res_type,
        func.count(Reservation.id).label('count')
    ).group_by(Reservation.res_type).all()
    data = {
        "labels": [item.res_type for item in result],
        "values": [item.count for item in result]
    }
    return data

@admin_bp.route("/stats/visitor-trend")
def visitor_trend():
    time_range = request.args.get("time_range", "month")
    
    if time_range == "day":
        result = db.session.query(
            func.date(Reservation.visit_date).label('date'),
            func.sum(Reservation.group_size).label('count')
        ).filter(Reservation.status == "已同意").group_by(func.date(Reservation.visit_date)).order_by('date').all()
        data = {
            "labels": [item.date.strftime('%Y-%m-%d') for item in result],
            "values": [item.count for item in result]
        }
    elif time_range == "week":
        result = db.session.query(
            func.date_format(Reservation.visit_date, '%Y-%u').label('week'),
            func.sum(Reservation.group_size).label('count')
        ).filter(Reservation.status == "已同意").group_by('week').order_by('week').all()
        data = {
            "labels": [item.week for item in result],
            "values": [item.count for item in result]
        }
    else:  # month
        result = db.session.query(
            func.date_format(Reservation.visit_date, '%Y-%m').label('month'),
            func.sum(Reservation.group_size).label('count')
        ).filter(Reservation.status == "已同意").group_by('month').order_by('month').all()
        data = {
            "labels": [item.month for item in result],
            "values": [item.count for item in result]
        }
    return data

@admin_bp.route("/stats/peak-hours")
def peak_hours():
    result = db.session.query(
        Reservation.visit_time,
        func.sum(Reservation.group_size).label('count')
    ).filter(Reservation.status == "已同意").group_by(Reservation.visit_time).order_by('count').all()
    data = {
        "labels": [item.visit_time for item in result],
        "values": [item.count for item in result]
    }
    return data

@admin_bp.route("/stats/campus-comparison")
def campus_comparison():
    result = db.session.query(
        Venue.campus,
        func.sum(Reservation.group_size).label('count')
    ).join(Reservation, Venue.id == Reservation.venue_id).filter(Reservation.status == "已同意").group_by(Venue.campus).all()
    data = {
        "labels": [item.campus for item in result],
        "values": [item.count for item in result]
    }
    return data

@admin_bp.route("/stats/time-utilization")
def time_utilization():
    # 获取所有时段
    time_slots = VenueTimeSlot.query.distinct(VenueTimeSlot.time_slot).all()
    time_slot_list = [slot.time_slot for slot in time_slots]
    
    # 统计每个时段的使用情况
    utilization_data = []
    for time_slot in time_slot_list:
        # 计算该时段的总容量
        capacity = db.session.query(
            func.sum(VenueTimeSlot.individual_capacity)
        ).filter(VenueTimeSlot.time_slot == time_slot).scalar() or 0
        
        # 计算该时段的实际使用量
        usage = db.session.query(
            func.sum(Reservation.group_size)
        ).filter(
            Reservation.visit_time == time_slot,
            Reservation.status == "已同意"
        ).scalar() or 0
        
        # 计算利用率
        utilization = (usage / capacity * 100) if capacity > 0 else 0
        
        utilization_data.append({
            "time_slot": time_slot,
            "utilization": round(utilization, 2)
        })
    
    # 按利用率排序
    utilization_data.sort(key=lambda x: x["utilization"], reverse=True)
    
    data = {
        "labels": [item["time_slot"] for item in utilization_data],
        "values": [item["utilization"] for item in utilization_data]
    }
    
    return data

@admin_bp.route("/stats/total")
def total_statistics():
    # 总预约量
    total_reservations = db.session.query(
        func.count(Reservation.id)
    ).scalar() or 0
    
    # 已同意预约量
    approved_reservations = db.session.query(
        func.count(Reservation.id)
    ).filter(Reservation.status == "已同意").scalar() or 0
    
    # 总客流量
    total_visitors = db.session.query(
        func.sum(Reservation.group_size)
    ).filter(Reservation.status == "已同意").scalar() or 0
    
    # 平均时段利用率
    # 计算总容量
    total_capacity = db.session.query(
        func.sum(VenueTimeSlot.individual_capacity)
    ).scalar() or 0
    
    # 计算总使用量
    total_usage = db.session.query(
        func.sum(Reservation.group_size)
    ).filter(Reservation.status == "已同意").scalar() or 0
    
    # 计算平均利用率
    avg_utilization = (total_usage / total_capacity * 100) if total_capacity > 0 else 0
    
    data = {
        "total_reservations": total_reservations,
        "approved_reservations": approved_reservations,
        "total_visitors": total_visitors,
        "avg_utilization": round(avg_utilization, 2)
    }
    
    return data

@admin_bp.route("/archive-requests")
def archive_requests():
    status_filter = request.args.get('status', '').strip()
    page = request.args.get('page', 1, type=int)
    
    query = ArchiveRequest.query.join(User)
    
    if status_filter:
        query = query.filter(ArchiveRequest.status == status_filter)
    
    query = query.order_by(ArchiveRequest.created_at.desc())
    
    pagination = query.paginate(page=page, per_page=10, error_out=False)
    archive_requests = pagination.items
    
    return jsonify({
        "archive_requests": [
            {
                "id": req.id,
                "user_id": req.user_id,
                "user_name": req.user.name,
                "user_id_type": req.user.id_type,
                "user_id_card": req.user.id_card,
                "user_phone": req.user.phone,
                "user_email": req.user.email,
                "request_email": req.email,
                "status": req.status,
                "admin_remark": req.admin_remark,
                "created_at": req.created_at.strftime('%Y-%m-%d %H:%M') if req.created_at else '',
                "updated_at": req.updated_at.strftime('%Y-%m-%d %H:%M') if req.updated_at else ''
            }
            for req in archive_requests
        ],
        "pagination": {
            "page": pagination.page,
            "pages": pagination.pages,
            "has_prev": pagination.has_prev,
            "has_next": pagination.has_next,
            "total": pagination.total
        },
        "curr_status": status_filter
    })

@admin_bp.route("/archive-request/<int:req_id>", methods=["POST"])
def handle_archive_request(req_id):
    action = request.form.get("action")
    remark = request.form.get("remark", "")
    
    archive_req = db.session.get(ArchiveRequest, req_id)
    if not archive_req:
        return jsonify({"error": "申请记录不存在"}), 404
    
    if archive_req.status != '待处理':
        return jsonify({"error": f"该申请已被处理 (当前状态: {archive_req.status})"}), 400
    
    if action == 'approve':
        archive_req.status = "已处理"
        archive_req.admin_remark = remark
        logger.info("档案查询申请 %s 已处理，用户 %s", req_id, archive_req.user_id)
    elif action == 'reject':
        archive_req.status = "已拒绝"
        archive_req.admin_remark = remark
        logger.info("档案查询申请 %s 已拒绝，原因: %s", req_id, remark)
    else:
        return jsonify({"error": "无效的操作"}), 400
    
    db.session.commit()
    flash(f"申请已{'处理' if action == 'approve' else '拒绝'}")
    return redirect(url_for("admin.dashboard", active_tab="archive"))

@admin_bp.route("/get-disabled-dates/<int:venue_id>")
def get_disabled_dates(venue_id):
    """获取场馆的禁用日期设置"""
    disabled_dates = VenueTimeSlotDisabledDate.query.filter_by(venue_id=venue_id).all()
    disabled_list = []
    for item in disabled_dates:
        disabled_list.append({
            "id": item.id,
            "time_slot": item.time_slot,
            "disabled_date": item.disabled_date.strftime('%Y-%m-%d')
        })
    return {"disabled_dates": disabled_list}

@admin_bp.route("/disabled-date", methods=["POST"])
def manage_disabled_date():
    """添加或删除禁用日期"""
    action = request.form.get("action")
    venue_id = request.form.get("venue_id", type=int)
    time_slot = request.form.get("time_slot", "")
    disabled_date = request.form.get("disabled_date", "")
    active_tab = request.form.get("active_tab", "venue")

    if not venue_id:
        flash("场馆ID无效")
        return redirect(url_for("admin.dashboard", active_tab=active_tab))

    if action == "add":
        if not time_slot or not disabled_date:
            flash("请选择时段和日期")
            return redirect(url_for("admin.dashboard", active_tab=active_tab))

        existing = VenueTimeSlotDisabledDate.query.filter_by(
            venue_id=venue_id,
            time_slot=time_slot,
            disabled_date=disabled_date
        ).first()

        if existing:
            flash("该日期时段已被禁用")
            return redirect(url_for("admin.dashboard", active_tab=active_tab))

        new_disabled = VenueTimeSlotDisabledDate(
            venue_id=venue_id,
            time_slot=time_slot,
            disabled_date=disabled_date
        )
        db.session.add(new_disabled)
        flash("禁用日期添加成功")

    elif action == "delete":
        disabled_id = request.form.get("disabled_id", type=int)
        if disabled_id:
            disabled_record = db.session.get(VenueTimeSlotDisabledDate, disabled_id)
            if disabled_record:
                db.session.delete(disabled_record)
                flash("禁用日期已删除")
        else:
            flash("禁用记录ID无效")

    db.session.commit()
    return redirect(url_for("admin.dashboard", active_tab=active_tab))
