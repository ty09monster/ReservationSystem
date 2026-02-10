from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import or_, case
from ..extensions import db
from ..models import Admin, Reservation, User, Announcement, SystemConfig, Venue, VenueTimeSlot, Attachment

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.before_request
def check_admin_status():
    if request.endpoint not in ['admin.login', 'admin.logout', 'static']:
        if session.get("admin_logged_in"):
            admin_id = session.get("admin_id")
            security_token = session.get("security_token")
            
            current_admin = Admin.query.get(admin_id)
            
            if not current_admin:
                session.clear()
                flash("您的账号已被删除，会话中断")
                return redirect(url_for('admin.login'))
            
            if current_admin.password_hash and \
               current_admin.password_hash[-6:] != security_token:
                session.clear()
                flash("密码已变更，请重新登录")
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
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))

    keyword = request.args.get('keyword', '').strip()
    status_filter = request.args.get('status', '').strip()
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

    return render_template(
        "admin_dashboard.html",
        reservations=reservations,
        pagination=pagination,
        announcements=announcements,
        config=config,
        venues=venues,
        curr_keyword=keyword,
        curr_status=status_filter,
        admin_list=admin_list,
        active_tab=active_tab
    )

@admin_bp.route("/audit/<int:res_id>", methods=["POST"])
def audit(res_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))
    action = request.form.get("action")
    reject_reason = request.form.get("reject_reason", "")

    res = Reservation.query.get(res_id)
    if res.status != '待审核':
        flash(f"操作被忽略：该预约已被处理 (当前状态: {res.status})")
        return redirect(url_for("admin.dashboard"))

    if action == "approve":
        res.status = "已同意"
        print(f"【模拟微信通知】预约已同意。注意事项：请携带身份证入馆。")
    elif action == "reject":
        res.status = "已拒绝"
        res.reject_reason = reject_reason
        print(f"【模拟微信通知】预约被拒绝。原因：{reject_reason}")

    db.session.commit()
    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/config", methods=["POST"])
def config():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))

    config = SystemConfig.query.first()
    active_tab = request.form.get("active_tab", "venue")

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
            return redirect(url_for("admin.dashboard"))
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

@admin_bp.route("/announcement/<int:ann_id>/toggle-pin", methods=["POST"])
def toggle_announcement_pin(ann_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))
    
    announcement = Announcement.query.get(ann_id)
    if announcement:
        announcement.is_pinned = not announcement.is_pinned
        db.session.commit()
        flash(f"公告{'已顶置' if announcement.is_pinned else '已取消顶置'}")
    else:
        flash("公告不存在")
    
    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/announcement/<int:ann_id>/toggle-hide", methods=["POST"])
def toggle_announcement_hide(ann_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))
    
    announcement = Announcement.query.get(ann_id)
    if announcement:
        announcement.is_hidden = not announcement.is_hidden
        db.session.commit()
        flash(f"公告{'已隐藏' if announcement.is_hidden else '已显示'}")
    else:
        flash("公告不存在")
    
    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/announcement/<int:ann_id>/delete", methods=["POST"])
def delete_announcement(ann_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))
    
    announcement = Announcement.query.get(ann_id)
    if announcement:
        db.session.delete(announcement)
        db.session.commit()
        flash("公告已删除")
    else:
        flash("公告不存在")
    
    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/announcement/<int:ann_id>/edit", methods=["POST"])
def edit_announcement(ann_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))
    
    announcement = Announcement.query.get(ann_id)
    if announcement:
        title = request.form.get("title")
        content = request.form.get("content")
        
        # 检查内容长度，限制在5000字符以内
        if len(content) > 5000:
            flash("公告内容不能超过5000字符")
            return redirect(url_for("admin.dashboard"))
        
        announcement.title = title
        announcement.content = content
        db.session.commit()
        flash("公告已更新")
    else:
        flash("公告不存在")
    
    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/account", methods=["POST"])
def account():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))

    action = request.form.get("action")
    
    if action == "change_own_password":
        new_pass = request.form.get("new_password")
        if new_pass:
            admin_id = session.get("admin_id")
            current_admin = Admin.query.get(admin_id)
            
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
        return redirect(url_for("admin.dashboard"))

    if action == "create_admin":
        username = request.form.get("username")
        password = request.form.get("password")
        if Admin.query.filter_by(username=username).first():
            flash("该用户名已存在")
        else:
            new_admin = Admin(username=username, password_hash=generate_password_hash(password), is_super=False)
            db.session.add(new_admin)
            db.session.commit()
            flash(f"普通管理员 {username} 创建成功")

    elif action == "delete_admin":
        admin_id = request.form.get("admin_id")
        target = Admin.query.get(admin_id)
        if target and not target.is_super:
            db.session.delete(target)
            db.session.commit()
            flash("管理员已删除")
        else:
            flash("删除失败：无法删除超级管理员或用户不存在")

    elif action == "reset_password":
        admin_id = request.form.get("admin_id")
        new_pass = request.form.get("new_password")
        target = Admin.query.get(admin_id)
        if target:
            target.password_hash = generate_password_hash(new_pass)
            db.session.commit()
            flash(f"管理员 {target.username} 的密码已重置")

    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/logout")
def logout():
    session.clear()
    flash("您已安全退出")
    return redirect(url_for("admin.login"))

@admin_bp.route("/stats")
def stats():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))
    
    return render_template("admin_stats.html")

@admin_bp.route("/time-slot-config", methods=["POST"])
def time_slot_config():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin.login"))
    
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
    if not session.get("admin_logged_in"):
        return {"error": "未登录"}, 401
    
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
    if not session.get("admin_logged_in"):
        return {"attachments": []}
    
    # 获取预约的附件
    reservation = Reservation.query.get(res_id)
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
    if not session.get("admin_logged_in"):
        return {"error": "未登录"}, 401
    
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
    if not session.get("admin_logged_in"):
        return {"error": "未登录"}, 401
    
    # 获取时间范围
    time_range = request.args.get("time_range", "month")
    
    # 构建查询
    query = Reservation.query
    
    # 按时间范围分组
    if time_range == "day":
        # 按日统计
        from sqlalchemy import func
        result = db.session.query(
            func.date(Reservation.created_at).label('date'),
            func.count(Reservation.id).label('count')
        ).group_by(func.date(Reservation.created_at)).order_by('date').all()
        
        data = {
            "labels": [item.date.strftime('%Y-%m-%d') for item in result],
            "values": [item.count for item in result]
        }
    elif time_range == "week":
        # 按周统计
        from sqlalchemy import func
        # 使用MySQL的DATE_FORMAT函数代替strftime
        result = db.session.query(
            func.date_format(Reservation.created_at, '%Y-%u').label('week'),
            func.count(Reservation.id).label('count')
        ).group_by('week').order_by('week').all()
        
        data = {
            "labels": [item.week for item in result],
            "values": [item.count for item in result]
        }
    else:  # month
        # 按月统计
        from sqlalchemy import func
        # 使用MySQL的DATE_FORMAT函数代替strftime
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
    if not session.get("admin_logged_in"):
        return {"error": "未登录"}, 401
    
    # 统计预约状态分布
    from sqlalchemy import func
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
    if not session.get("admin_logged_in"):
        return {"error": "未登录"}, 401
    
    # 统计场馆/校区对比
    from sqlalchemy import func
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
    if not session.get("admin_logged_in"):
        return {"error": "未登录"}, 401
    
    # 统计个人/团体比例
    from sqlalchemy import func
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
    if not session.get("admin_logged_in"):
        return {"error": "未登录"}, 401
    
    # 获取时间范围
    time_range = request.args.get("time_range", "month")
    
    # 构建查询
    query = Reservation.query.filter(Reservation.status == "已同意")
    
    # 按时间范围分组
    if time_range == "day":
        # 按日统计
        from sqlalchemy import func
        result = db.session.query(
            func.date(Reservation.visit_date).label('date'),
            func.sum(Reservation.group_size).label('count')
        ).filter(Reservation.status == "已同意").group_by(func.date(Reservation.visit_date)).order_by('date').all()
        
        data = {
            "labels": [item.date.strftime('%Y-%m-%d') for item in result],
            "values": [item.count for item in result]
        }
    elif time_range == "week":
        # 按周统计
        from sqlalchemy import func
        # 使用MySQL的DATE_FORMAT函数代替strftime
        result = db.session.query(
            func.date_format(Reservation.visit_date, '%Y-%u').label('week'),
            func.sum(Reservation.group_size).label('count')
        ).filter(Reservation.status == "已同意").group_by('week').order_by('week').all()
        
        data = {
            "labels": [item.week for item in result],
            "values": [item.count for item in result]
        }
    else:  # month
        # 按月统计
        from sqlalchemy import func
        # 使用MySQL的DATE_FORMAT函数代替strftime
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
    if not session.get("admin_logged_in"):
        return {"error": "未登录"}, 401
    
    # 统计高峰时段
    from sqlalchemy import func
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
    if not session.get("admin_logged_in"):
        return {"error": "未登录"}, 401
    
    # 统计校区客流对比
    from sqlalchemy import func
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
    if not session.get("admin_logged_in"):
        return {"error": "未登录"}, 401
    
    # 统计时段利用率
    from sqlalchemy import func
    
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
    if not session.get("admin_logged_in"):
        return {"error": "未登录"}, 401
    
    # 统计总数据
    from sqlalchemy import func
    
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
