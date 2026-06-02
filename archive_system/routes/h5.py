import logging
import re
import html as html_module
from urllib.parse import urlparse, urljoin
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from markupsafe import Markup
from datetime import datetime, date, timedelta
import os
import uuid
from ..extensions import db
from ..models import User, SystemConfig, Announcement, Reservation, Venue, VenueTimeSlot, Attachment, ArchiveRequest, VenueTimeSlotDisabledDate, CancelRequest
from ..validators import validate_certificate, validate_phone, validate_email, validate_visit_date
from ..decorators import login_required
from sqlalchemy import func

logger = logging.getLogger(__name__)

h5_bp = Blueprint('h5', __name__)

# 文件上传安全：允许的图片扩展名
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
MAX_FILE_SIZE = 15 * 1024 * 1024  # 15MB
MAX_FILE_COUNT = 8

# HTML 净化白名单（防止隐私政策存储型 XSS）
ALLOWED_TAGS = {
    'p', 'br', 'b', 'i', 'u', 'strong', 'em', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'ul', 'ol', 'li', 'a', 'span', 'div', 'table', 'thead', 'tbody', 'tr', 'th', 'td',
    'blockquote', 'hr', 'pre', 'code',
}
ALLOWED_ATTRS = {'a': {'href', 'title', 'target'}, 'span': {'style'}, 'div': {'style'}}


def sanitize_html(raw_html):
    """简易 HTML 白名单过滤，移除不在白名单内的标签和危险属性。
    对白名单标签保留允许的属性，其他标签的内容保留但标签本身被去除。
    """
    if not raw_html:
        return ""

    def replace_tag(match):
        full = match.group(0)
        is_closing = match.group(1)  # '/' or ''
        tag_name = match.group(2).lower()
        attrs_str = match.group(3) or ''

        if tag_name not in ALLOWED_TAGS:
            return ''  # 移除不在白名单内的标签

        if is_closing:
            return f'</{tag_name}>'

        # 过滤属性
        allowed = ALLOWED_ATTRS.get(tag_name, set())
        safe_attrs = []
        for attr_match in re.finditer(r'(\w+)\s*=\s*(?:"([^"]*)"|' "'([^']*)')", attrs_str):
            attr_name = attr_match.group(1).lower()
            attr_val = attr_match.group(2) if attr_match.group(2) is not None else attr_match.group(3)
            if attr_name in allowed:
                # 防止 javascript: 协议注入
                if attr_name == 'href' and attr_val.strip().lower().startswith('javascript'):
                    continue
                safe_attrs.append(f'{attr_name}="{html_module.escape(attr_val)}"')

        attrs_part = (' ' + ' '.join(safe_attrs)) if safe_attrs else ''
        return f'<{tag_name}{attrs_part}>'

    # 匹配 HTML 标签：<tag ...> 或 </tag>
    result = re.sub(r'<(/?)([a-zA-Z][a-zA-Z0-9]*)([^>]*)/?>', replace_tag, raw_html)
    return Markup(result)


def is_safe_url(target):
    """校验重定向目标是否为站内地址，防止开放重定向漏洞。"""
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc


@h5_bp.route("/")
def index():
    """
    系统首页（A页面）
    无需登录即可访问
    """
    config = SystemConfig.query.first()
    announcements = Announcement.query.filter_by(is_hidden=False).order_by(
        Announcement.is_pinned.desc(),
        Announcement.created_at.desc()
    ).limit(2).all()
    is_logged_in = "user_id" in session
    return render_template("index.html", config=config, announcements=announcements, is_logged_in=is_logged_in)

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
    for ann in announcements:
        ann._safe_content = sanitize_html(ann.content)
    is_logged_in = "user_id" in session
    return render_template("announcements.html", announcements=announcements, is_logged_in=is_logged_in)

@h5_bp.route("/about")
def about():
    """
    关于我们（A页面）
    无需登录即可访问
    """
    config = SystemConfig.query.first()
    is_logged_in = "user_id" in session
    return render_template("about.html", config=config, is_logged_in=is_logged_in)

@h5_bp.route("/h5/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        # 修复 #1: 开放重定向——校验 next 参数是否为站内地址
        next_url = request.args.get('next')
        if next_url and is_safe_url(next_url):
            return redirect(next_url)
        return redirect(url_for("h5.home"))

    if request.method == "POST":
        id_type = request.form.get("id_type")
        id_card = request.form.get("id_card", "").upper().strip()
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()

        is_phone_valid, phone_msg = validate_phone(phone)
        config = SystemConfig.query.first()
        if not is_phone_valid:
            flash(f"手机号错误：{phone_msg}")
            return render_template("h5_login.html", prev_name=name, prev_phone=phone, prev_id_card=id_card, prev_id_type=id_type, prev_email=email, privacy_policy=config.privacy_policy)
        
        if email:
            is_email_valid, email_msg = validate_email(email)
            if not is_email_valid:
                flash(f"邮箱错误：{email_msg}")
                return render_template("h5_login.html", prev_name=name, prev_phone=phone, prev_id_card=id_card, prev_id_type=id_type, prev_email=email, privacy_policy=config.privacy_policy)
        
        is_valid, err_msg = validate_certificate(id_type, id_card)
        if not is_valid:
            flash(f"证件错误：{err_msg}")
            return render_template("h5_login.html", prev_name=name, prev_phone=phone, prev_id_card=id_card, prev_id_type=id_type, prev_email=email, privacy_policy=config.privacy_policy)
        
        user = User.query.filter_by(id_card=id_card).first()

        if not user:
            user = User(id_type=id_type, id_card=id_card, name=name, phone=phone, email=email or None)
            db.session.add(user)
            db.session.commit()
        else:
            user.name = name
            user.phone = phone
            user.id_type = id_type
            user.email = email or None
            db.session.commit()

        session["user_id"] = user.id
        # 修复 #1: 登录后跳转也做安全校验
        next_url = request.form.get('next') or request.args.get('next')
        if next_url and is_safe_url(next_url):
            return redirect(next_url)
        return redirect(url_for("h5.home"))

    config = SystemConfig.query.first()
    policy_text = config.privacy_policy if config else "<p>暂无内容</p>"
    # 修复 #16: 对隐私政策内容做 HTML 白名单过滤，防止存储型 XSS
    safe_policy = sanitize_html(policy_text)
    return render_template("h5_login.html", privacy_policy=safe_policy)

@h5_bp.route("/h5/home")
@login_required
def home():
    # 修复 #15: 使用 db.session.get 替代废弃的 Query.get
    user = db.session.get(User, session["user_id"])
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

@h5_bp.route("/h5/reserve/select")
def reserve_select():
    return redirect(url_for("h5.reserve"))

@h5_bp.route("/h5/reserve", methods=["GET", "POST"])
@login_required
def reserve():
    return _reserve_base("visit", "个人")

# 预约基础函数
def _reserve_base(template_key, render_res_type="个人", visit_type="线下"):
    user = db.session.get(User, session["user_id"])
    if not user:
        flash("用户信息不存在，请重新登录")
        session.clear()
        return redirect(url_for("h5.login"))

    if user.is_blacklisted:
        flash("您的账号已被管理员限制预约，如有疑问请联系学校相关部门")
        return redirect(url_for("h5.home"))

    config = SystemConfig.query.first()
    if not config.is_open:
        flash("系统维护中，暂时关闭预约")
        return redirect(url_for("h5.home"))

    venues = Venue.query.filter(Venue.is_active.is_(True), Venue.category.in_(['校史馆', '标本馆'])).all()
    if not venues:
        flash("暂无可用场馆")
        return redirect(url_for("h5.home"))

    default_venue = venues[0] if venues else None

    if request.method == "POST":
        campus_venue_id = request.form.get("campus_venue_id")
        visit_date = request.form.get("visit_date")
        visit_time = request.form.get("visit_time")
        reason = request.form.get("reason")
        res_type = request.form.get("res_type", "个人")
        visitor_count = request.form.get("visitor_count", 1, type=int)
        license_plate = request.form.get("license_plate", "").strip()
        need_guide = request.form.get("need_guide") == "1"

        group_name = request.form.get("group_name", "").strip()
        group_contact = request.form.get("group_contact", "").strip()
        id_number = request.form.get("id_number", "").strip()
        contact_phone = request.form.get("contact_phone", "").strip()

        if visitor_count < 1:
            visitor_count = 1

        # 验证场馆是否存在且启用
        venue = Venue.query.filter_by(id=campus_venue_id, is_active=True).first()
        if not venue:
            flash("选择的场馆不存在或未启用")
            return render_template("h5_reserve_modern.html", user=user, venues=venues, venue=default_venue)

        # 强制提前一天预约，不允许预约当天
        visit_date_obj = datetime.strptime(visit_date, "%Y-%m-%d").date()
        if visit_date_obj <= date.today():
            flash("必须提前一天预约，不可预约当天或过去的日期")
            return render_template("h5_reserve_modern.html", user=user, venues=venues, venue=default_venue)

        # 验证预约日期，传入 advance_days 上限
        is_date_valid, date_msg = validate_visit_date(visit_date, advance_days=venue.advance_days)
        if not is_date_valid:
            flash(date_msg)
            return render_template("h5_reserve_modern.html", user=user, venues=venues, venue=default_venue)

        # F14: cutoff_time 校验——已不再需要，因为不允许预约当天

        # 验证单位信息
        if res_type == "单位":
            if not group_name:
                flash("请输入预约人单位")
                return render_template("h5_reserve_modern.html", user=user, venues=venues, venue=default_venue)
            if not id_number:
                flash("请输入预约人身份证号")
                return render_template("h5_reserve_modern.html", user=user, venues=venues, venue=default_venue)
            if not group_contact:
                flash("请输入单位联系人")
                return render_template("h5_reserve_modern.html", user=user, venues=venues, venue=default_venue)
            if not contact_phone:
                flash("请输入联系电话")
                return render_template("h5_reserve_modern.html", user=user, venues=venues, venue=default_venue)


        MUSEUM_SLOTS = [
            "09:00-09:30", "09:30-10:00", "10:00-10:30", "10:30-11:00", "11:00-11:30",
            "15:00-15:30", "15:30-16:00", "16:00-16:30", "16:30-17:00", "17:00-17:30"
        ]
        is_museum_venue = venue.category in ('校史馆', '标本馆')

        # 检查该日期时段是否被禁用（检查时间段是否有重叠）
        disabled_list = VenueTimeSlotDisabledDate.query.filter_by(
            venue_id=campus_venue_id,
            disabled_date=visit_date_obj
        ).all()

        if is_museum_venue:
            if visit_time not in MUSEUM_SLOTS:
                flash("所选时段未开放，请选择其他时段")
                return render_template("h5_reserve_modern.html", user=user, venues=venues, venue=default_venue)
        else:
            day_of_week = (visit_date_obj.weekday() + 1) % 7
            time_slot_config = VenueTimeSlot.query.filter_by(
                venue_id=campus_venue_id,
                day_of_week=day_of_week,
                time_slot=visit_time,
                is_active=True
            ).first()
            if not time_slot_config:
                flash("所选时段未开放，请选择其他时段")
                return render_template("h5_reserve_modern.html", user=user, venues=venues, venue=default_venue)

        for disabled in disabled_list:
            disabled_start = disabled.time_slot.split('-')[0]
            disabled_end = disabled.time_slot.split('-')[1]
            visit_start = visit_time.split('-')[0]
            visit_end = visit_time.split('-')[1]
            if not (visit_end <= disabled_start or visit_start >= disabled_end):
                flash("所选日期时段已被管理员禁用，请选择其他时段")
                return render_template("h5_reserve_modern.html", user=user, venues=venues, venue=default_venue)

        # 使用事务确保并发安全
        from sqlalchemy.exc import SQLAlchemyError
        
        try:
            if is_museum_venue:
                pass
            else:
                day_of_week = (visit_date_obj.weekday() + 1) % 7
                time_slot_config = VenueTimeSlot.query.filter_by(
                    venue_id=campus_venue_id,
                    day_of_week=day_of_week,
                    time_slot=visit_time,
                    is_active=True
                ).with_for_update().first()
                
                if not time_slot_config:
                    db.session.rollback()
                    flash("所选时段未开放，请选择其他时段")
                    return render_template("h5_reserve_modern.html", user=user, venues=venues, venue=default_venue)

            # 校史馆/标本馆时段容量检查（每时段最多30人）
            if is_museum_venue:
                existing_count = db.session.query(func.sum(Reservation.visitor_count)).filter(
                    Reservation.venue_id == campus_venue_id,
                    Reservation.visit_date == visit_date_obj,
                    Reservation.visit_time == visit_time,
                    Reservation.status.in_(["待审核", "已同意"])
                ).scalar() or 0
                if existing_count + visitor_count > 30:
                    db.session.rollback()
                    flash(f"该时段预约人数已达上限（{existing_count}/30），请选择其他时段")
                    return render_template("h5_reserve_modern.html", user=user, venues=venues, venue=default_venue)
            
            # 创建预约记录
            res = Reservation(
                user_id=session["user_id"],
                venue_id=campus_venue_id,
                visit_date=visit_date_obj,
                visit_time=visit_time,
                reason=reason,
                res_type=res_type,
                visit_type=visit_type,
                group_name=group_name if res_type == "单位" else None,
                group_contact=group_contact if res_type == "单位" else None,
                id_number=id_number if res_type == "单位" else None,
                group_size=visitor_count if res_type == "单位" else 1,
                visitor_count=visitor_count,
                license_plate=license_plate or None,
                need_guide=need_guide,
                visiting_unit=None,
                contact_phone=contact_phone if res_type == "单位" else None,
                campus=venue.campus,
                status="待审核",
            )
            db.session.add(res)
            db.session.flush()  # 获取res的ID，用于附件关联
            
            # 修复 #2: 安全的文件上传处理
            if 'attachments' in request.files:
                files = request.files.getlist('attachments')
                
                # 限制文件数量
                if len(files) > MAX_FILE_COUNT:
                    db.session.rollback()
                    flash(f"最多上传 {MAX_FILE_COUNT} 个文件")
                    return render_template("h5_reserve_modern.html", user=user, venues=venues, venue=default_venue)
                
                # 创建上传目录
                upload_dir = os.path.join(os.path.dirname(__file__), '..', 'static', 'uploads')
                if not os.path.exists(upload_dir):
                    os.makedirs(upload_dir)
                
                # 处理上传的文件
                for file in files:
                    if file and file.filename:
                        # 校验文件扩展名（白名单）
                        ext = os.path.splitext(file.filename)[1].lower()
                        if ext not in ALLOWED_EXTENSIONS:
                            db.session.rollback()
                            flash(f"不支持的文件类型: {file.filename}，仅允许图片文件（{', '.join(ALLOWED_EXTENSIONS)}）")
                            return render_template("h5_reserve_modern.html", user=user, venues=venues, venue=default_venue)
                        
                        # 先读取文件内容，检查真实大小（file.content_length 不可靠）
                        content = file.read()
                        actual_size = len(content)
                        if actual_size > MAX_FILE_SIZE:
                            db.session.rollback()
                            flash(f"文件 {file.filename} 超过15MB限制（实际大小：{actual_size // 1024 // 1024}MB）")
                            return render_template("h5_reserve_modern.html", user=user, venues=venues, venue=default_venue)
                        
                        # 生成唯一文件名（保留安全的扩展名）
                        filename = f"{uuid.uuid4()}{ext}"
                        filepath = os.path.join(upload_dir, filename)
                        
                        # 保存文件（从已读取的内容写入）
                        with open(filepath, 'wb') as f:
                            f.write(content)
                        
                        # 创建附件记录（使用真实文件大小）
                        attachment = Attachment(
                            reservation_id=res.id,
                            filename=file.filename,
                            filepath=os.path.join('uploads', filename),
                            file_size=actual_size
                        )
                        db.session.add(attachment)
                        
                        logger.info("附件上传: 用户 %s 上传文件 %s, 保存为 %s, 大小 %d 字节",
                                    user.id, file.filename, filename, actual_size)
            
            # 提交所有更改
            db.session.commit()
            
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error("预约提交失败: %s", e)
            flash("预约提交失败，请稍后重试")
            return render_template("h5_reserve_modern.html", user=user, venues=venues, venue=default_venue)

        logger.info("用户 %s 预约提交成功，等待审核", session['user_id'])
        flash("预约提交成功，请等待审核通知")
        return redirect(url_for("h5.history"))

    # GET请求时显示预约表单
    return render_template("h5_reserve_modern.html", user=user, venues=venues, venue=default_venue)

# 校史馆预约
@h5_bp.route("/h5/reserve/xiaoshi", methods=["GET", "POST"])
@login_required
def reserve_xiaoshi():
    return _reserve_base("visit", "个人")

# 标本馆预约
@h5_bp.route("/h5/reserve/biaoben", methods=["GET", "POST"])
@login_required
def reserve_biaoben():
    return _reserve_base("visit", "个人")

@h5_bp.route("/h5/history")
@login_required
def history():
    user = db.session.get(User, session["user_id"])
    if not user:
        flash("用户信息不存在，请重新登录")
        session.clear()
        return redirect(url_for("h5.login"))

    status_filter = request.args.get("status", "").strip()
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()
    time_range = request.args.get("time_range", "").strip()
    venue_name = request.args.get("venue_name", "").strip()

    if time_range and not start_date:
        today = date.today()
        if time_range == 'week':
            start_date = (today - timedelta(days=7)).strftime('%Y-%m-%d')
        elif time_range == 'month':
            start_date = (today - timedelta(days=30)).strftime('%Y-%m-%d')
        elif time_range == '3month':
            start_date = (today - timedelta(days=90)).strftime('%Y-%m-%d')

    query = Reservation.query.filter_by(user_id=session["user_id"]).join(Venue).filter(
        Venue.category.in_(["校史馆", "标本馆"])
    )

    if status_filter:
        query = query.filter(Reservation.status == status_filter)

    if start_date:
        query = query.filter(Reservation.visit_date >= start_date)

    if end_date:
        query = query.filter(Reservation.visit_date <= end_date)

    if venue_name:
        query = query.filter(Venue.name.contains(venue_name))

    reservations = query.order_by(Reservation.created_at.desc()).all()

    venue_names = db.session.query(Venue.name).filter(
        Venue.category.in_(["校史馆", "标本馆"])
    ).distinct().all()
    venue_names = [v[0] for v in venue_names]

    return render_template("h5_history.html",
                           reservations=reservations,
                           curr_status=status_filter,
                           curr_start_date=start_date,
                           curr_end_date=end_date,
                           curr_time_range=time_range,
                           curr_venue_name=venue_name,
                           venue_names=venue_names)

@h5_bp.route("/h5/cancel/<int:res_id>", methods=["POST"])
@login_required
def cancel_reservation(res_id):
    reservation = db.session.get(Reservation, res_id)
    if not reservation:
        flash("预约不存在")
        return redirect(url_for("h5.history"))

    if reservation.user_id != session["user_id"]:
        flash("无权操作此预约")
        return redirect(url_for("h5.history"))

    if reservation.status in ("已取消", "已核销", "已拒绝"):
        flash("当前状态不可取消")
        return redirect(url_for("h5.history"))

    now = datetime.now()
    visit_datetime = datetime.combine(reservation.visit_date, datetime.strptime(reservation.visit_time.split('-')[0], "%H:%M").time())
    time_until_visit = visit_datetime - now

    if time_until_visit.total_seconds() < 3600:
        flash("距离预约开始时间不足一小时，无法取消")
        return redirect(url_for("h5.history"))

    reservation.status = "已取消"
    db.session.commit()
    flash("预约已取消")
    return redirect(url_for("h5.history"))

@h5_bp.route("/h5/archive-history")
@login_required
def archive_history():
    user = db.session.get(User, session["user_id"])
    if not user:
        flash("用户信息不存在，请重新登录")
        session.clear()
        return redirect(url_for("h5.login"))

    status_filter = request.args.get("status", "").strip()
    type_filter = request.args.get("type", "").strip()
    time_range = request.args.get("time_range", "").strip()
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()

    if time_range and not start_date:
        today = date.today()
        if time_range == 'week':
            start_date = (today - timedelta(days=7)).strftime('%Y-%m-%d')
        elif time_range == 'month':
            start_date = (today - timedelta(days=30)).strftime('%Y-%m-%d')
        elif time_range == '3month':
            start_date = (today - timedelta(days=90)).strftime('%Y-%m-%d')

    query = Reservation.query.join(Venue).filter(
        Reservation.user_id == session["user_id"],
        Venue.category == "档案馆"
    )

    if status_filter:
        query = query.filter(Reservation.status == status_filter)

    if type_filter:
        if type_filter == '线上':
            query = query.filter(Reservation.visit_type == '线上')
        elif type_filter == '线下':
            query = query.filter(Reservation.visit_type == '线下')

    if start_date:
        query = query.filter(Reservation.visit_date >= start_date)

    if end_date:
        query = query.filter(Reservation.visit_date <= end_date)

    reservations = query.order_by(Reservation.created_at.desc()).all()

    return render_template("h5_archive_history.html",
                           reservations=reservations,
                           curr_status=status_filter,
                           curr_type=type_filter,
                           curr_time_range=time_range,
                           curr_start_date=start_date,
                           curr_end_date=end_date)

@h5_bp.route("/h5/archive-cancel/<int:res_id>", methods=["POST"])
@login_required
def cancel_archive_reservation(res_id):
    reservation = db.session.get(Reservation, res_id)
    if not reservation:
        flash("预约不存在")
        return redirect(url_for("h5.archive_history"))

    if reservation.user_id != session["user_id"]:
        flash("无权操作此预约")
        return redirect(url_for("h5.archive_history"))

    if reservation.status != "待审核":
        flash("当前状态不可取消，已进入审批流程，如需取消请联系档案馆工作人员")
        return redirect(url_for("h5.archive_history"))

    cancel_reason = request.form.get("cancel_reason", "").strip()
    if not cancel_reason:
        flash("请填写取消原因")
        return redirect(url_for("h5.archive_history"))

    cancel_req = CancelRequest(
        reservation_id=reservation.id,
        user_id=session["user_id"],
        reason=cancel_reason,
        status="待处理"
    )
    db.session.add(cancel_req)
    reservation.status = "已取消"
    db.session.commit()

    logger.info("用户 %s 取消档案馆预约 %s，原因: %s", session['user_id'], res_id, cancel_reason)
    flash("预约已取消")
    return redirect(url_for("h5.archive_history"))

@h5_bp.route("/h5/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = db.session.get(User, session["user_id"])
    if not user:
        flash("用户信息不存在，请重新登录")
        session.clear()
        return redirect(url_for("h5.login"))

    if request.method == "POST":
        name = request.form.get("name")
        phone = request.form.get("phone")
        email = request.form.get("email", "").strip()
        
        is_phone_valid, phone_msg = validate_phone(phone)
        if not is_phone_valid:
            flash(f"手机号错误：{phone_msg}")
            return render_template("h5_profile.html", user=user)
        
        if email:
            is_email_valid, email_msg = validate_email(email)
            if not is_email_valid:
                flash(f"邮箱错误：{email_msg}")
                return render_template("h5_profile.html", user=user)
        
        user.name = name
        user.phone = phone
        user.email = email or None
        db.session.commit()
        flash("个人信息已更新")
        return redirect(url_for("h5.home"))

    return render_template("h5_profile.html", user=user)

@h5_bp.route("/h5/api/available-slots")
@login_required
def get_available_slots():
    """获取可用时段和剩余名额"""
    MUSEUM_SLOTS = [
        "09:00-09:30", "09:30-10:00", "10:00-10:30", "10:30-11:00", "11:00-11:30",
        "15:00-15:30", "15:30-16:00", "16:00-16:30", "16:30-17:00", "17:00-17:30"
    ]
    MUSEUM_CAPACITY = 30

    try:
        venue_id = request.args.get("venue_id", type=int)
        visit_date = request.args.get("visit_date")

        if not venue_id or not visit_date:
            return {"error": "缺少必要参数"}, 400

        visit_date_obj = datetime.strptime(visit_date, "%Y-%m-%d").date()

        venue = db.session.get(Venue, venue_id)
        if not venue:
            return {"error": "场馆不存在"}, 404

        disabled_slots = VenueTimeSlotDisabledDate.query.filter_by(
            venue_id=venue_id,
            disabled_date=visit_date_obj
        ).all()

        is_museum = venue.category in ('校史馆', '标本馆')

        if is_museum:
            slots_to_check = MUSEUM_SLOTS
            slot_capacity = MUSEUM_CAPACITY
        else:
            day_of_week = (visit_date_obj.weekday() + 1) % 7
            time_slots = VenueTimeSlot.query.filter_by(
                venue_id=venue_id,
                day_of_week=day_of_week,
                is_active=True
            ).all()
            if time_slots:
                slots_to_check = [s.time_slot for s in time_slots]
            else:
                config = SystemConfig.query.first()
                global_times = config.visit_times if config else "09:00-11:00,14:00-16:00"
                slots_to_check = [t.strip() for t in global_times.split(",") if t.strip()]
            slot_capacity = None

        existing_counts = {}
        if is_museum:
            reservations = Reservation.query.filter_by(
                venue_id=venue_id,
                visit_date=visit_date_obj
            ).filter(Reservation.status.in_(["待审核", "已同意"])).all()
            for r in reservations:
                existing_counts[r.visit_time] = existing_counts.get(r.visit_time, 0) + r.visitor_count

        def _is_slot_disabled(slot_str):
            slot_start, slot_end = slot_str.split('-')
            for disabled in disabled_slots:
                d_start, d_end = disabled.time_slot.split('-')
                if not (slot_end <= d_start or slot_start >= d_end):
                    return True
            return False

        available_slots = []
        for slot in slots_to_check:
            is_disabled = _is_slot_disabled(slot)
            booked = existing_counts.get(slot, 0) if is_museum else 0
            remaining = max(0, slot_capacity - booked) if is_museum else 0

            available_slots.append({
                "time_slot": slot,
                "available": not is_disabled and (not is_museum or remaining > 0),
                "remaining": remaining,
                "capacity": slot_capacity,
                "is_disabled": is_disabled,
                "is_museum": is_museum,
            })

        return {"slots": available_slots, "is_museum": is_museum}
    except Exception as e:
        logger.error("获取可用时段失败: %s", e)
        return {"error": "获取可用时段失败"}, 500

@h5_bp.route("/h5/archive-request", methods=["GET", "POST"])
@login_required
def archive_request():
    return redirect(url_for("h5.archive_reserve", visit_type="线下"))


@h5_bp.route("/h5/archive/reserve/<visit_type>", methods=["GET", "POST"])
@login_required
def archive_reserve(visit_type):
    visit_type = "线下"

    user = db.session.get(User, session["user_id"])
    if not user:
        flash("用户信息不存在，请重新登录")
        session.clear()
        return redirect(url_for("h5.login"))

    if user.is_blacklisted:
        flash("您的账号已被管理员限制预约，如有疑问请联系学校相关部门")
        return redirect(url_for("h5.home"))

    config = SystemConfig.query.first()
    if not config.is_open:
        flash("系统维护中，暂时关闭预约")
        return redirect(url_for("h5.home"))

    venues = Venue.query.filter_by(is_active=True).filter(Venue.category == "档案馆").all()
    if not venues:
        flash("暂无可用场馆")
        return redirect(url_for("h5.home"))

    def _get_default_archive_venue_id():
        if venues:
            return venues[0].id
        return None

    default_venue_id = _get_default_archive_venue_id()

    def _render(**extra):
        kwargs = dict(user=user, venues=venues, visit_type=visit_type, default_venue_id=default_venue_id)
        kwargs.update(extra)
        return render_template("h5_archive_reserve.html", **kwargs)

    if request.method == "POST":
        campus_venue_id = request.form.get("campus_venue_id")
        visit_date = request.form.get("visit_date")
        visit_time = request.form.get("visit_time")
        major = request.form.get("major", "").strip()
        grade = request.form.get("grade", "").strip()
        education_level = request.form.get("education_level", "").strip()
        custom_education_level = request.form.get("custom_education_level", "").strip()
        if education_level == "其他":
            if not custom_education_level:
                flash("请填写学历类别")
                return _render()
            education_level = custom_education_level
        query_content = request.form.get("query_content", "").strip()
        license_plate = request.form.get("license_plate", "").strip()

        if not major:
            flash("请输入专业")
            return _render()
        if not grade:
            flash("请输入年级")
            return _render()
        if not education_level:
            flash("请选择查询学历类别")
            return _render()
        if not query_content:
            flash("请填写查询内容")
            return _render()

        venue = Venue.query.filter_by(id=campus_venue_id, is_active=True).first()
        if not venue:
            flash("选择的场馆不存在或未启用")
            return _render()

        is_date_valid, date_msg = validate_visit_date(visit_date, advance_days=venue.advance_days)
        if not is_date_valid:
            flash(date_msg)
            return _render()

        visit_date_obj = datetime.strptime(visit_date, "%Y-%m-%d").date()

        if visit_date_obj == datetime.now().date() and venue.cutoff_time:
            try:
                cutoff = datetime.strptime(venue.cutoff_time, "%H:%M").time()
                if datetime.now().time() > cutoff:
                    flash(f"今日预约已截止（截止时间 {venue.cutoff_time}），请选择其他日期")
                    return _render()
            except ValueError:
                pass

        if visit_date_obj == datetime.now().date():
            try:
                slot_end_time = datetime.strptime(visit_time.split('-')[1], "%H:%M").time()
                if datetime.now().time() > slot_end_time:
                    flash(f"所选时间段 {visit_time} 已过，请选择其他时段")
                    return _render()
            except ValueError:
                pass

        day_of_week = (visit_date_obj.weekday() + 1) % 7
        time_slot_config = VenueTimeSlot.query.filter_by(
            venue_id=campus_venue_id,
            day_of_week=day_of_week,
            time_slot=visit_time,
            is_active=True
        ).first()

        has_any_slots = VenueTimeSlot.query.filter_by(
            venue_id=campus_venue_id
        ).first()

        if has_any_slots and not time_slot_config:
            flash("所选时段未开放，请选择其他时段")
            return _render()

        if not has_any_slots:
            config = SystemConfig.query.first()
            global_times = [t.strip() for t in (config.visit_times if config else "09:00-11:00,14:00-16:00").split(",") if t.strip()]
            if visit_time not in global_times:
                flash("所选时段未开放，请选择其他时段")
                return _render()

        disabled_list = VenueTimeSlotDisabledDate.query.filter_by(
            venue_id=campus_venue_id,
            disabled_date=visit_date_obj
        ).all()

        for disabled in disabled_list:
            disabled_start = disabled.time_slot.split('-')[0]
            disabled_end = disabled.time_slot.split('-')[1]
            visit_start = visit_time.split('-')[0]
            visit_end = visit_time.split('-')[1]
            if not (visit_end <= disabled_start or visit_start >= disabled_end):
                flash("所选日期时段已被管理员禁用，请选择其他时段")
                return _render()

        from sqlalchemy.exc import SQLAlchemyError

        try:
            if has_any_slots:
                time_slot_config = VenueTimeSlot.query.filter_by(
                    venue_id=campus_venue_id,
                    day_of_week=day_of_week,
                    time_slot=visit_time,
                    is_active=True
                ).with_for_update().first()

                if not time_slot_config:
                    db.session.rollback()
                    flash("所选时段未开放，请选择其他时段")
                    return _render()

            # ID card photo is required
            id_card_file = request.files.get('id_card_photo')
            if not id_card_file or not id_card_file.filename:
                flash("请上传身份证正面照")
                return _render()

            res = Reservation(
                user_id=session["user_id"],
                venue_id=campus_venue_id,
                visit_date=visit_date_obj,
                visit_time=visit_time,
                res_type="个人",
                visit_type=visit_type,
                archive_name=major,
                archive_number=grade,
                archive_purpose=query_content,
                education_level=education_level,
                license_plate=license_plate or None,
                visitor_count=1,
                campus=venue.campus,
                status="待审核",
            )
            db.session.add(res)
            db.session.flush()

            all_file_inputs = []
            if 'attachments' in request.files:
                all_file_inputs.extend(request.files.getlist('attachments'))
            if 'id_card_photo' in request.files:
                id_card_file = request.files['id_card_photo']
                if id_card_file and id_card_file.filename:
                    all_file_inputs.append(id_card_file)

            if len(all_file_inputs) > MAX_FILE_COUNT:
                db.session.rollback()
                flash(f"最多上传 {MAX_FILE_COUNT} 个文件")
                return _render()

            upload_dir = os.path.join(os.path.dirname(__file__), '..', 'static', 'uploads')
            if not os.path.exists(upload_dir):
                os.makedirs(upload_dir)

            for file in all_file_inputs:
                if file and file.filename:
                    ext = os.path.splitext(file.filename)[1].lower()
                    if ext not in ALLOWED_EXTENSIONS:
                        db.session.rollback()
                        flash(f"不支持的文件类型: {file.filename}，仅允许图片文件")
                        return _render()

                    content = file.read()
                    actual_size = len(content)
                    if actual_size > MAX_FILE_SIZE:
                        db.session.rollback()
                        flash(f"文件 {file.filename} 超过15MB限制")
                        return _render()

                    filename = f"{uuid.uuid4()}{ext}"
                    filepath = os.path.join(upload_dir, filename)

                    with open(filepath, 'wb') as f:
                        f.write(content)

                    attachment = Attachment(
                        reservation_id=res.id,
                        filename=file.filename,
                        filepath=os.path.join('uploads', filename),
                        file_size=actual_size
                    )
                    db.session.add(attachment)

            db.session.commit()

        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error("档案预约提交失败: %s", e)
            flash("预约提交失败，请稍后重试")
            return _render()

        logger.info("用户 %s 档案线下查阅预约提交成功", session['user_id'])
        flash("预约提交成功，请等待审核通知")
        return redirect(url_for("h5.archive_history"))

    return _render()
