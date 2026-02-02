from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import or_, case
from ..extensions import db
from ..models import Admin, Reservation, User, Announcement, SystemConfig, Venue, Attachment

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
        admin_list=admin_list
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
        open_hours = request.form.get("venue_open_hours")
        daily_limit = request.form.get("venue_daily_limit", 50, type=int)
        individual_limit = request.form.get("venue_individual_limit", 20, type=int)
        group_limit = request.form.get("venue_group_limit", 30, type=int)
        group_min_size = request.form.get("venue_group_min_size", 2, type=int)
        group_max_size = request.form.get("venue_group_max_size", 50, type=int)
        advance_days = request.form.get("venue_advance_days", 7, type=int)
        cutoff_time = request.form.get("venue_cutoff_time", "16:00")
        is_active = "venue_is_active" in request.form
        
        venue = Venue.query.get(venue_id)
        if venue:
            venue.name = name
            venue.description = description
            venue.address = address
            venue.open_hours = open_hours
            venue.daily_limit = daily_limit
            venue.individual_limit = individual_limit
            venue.group_limit = group_limit
            venue.group_min_size = group_min_size
            venue.group_max_size = group_max_size
            venue.advance_days = advance_days
            venue.cutoff_time = cutoff_time
            venue.is_active = is_active
            flash("场馆设置更新成功")
        else:
            flash("场馆不存在")

    db.session.commit()
    return redirect(url_for("admin.dashboard"))

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
