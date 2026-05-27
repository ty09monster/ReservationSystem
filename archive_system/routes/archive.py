import logging
from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import check_password_hash
from sqlalchemy import or_, and_, func
from ..extensions import db
from ..models import ApprovalStaff, Reservation, User, Venue, Guide

logger = logging.getLogger(__name__)

archive_bp = Blueprint('archive', __name__, url_prefix='/archive')

STATUS_LABEL_MAP = {
    '待部门领导指定审批人': '待指定审批人',
    '待审核': '待审批',
    '已同意': '已通过',
    '已拒绝': '已拒绝',
    '已核销': '已核销',
    '已完成': '已完成',
    '已取消': '已取消',
}


@archive_bp.before_request
def check_archive_auth():
    whitelist = {'archive.login', 'archive.logout', 'static'}
    if request.endpoint in whitelist:
        return

    if not session.get("archive_logged_in"):
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"error": "请先登录"}), 401
        return redirect(url_for('archive.login'))

    staff_id = session.get("archive_staff_id")
    security_token = session.get("archive_security_token")
    current_staff = db.session.get(ApprovalStaff, staff_id)

    if not current_staff:
        session.pop("archive_logged_in", None)
        flash("您的账号已被删除，会话中断")
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"error": "账号已被删除"}), 401
        return redirect(url_for('archive.login'))

    if not current_staff.is_active:
        session.pop("archive_logged_in", None)
        flash("您的账号已被禁用")
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"error": "账号已被禁用"}), 401
        return redirect(url_for('archive.login'))

    if current_staff.password_hash and current_staff.password_hash[-6:] != security_token:
        session.pop("archive_logged_in", None)
        flash("密码已变更，请重新登录")
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"error": "密码已变更"}), 401
        return redirect(url_for('archive.login'))


@archive_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        staff = ApprovalStaff.query.filter_by(username=username).first()

        if staff and staff.is_active and check_password_hash(staff.password_hash, password):
            venue_ids = staff.get_assigned_venue_ids()
            if venue_ids:
                categories = {row[0] for row in db.session.query(Venue.category).filter(Venue.id.in_(venue_ids)).all()}
                if '档案馆' not in categories:
                    flash("该账号非档案馆审批人员，请前往校史馆审批端登录")
                    return render_template("archive_login.html")

            session["archive_logged_in"] = True
            session["archive_staff_id"] = staff.id
            session["archive_username"] = staff.username
            session["archive_name"] = staff.name
            session["archive_staff_type"] = staff.staff_type
            session["archive_security_token"] = staff.password_hash[-6:]

            if staff.staff_type == 'leader':
                return redirect(url_for("archive.leader_dashboard"))
            return redirect(url_for("archive.dashboard"))

        flash("用户名或密码错误，或账号已被禁用")
    return render_template("archive_login.html")


def _get_assigned_venue_ids():
    staff_id = session.get("archive_staff_id")
    if not staff_id:
        return []
    staff = db.session.get(ApprovalStaff, staff_id)
    if not staff:
        return []
    return staff.get_assigned_venue_ids()


def _get_current_staff():
    staff_id = session.get("archive_staff_id")
    if not staff_id:
        return None
    return db.session.get(ApprovalStaff, staff_id)


# ============================================================
# 档案馆教师审批端 - 审批列表
# ============================================================

@archive_bp.route("/dashboard")
def dashboard():
    staff = _get_current_staff()
    if not staff or staff.staff_type == 'leader':
        return redirect(url_for('archive.leader_dashboard'))

    keyword = request.args.get('keyword', '').strip()
    status_filter = request.args.get('status', '').strip()
    res_type_filter = request.args.get('res_type', '').strip()
    visit_type_filter = request.args.get('visit_type', '').strip()
    time_range = request.args.get('time_range', '').strip()
    custom_start = request.args.get('start_date', '').strip()
    custom_end = request.args.get('end_date', '').strip()
    page = request.args.get('page', 1, type=int)

    query = Reservation.query.join(User).join(Venue).filter(
        Reservation.approval_teacher_id == staff.id,
        Venue.category == '档案馆'
    )

    if keyword:
        query = query.filter(
            or_(
                User.name.contains(keyword),
                User.phone.contains(keyword),
                Reservation.group_name.contains(keyword),
                Reservation.visiting_unit.contains(keyword)
            )
        )

    if status_filter:
        query = query.filter(Reservation.status == status_filter)

    if res_type_filter:
        query = query.filter(Reservation.res_type == res_type_filter)

    if visit_type_filter:
        query = query.filter(Reservation.visit_type == visit_type_filter)

    if time_range == 'week':
        query = query.filter(Reservation.created_at >= datetime.now() - timedelta(days=7))
    elif time_range == 'month':
        query = query.filter(Reservation.created_at >= datetime.now() - timedelta(days=30))
    elif time_range == 'quarter':
        query = query.filter(Reservation.created_at >= datetime.now() - timedelta(days=90))
    elif time_range == 'custom':
        if custom_start:
            query = query.filter(func.date(Reservation.created_at) >= custom_start)
        if custom_end:
            query = query.filter(func.date(Reservation.created_at) <= custom_end)

    query = query.order_by(Reservation.created_at.desc())

    pagination = query.paginate(page=page, per_page=15, error_out=False)
    reservations = pagination.items

    leader_map = {}
    for res in reservations:
        if res.leader_id:
            leader = db.session.get(ApprovalStaff, res.leader_id)
            leader_map[res.id] = leader.name if leader else ''

    return render_template(
        "teacher_dashboard.html",
        reservations=reservations,
        pagination=pagination,
        leader_map=leader_map,
        area_label="档案馆",
        curr_keyword=keyword,
        curr_status=status_filter,
        curr_res_type=res_type_filter,
        curr_visit_type=visit_type_filter,
        curr_time_range=time_range,
        curr_start_date=custom_start,
        curr_end_date=custom_end,
        status_label_map=STATUS_LABEL_MAP,
        bp_prefix="/archive",
        bp_name="archive",
    )


# ============================================================
# 档案馆教师审批端 - 预约详情
# ============================================================

@archive_bp.route("/reservation/<int:res_id>")
def reservation_detail(res_id):
    res = db.session.get(Reservation, res_id)
    if not res:
        return jsonify({"error": "预约记录不存在"}), 404

    attachments = []
    for att in res.attachments:
        attachments.append({
            "filename": att.filename,
            "filepath": att.filepath,
            "file_size": att.file_size
        })

    leader_name = ''
    leader_opinion = res.leader_opinion or ''
    if res.leader_id:
        leader = db.session.get(ApprovalStaff, res.leader_id)
        leader_name = leader.name if leader else ''

    return jsonify({
        "id": res.id,
        "user_name": res.user.name,
        "user_phone": res.user.phone,
        "user_email": res.user.email or '',
        "user_id_type": res.user.id_type,
        "user_id_card": res.user.id_card,
        "identity": res.identity or '',
        "res_type": res.res_type,
        "group_name": res.group_name or '',
        "group_contact": res.group_contact or '',
        "group_size": res.group_size or 0,
        "visiting_unit": res.visiting_unit or '',
        "contact_phone": res.contact_phone or '',
        "visitor_count": res.visitor_count or 1,
        "license_plate": res.license_plate or '',
        "need_guide": res.need_guide,
        "visit_date": res.visit_date.strftime('%Y-%m-%d') if res.visit_date else '',
        "visit_time": res.visit_time or '',
        "venue_name": res.venue.name,
        "campus": res.campus or '',
        "reason": res.reason or '',
        "archive_name": res.archive_name or '',
        "archive_number": res.archive_number or '',
        "archive_purpose": res.archive_purpose or '',
        "visit_type": res.visit_type or '',
        "status": res.status,
        "reject_reason": res.reject_reason or '',
        "guide_info": res.guide_info or '',
        "verified_at": res.verified_at.strftime('%Y-%m-%d %H:%M') if res.verified_at else '',
        "verify_note": res.verify_note or '',
        "created_at": res.created_at.strftime('%Y-%m-%d %H:%M'),
        "leader_name": leader_name,
        "leader_opinion": leader_opinion,
        "attachments": attachments
    })


# ============================================================
# 档案馆教师审批端 - 审批操作（同意/拒绝/核销）
# ============================================================

@archive_bp.route("/audit/<int:res_id>", methods=["POST"])
def audit(res_id):
    action = request.form.get("action")
    reject_reason = request.form.get("reject_reason", "")
    guide_info = request.form.get("guide_info", "").strip()
    verify_note = request.form.get("verify_note", "").strip()

    res = db.session.get(Reservation, res_id)
    if not res:
        flash("预约记录不存在")
        return redirect(url_for("archive.dashboard"))

    if action == "approve":
        if res.status != '待审核':
            flash(f"操作被忽略：该预约已被处理 (当前状态: {res.status})")
            return redirect(url_for("archive.dashboard"))
        res.status = "已同意"
        if guide_info:
            res.guide_info = guide_info
    elif action == "reject":
        if res.status != '待审核':
            flash(f"操作被忽略：该预约已被处理 (当前状态: {res.status})")
            return redirect(url_for("archive.dashboard"))
        if not reject_reason.strip():
            flash("拒绝理由不能为空")
            return redirect(url_for("archive.dashboard"))
        res.status = "已拒绝"
        res.reject_reason = reject_reason
    elif action == "verify":
        if res.status != '已同意':
            flash(f"操作被忽略：只能核销已通过的预约 (当前状态: {res.status})")
            return redirect(url_for("archive.dashboard"))
        if res.visit_date and res.visit_date > date.today():
            flash("操作被忽略：只能核销参观日期已过的预约")
            return redirect(url_for("archive.dashboard"))
        res.status = "已核销"
        res.verified_at = datetime.now()
        res.verified_by = session.get("archive_staff_id")
        if verify_note:
            res.verify_note = verify_note
    else:
        flash("无效的操作")
        return redirect(url_for("archive.dashboard"))

    db.session.commit()
    return redirect(url_for("archive.dashboard"))


# ============================================================
# 档案馆教师审批端 - 统计API
# ============================================================

@archive_bp.route("/api/stats")
def api_stats():
    period = request.args.get('period', 'today')
    today = date.today()
    staff_id = session.get("archive_staff_id")

    if period == 'today':
        start = today
        end = today
    elif period == 'week':
        start = today - timedelta(days=today.weekday())
        end = today
    elif period == 'month':
        start = today.replace(day=1)
        end = today
    elif period == 'year':
        start = today.replace(month=1, day=1)
        end = today
    else:
        start = today
        end = today

    if start == end:
        date_cond = func.date(Reservation.created_at) == start
    else:
        date_cond = func.date(Reservation.created_at).between(start, end)

    teacher_cond = and_(Reservation.approval_teacher_id == staff_id, Venue.category == '档案馆')

    def _count(extra_cond=None):
        filters = [date_cond, teacher_cond]
        if extra_cond is not None:
            filters.append(extra_cond)
        return db.session.query(func.count(Reservation.id)).filter(*filters).scalar() or 0

    total_count = _count()
    pending_count = _count(Reservation.status == '待审核')
    approved_count = _count(Reservation.status == '已同意')
    group_count = _count(Reservation.res_type == '单位')
    individual_count = _count(Reservation.res_type == '个人')
    verified_count = _count(Reservation.status == '已核销')
    rejected_count = _count(Reservation.status == '已拒绝')
    completed_count = _count(Reservation.status == '已完成')

    return jsonify({
        "period": period,
        "start_date": start.strftime('%Y-%m-%d'),
        "end_date": end.strftime('%Y-%m-%d'),
        "total_count": total_count,
        "pending_count": pending_count,
        "approved_count": approved_count,
        "group_count": group_count,
        "individual_count": individual_count,
        "verified_count": verified_count,
        "rejected_count": rejected_count,
        "completed_count": completed_count,
    })


@archive_bp.route("/stats")
def stats_page():
    return render_template("teacher_stats.html", area_label="档案馆", bp_prefix="/archive", bp_name="archive")


@archive_bp.route("/stats/reservation-trend")
def archive_reservation_trend():
    time_range = request.args.get("time_range", "month")
    staff_id = session.get("archive_staff_id")
    teacher_cond = and_(Reservation.approval_teacher_id == staff_id, Venue.category == '档案馆')

    if time_range == "day":
        result = db.session.query(
            func.date(Reservation.created_at).label('date'),
            func.count(Reservation.id).label('count')
        ).filter(teacher_cond).group_by(
            func.date(Reservation.created_at)
        ).order_by('date').all()
        data = {
            "labels": [item.date.strftime('%Y-%m-%d') for item in result],
            "values": [item.count for item in result]
        }
    elif time_range == "week":
        result = db.session.query(
            func.date_format(Reservation.created_at, '%Y-%u').label('week'),
            func.count(Reservation.id).label('count')
        ).filter(teacher_cond).group_by('week').order_by('week').all()
        data = {
            "labels": [item.week for item in result],
            "values": [item.count for item in result]
        }
    else:
        result = db.session.query(
            func.date_format(Reservation.created_at, '%Y-%m').label('month'),
            func.count(Reservation.id).label('count')
        ).filter(teacher_cond).group_by('month').order_by('month').all()
        data = {
            "labels": [item.month for item in result],
            "values": [item.count for item in result]
        }
    return data


@archive_bp.route("/stats/reservation-status")
def archive_reservation_status():
    staff_id = session.get("archive_staff_id")
    result = db.session.query(
        Reservation.status,
        func.count(Reservation.id).label('count')
    ).select_from(Reservation).join(Venue).filter(
        Reservation.approval_teacher_id == staff_id,
        Venue.category == '档案馆'
    ).group_by(Reservation.status).all()
    return {
        "labels": [item.status for item in result],
        "values": [item.count for item in result]
    }


@archive_bp.route("/stats/reservation-type")
def archive_reservation_type():
    staff_id = session.get("archive_staff_id")
    result = db.session.query(
        Reservation.res_type,
        func.count(Reservation.id).label('count')
    ).select_from(Reservation).join(Venue).filter(
        Reservation.approval_teacher_id == staff_id,
        Venue.category == '档案馆'
    ).group_by(Reservation.res_type).all()
    return {
        "labels": [item.res_type for item in result],
        "values": [item.count for item in result]
    }


@archive_bp.route("/api/guide-list")
def api_guide_list():
    guides = Guide.query.filter_by(status='在岗').order_by(Guide.name).all()
    return jsonify({
        "guides": [{"name": g.name, "id": g.id} for g in guides]
    })


# ============================================================
# 档案馆领导审批端
# ============================================================

@archive_bp.route("/leader/dashboard")
def leader_dashboard():
    staff = _get_current_staff()
    if not staff or staff.staff_type != 'leader':
        flash("您没有部门领导权限")
        return redirect(url_for('archive.dashboard'))

    return render_template("leader_dashboard.html", area_label="档案馆", bp_prefix="/archive", bp_name="archive")


@archive_bp.route("/leader/api/reservations")
def leader_api_reservations():
    staff = _get_current_staff()
    if not staff or staff.staff_type != 'leader':
        return jsonify({"error": "无权限"}), 403

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 15, type=int)
    keyword = request.args.get('keyword', '').strip()
    status_filter = request.args.get('status', '').strip()
    res_type_filter = request.args.get('res_type', '').strip()
    visit_type_filter = request.args.get('visit_type', '').strip()
    time_range = request.args.get('time_range', '').strip()
    custom_start = request.args.get('start_date', '').strip()
    custom_end = request.args.get('end_date', '').strip()

    assigned_ids = _get_assigned_venue_ids()

    query = Reservation.query.join(User).join(Venue)

    if assigned_ids:
        query = query.filter(Reservation.venue_id.in_(assigned_ids))

    if keyword:
        query = query.filter(
            or_(
                User.name.contains(keyword),
                User.phone.contains(keyword),
                Reservation.group_name.contains(keyword),
                Reservation.visiting_unit.contains(keyword)
            )
        )

    if status_filter:
        if status_filter == 'pending_assign':
            query = query.filter(Reservation.status == '待部门领导指定审批人')
        elif status_filter == 'assigned':
            query = query.filter(Reservation.status == '待审核')
        elif status_filter == 'completed':
            query = query.filter(Reservation.status.in_(['已同意', '已拒绝', '已核销', '已完成', '已取消']))
        else:
            query = query.filter(Reservation.status == status_filter)

    if res_type_filter:
        query = query.filter(Reservation.res_type == res_type_filter)

    if visit_type_filter:
        query = query.filter(Reservation.visit_type == visit_type_filter)

    if time_range == 'week':
        query = query.filter(Reservation.created_at >= datetime.now() - timedelta(days=7))
    elif time_range == 'month':
        query = query.filter(Reservation.created_at >= datetime.now() - timedelta(days=30))
    elif time_range == 'quarter':
        query = query.filter(Reservation.created_at >= datetime.now() - timedelta(days=90))
    elif time_range == 'custom':
        if custom_start:
            query = query.filter(func.date(Reservation.created_at) >= custom_start)
        if custom_end:
            query = query.filter(func.date(Reservation.created_at) <= custom_end)

    query = query.order_by(Reservation.created_at.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    reservations_data = []
    for r in pagination.items:
        teacher_name = ''
        if r.approval_teacher_id:
            teacher = db.session.get(ApprovalStaff, r.approval_teacher_id)
            teacher_name = teacher.name if teacher else ''

        leader_name = ''
        if r.leader_id:
            leader = db.session.get(ApprovalStaff, r.leader_id)
            leader_name = leader.name if leader else ''

        reservations_data.append({
            "id": r.id,
            "user_name": r.user.name,
            "user_phone": r.user.phone,
            "res_type": r.res_type,
            "group_name": r.group_name or '',
            "visiting_unit": r.visiting_unit or '',
            "visitor_count": r.visitor_count or 1,
            "venue_name": r.venue.name,
            "venue_category": r.venue.category,
            "visit_date": r.visit_date.strftime('%Y-%m-%d') if r.visit_date else '',
            "visit_time": r.visit_time or '',
            "status": r.status,
            "reject_reason": r.reject_reason or '',
            "created_at": r.created_at.strftime('%Y-%m-%d %H:%M'),
            "approval_teacher_name": teacher_name,
            "leader_name": leader_name,
            "visit_type": r.visit_type or '',
        })

    return jsonify({
        "reservations": reservations_data,
        "pagination": {
            "page": pagination.page,
            "pages": pagination.pages,
            "has_prev": pagination.has_prev,
            "has_next": pagination.has_next,
            "total": pagination.total
        }
    })


@archive_bp.route("/leader/reservation/<int:res_id>")
def leader_reservation_detail(res_id):
    res = db.session.get(Reservation, res_id)
    if not res:
        return jsonify({"error": "预约记录不存在"}), 404

    attachments = []
    for att in res.attachments:
        attachments.append({
            "filename": att.filename,
            "filepath": att.filepath,
            "file_size": att.file_size
        })

    teacher_name = ''
    if res.approval_teacher_id:
        teacher = db.session.get(ApprovalStaff, res.approval_teacher_id)
        teacher_name = teacher.name if teacher else ''

    return jsonify({
        "id": res.id,
        "user_name": res.user.name,
        "user_phone": res.user.phone,
        "user_email": res.user.email or '',
        "user_id_type": res.user.id_type,
        "user_id_card": res.user.id_card,
        "identity": res.identity or '',
        "res_type": res.res_type,
        "group_name": res.group_name or '',
        "group_contact": res.group_contact or '',
        "group_size": res.group_size or 0,
        "visiting_unit": res.visiting_unit or '',
        "contact_phone": res.contact_phone or '',
        "visitor_count": res.visitor_count or 1,
        "license_plate": res.license_plate or '',
        "need_guide": res.need_guide,
        "visit_date": res.visit_date.strftime('%Y-%m-%d') if res.visit_date else '',
        "visit_time": res.visit_time or '',
        "venue_name": res.venue.name,
        "venue_category": res.venue.category,
        "campus": res.campus or '',
        "reason": res.reason or '',
        "archive_name": res.archive_name or '',
        "archive_number": res.archive_number or '',
        "archive_purpose": res.archive_purpose or '',
        "visit_type": res.visit_type or '',
        "status": res.status,
        "reject_reason": res.reject_reason or '',
        "leader_opinion": res.leader_opinion or '',
        "guide_info": res.guide_info or '',
        "verified_at": res.verified_at.strftime('%Y-%m-%d %H:%M') if res.verified_at else '',
        "created_at": res.created_at.strftime('%Y-%m-%d %H:%M'),
        "approval_teacher_name": teacher_name,
        "attachments": attachments
    })


@archive_bp.route("/leader/assign/<int:res_id>", methods=["POST"])
def leader_assign(res_id):
    staff = _get_current_staff()
    if not staff or staff.staff_type != 'leader':
        return jsonify({"error": "无权限"}), 403

    teacher_id = request.form.get("teacher_id", type=int)
    opinion = request.form.get("opinion", "").strip()

    if not teacher_id:
        flash("请选择审批教师")
        return redirect(url_for("archive.leader_dashboard"))

    res = db.session.get(Reservation, res_id)
    if not res:
        flash("预约记录不存在")
        return redirect(url_for("archive.leader_dashboard"))

    if res.status != '待部门领导指定审批人':
        flash(f"操作被忽略：当前状态为 {res.status}")
        return redirect(url_for("archive.leader_dashboard"))

    res.approval_teacher_id = teacher_id
    res.leader_id = staff.id
    res.leader_opinion = opinion
    res.status = '待审核'
    res.assigned_at = datetime.now()

    db.session.commit()
    flash(f"已指定审批教师，预约进入待审核状态")
    return redirect(url_for("archive.leader_dashboard"))


@archive_bp.route("/leader/reject/<int:res_id>", methods=["POST"])
def leader_reject(res_id):
    staff = _get_current_staff()
    if not staff or staff.staff_type != 'leader':
        return jsonify({"error": "无权限"}), 403

    reject_reason = request.form.get("reject_reason", "").strip()
    if not reject_reason:
        flash("拒绝原因不能为空")
        return redirect(url_for("archive.leader_dashboard"))

    res = db.session.get(Reservation, res_id)
    if not res:
        flash("预约记录不存在")
        return redirect(url_for("archive.leader_dashboard"))

    if res.status != '待部门领导指定审批人':
        flash(f"操作被忽略：当前状态为 {res.status}")
        return redirect(url_for("archive.leader_dashboard"))

    res.status = '已拒绝'
    res.reject_reason = reject_reason
    res.leader_id = staff.id

    db.session.commit()
    flash("已拒绝该预约申请")
    return redirect(url_for("archive.leader_dashboard"))


@archive_bp.route("/leader/push/<int:res_id>", methods=["POST"])
def leader_push(res_id):
    staff = _get_current_staff()
    if not staff or staff.staff_type != 'leader':
        return jsonify({"error": "无权限"}), 403

    res = db.session.get(Reservation, res_id)
    if not res:
        return jsonify({"error": "预约记录不存在"}), 404

    if not res.approval_teacher_id:
        return jsonify({"error": "该预约尚未指定审批教师"}), 400

    return jsonify({"success": True, "message": "已重复推送消息至审批教师"})


@archive_bp.route("/leader/api/teachers")
def leader_api_teachers():
    staff = _get_current_staff()
    if not staff or staff.staff_type != 'leader':
        return jsonify({"error": "无权限"}), 403

    import json
    all_teachers = ApprovalStaff.query.filter_by(
        staff_type='approval', is_active=True
    ).order_by(ApprovalStaff.name).all()

    archive_venue_ids = set(_get_assigned_venue_ids())
    filtered_teachers = []
    for t in all_teachers:
        t_venue_ids = set(t.get_assigned_venue_ids())
        if t_venue_ids & archive_venue_ids:
            filtered_teachers.append({
                "id": t.id,
                "name": t.name,
                "department": t.department or '',
                "phone": t.phone or ''
            })

    return jsonify({"teachers": filtered_teachers})


@archive_bp.route("/leader/api/stats")
def leader_api_stats():
    period = request.args.get('period', 'today')
    today = date.today()

    if period == 'today':
        start = today
        end = today
    elif period == 'week':
        start = today - timedelta(days=today.weekday())
        end = today
    elif period == 'month':
        start = today.replace(day=1)
        end = today
    elif period == 'year':
        start = today.replace(month=1, day=1)
        end = today
    else:
        start = today
        end = today

    if start == end:
        date_cond = func.date(Reservation.created_at) == start
    else:
        date_cond = func.date(Reservation.created_at).between(start, end)

    assigned_ids = _get_assigned_venue_ids()
    if assigned_ids:
        venue_cond = Reservation.venue_id.in_(assigned_ids)
        total_count = db.session.query(func.count(Reservation.id)).filter(date_cond, venue_cond).scalar() or 0
        pending_assign_count = db.session.query(func.count(Reservation.id)).filter(
            date_cond, venue_cond, Reservation.status == '待部门领导指定审批人'
        ).scalar() or 0
        pending_audit_count = db.session.query(func.count(Reservation.id)).filter(
            date_cond, venue_cond, Reservation.status == '待审核'
        ).scalar() or 0
        approved_count = db.session.query(func.count(Reservation.id)).filter(
            date_cond, venue_cond, Reservation.status == '已同意'
        ).scalar() or 0
        rejected_count = db.session.query(func.count(Reservation.id)).filter(
            date_cond, venue_cond, Reservation.status == '已拒绝'
        ).scalar() or 0
        verified_count = db.session.query(func.count(Reservation.id)).filter(
            date_cond, venue_cond, Reservation.status == '已核销'
        ).scalar() or 0
        online_count = db.session.query(func.count(Reservation.id)).filter(
            date_cond, venue_cond, Reservation.visit_type == '线上'
        ).scalar() or 0
        offline_count = db.session.query(func.count(Reservation.id)).filter(
            date_cond, venue_cond, Reservation.visit_type == '线下'
        ).scalar() or 0
    else:
        total_count = db.session.query(func.count(Reservation.id)).filter(date_cond).scalar() or 0
        pending_assign_count = db.session.query(func.count(Reservation.id)).filter(
            date_cond, Reservation.status == '待部门领导指定审批人'
        ).scalar() or 0
        pending_audit_count = db.session.query(func.count(Reservation.id)).filter(
            date_cond, Reservation.status == '待审核'
        ).scalar() or 0
        approved_count = db.session.query(func.count(Reservation.id)).filter(
            date_cond, Reservation.status == '已同意'
        ).scalar() or 0
        rejected_count = db.session.query(func.count(Reservation.id)).filter(
            date_cond, Reservation.status == '已拒绝'
        ).scalar() or 0
        verified_count = db.session.query(func.count(Reservation.id)).filter(
            date_cond, Reservation.status == '已核销'
        ).scalar() or 0
        online_count = db.session.query(func.count(Reservation.id)).filter(
            date_cond, Reservation.visit_type == '线上'
        ).scalar() or 0
        offline_count = db.session.query(func.count(Reservation.id)).filter(
            date_cond, Reservation.visit_type == '线下'
        ).scalar() or 0

    return jsonify({
        "period": period,
        "start_date": start.strftime('%Y-%m-%d'),
        "end_date": end.strftime('%Y-%m-%d'),
        "total_count": total_count,
        "pending_assign_count": pending_assign_count,
        "pending_audit_count": pending_audit_count,
        "approved_count": approved_count,
        "rejected_count": rejected_count,
        "verified_count": verified_count,
        "online_count": online_count,
        "offline_count": offline_count,
    })


@archive_bp.route("/leader/stats")
def leader_stats_page():
    return render_template("leader_stats.html", area_label="档案馆", bp_prefix="/archive", bp_name="archive")


@archive_bp.route("/leader/stats/trend")
def leader_stats_trend():
    time_range = request.args.get("time_range", "month")
    assigned_ids = _get_assigned_venue_ids()

    query = Reservation.query
    if assigned_ids:
        query = query.filter(Reservation.venue_id.in_(assigned_ids))

    if time_range == "day":
        result = query.with_entities(
            func.date(Reservation.created_at).label('date'),
            func.count(Reservation.id).label('count')
        ).group_by(func.date(Reservation.created_at)).order_by('date').all()
        data = {
            "labels": [item.date.strftime('%Y-%m-%d') for item in result],
            "values": [item.count for item in result]
        }
    elif time_range == "week":
        result = query.with_entities(
            func.date_format(Reservation.created_at, '%Y-%u').label('week'),
            func.count(Reservation.id).label('count')
        ).group_by('week').order_by('week').all()
        data = {
            "labels": [item.week for item in result],
            "values": [item.count for item in result]
        }
    else:
        result = query.with_entities(
            func.date_format(Reservation.created_at, '%Y-%m').label('month'),
            func.count(Reservation.id).label('count')
        ).group_by('month').order_by('month').all()
        data = {
            "labels": [item.month for item in result],
            "values": [item.count for item in result]
        }
    return data


@archive_bp.route("/leader/stats/status")
def leader_stats_status():
    assigned_ids = _get_assigned_venue_ids()
    query = Reservation.query
    if assigned_ids:
        query = query.filter(Reservation.venue_id.in_(assigned_ids))

    result = query.with_entities(
        Reservation.status,
        func.count(Reservation.id).label('count')
    ).group_by(Reservation.status).all()
    return {
        "labels": [item.status for item in result],
        "values": [item.count for item in result]
    }


@archive_bp.route("/leader/stats/visit-type")
def leader_stats_visit_type():
    assigned_ids = _get_assigned_venue_ids()
    query = Reservation.query
    if assigned_ids:
        query = query.filter(Reservation.venue_id.in_(assigned_ids))

    result = query.with_entities(
        Reservation.visit_type,
        func.count(Reservation.id).label('count')
    ).group_by(Reservation.visit_type).all()
    return {
        "labels": [item.visit_type or '未指定' for item in result],
        "values": [item.count for item in result]
    }


@archive_bp.route("/logout")
def logout():
    session.pop("archive_logged_in", None)
    session.pop("archive_staff_id", None)
    session.pop("archive_username", None)
    session.pop("archive_name", None)
    session.pop("archive_staff_type", None)
    session.pop("archive_security_token", None)
    flash("您已安全退出")
    return redirect(url_for("archive.login"))
