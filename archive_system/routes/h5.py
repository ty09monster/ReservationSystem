import logging
import re
import html as html_module
from urllib.parse import urlparse, urljoin
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from markupsafe import Markup
from datetime import datetime
import os
import uuid
from ..extensions import db
from ..models import User, SystemConfig, Announcement, Reservation, Venue, VenueTimeSlot, Attachment
from ..validators import validate_certificate, validate_phone, validate_visit_date
from ..decorators import login_required

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
        for attr_match in re.finditer(r'(\w+)\s*=\s*(?:"([^"]*)"|' "'([^']*)'", attrs_str):
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
    # F9: 对公告内容做 HTML 净化，防止存储型 XSS
    for ann in announcements:
        ann._safe_content = sanitize_html(ann.content)
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

# 预约基础函数
def _reserve_base(venue_category, res_type):
    # 修复 #15: 使用 db.session.get
    user = db.session.get(User, session["user_id"])
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
        flash("暂无可用场馆")
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

        # F13: 个人预约严格强制 group_size=1，不允许带同伴
        if res_type == "个人":
            group_size = 1
        elif group_size < 1:
            group_size = 1

        # 验证场馆是否存在且启用
        venue = Venue.query.filter_by(id=campus_venue_id, is_active=True).first()
        if not venue:
            flash("选择的场馆不存在或未启用")
            return render_template(f"h5_reserve_{venue_category}_{res_type}.html", user=user, venues=venues, venue=default_venue)

        # 验证预约日期，传入 advance_days 上限
        is_date_valid, date_msg = validate_visit_date(visit_date, advance_days=venue.advance_days)
        if not is_date_valid:
            flash(date_msg)
            return render_template(f"h5_reserve_{venue_category}_{res_type}.html", user=user, venues=venues, venue=default_venue)

        # F14: cutoff_time 校验——如果预约当天，检查是否超过截止时间
        visit_date_obj_check = datetime.strptime(visit_date, "%Y-%m-%d").date()
        if visit_date_obj_check == datetime.now().date() and venue.cutoff_time:
            try:
                cutoff = datetime.strptime(venue.cutoff_time, "%H:%M").time()
                if datetime.now().time() > cutoff:
                    flash(f"今日预约已截止（截止时间 {venue.cutoff_time}），请选择其他日期")
                    return render_template(f"h5_reserve_{venue_category}_{res_type}.html", user=user, venues=venues, venue=default_venue)
            except ValueError:
                pass  # cutoff_time 格式异常时跳过校验

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
        # F11: Python weekday() 返回 0=周一，转换为 0=周日
        day_of_week = (visit_date_obj.weekday() + 1) % 7
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
                reserved_individual = sum(res.group_size for res in time_slot_reservations)
                
                if reserved_individual + group_size > time_slot_config.individual_capacity:
                    db.session.rollback()
                    flash("所选时段个人预约人数已满，请选择其他时段")
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
            
            # 修复 #2: 安全的文件上传处理
            if 'attachments' in request.files:
                files = request.files.getlist('attachments')
                
                # 限制文件数量
                if len(files) > MAX_FILE_COUNT:
                    db.session.rollback()
                    flash(f"最多上传 {MAX_FILE_COUNT} 个文件")
                    return render_template(f"h5_reserve_{venue_category}_{res_type}.html", user=user, venues=venues, venue=default_venue)
                
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
                            return render_template(f"h5_reserve_{venue_category}_{res_type}.html", user=user, venues=venues, venue=default_venue)
                        
                        # 先读取文件内容，检查真实大小（file.content_length 不可靠）
                        content = file.read()
                        actual_size = len(content)
                        if actual_size > MAX_FILE_SIZE:
                            db.session.rollback()
                            flash(f"文件 {file.filename} 超过15MB限制（实际大小：{actual_size // 1024 // 1024}MB）")
                            return render_template(f"h5_reserve_{venue_category}_{res_type}.html", user=user, venues=venues, venue=default_venue)
                        
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
            return render_template(f"h5_reserve_{venue_category}_{res_type}.html", user=user, venues=venues, venue=default_venue)

        logger.info("用户 %s 预约提交成功，等待审核", session['user_id'])
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


# 邮件个人查询档案
@h5_bp.route("/h5/reserve/email/individual", methods=["GET", "POST"])
@login_required
def reserve_email_individual():
    user = db.session.get(User, session["user_id"])
    if not user:
        flash("用户信息不存在，请重新登录")
        session.clear()
        return redirect(url_for("h5.login"))

    config = SystemConfig.query.first()
    if not config.is_open:
        flash("系统维护中，暂时关闭预约")
        return redirect(url_for("h5.home"))

    venues = Venue.query.filter_by(is_active=True).all()
    default_venue = venues[0] if venues else None

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        reason = request.form.get("reason", "").strip()
        identity = request.form.get("identity", "").strip()

        # 邮箱校验
        if not email or "@" not in email or "." not in email.split("@")[-1]:
            flash("请填写正确的邮箱地址")
            return render_template("h5_reserve_邮件_个人.html", user=user, venues=venues, venue=default_venue)

        if not reason:
            flash("请填写申请理由")
            return render_template("h5_reserve_邮件_个人.html", user=user, venues=venues, venue=default_venue)

        # F2: 保存用户邮箱
        user.email = email

        # 动态查询档案馆场馆
        archive_venue = Venue.query.filter(
            Venue.category == "档案馆",
            Venue.is_active == True
        ).first()
        if not archive_venue:
            archive_venue = Venue.query.filter_by(is_active=True).first()
        if not archive_venue:
            flash("暂无可用场馆，无法提交申请")
            return render_template("h5_reserve_邮件_个人.html", user=user, venues=venues, venue=default_venue)

        # F12: 查重——每个用户每天最多 1 次档案查询
        today = datetime.now().date()
        existing = Reservation.query.filter_by(
            user_id=session["user_id"],
            visit_time="线上办理",
            visit_date=today
        ).filter(
            Reservation.status.in_(["待审核", "已同意"])
        ).count()
        if existing > 0:
            flash("您今天已提交过档案查询申请，请等待审核结果")
            return render_template("h5_reserve_邮件_个人.html", user=user, venues=venues, venue=default_venue)

        from sqlalchemy.exc import SQLAlchemyError
        try:
            # 创建预约记录
            res = Reservation(
                user_id=session["user_id"],
                venue_id=archive_venue.id,
                visit_date=today,
                visit_time="线上办理",
                reason=f"【邮件查询】{reason}",
                res_type="个人",
                group_name=None,
                group_contact=None,
                group_size=1,
                identity=identity,
                campus=archive_venue.campus or "无",
            )
            db.session.add(res)
            db.session.flush()

            # F1: 处理附件上传（复用安全上传逻辑）
            if 'attachments' in request.files:
                files = request.files.getlist('attachments')
                if len(files) > MAX_FILE_COUNT:
                    db.session.rollback()
                    flash(f"最多上传 {MAX_FILE_COUNT} 个文件")
                    return render_template("h5_reserve_邮件_个人.html", user=user, venues=venues, venue=default_venue)

                upload_dir = os.path.join(os.path.dirname(__file__), '..', 'static', 'uploads')
                if not os.path.exists(upload_dir):
                    os.makedirs(upload_dir)

                for file in files:
                    if file and file.filename:
                        ext = os.path.splitext(file.filename)[1].lower()
                        if ext not in ALLOWED_EXTENSIONS:
                            db.session.rollback()
                            flash(f"不支持的文件类型: {file.filename}")
                            return render_template("h5_reserve_邮件_个人.html", user=user, venues=venues, venue=default_venue)

                        content = file.read()
                        actual_size = len(content)
                        if actual_size > MAX_FILE_SIZE:
                            db.session.rollback()
                            flash(f"文件 {file.filename} 超过15MB限制")
                            return render_template("h5_reserve_邮件_个人.html", user=user, venues=venues, venue=default_venue)

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
                        logger.info("档案查询附件: 用户 %s 上传 %s", user.id, file.filename)

            db.session.commit()
            logger.info("用户 %s 提交线上档案查询，邮箱: %s", session["user_id"], email)
            flash("档案查询申请提交成功，审核通过后将发送至您的邮箱")
            return redirect(url_for("h5.history"))

        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error("档案查询提交失败: %s", e)
            flash("提交失败，请稍后重试")
            return render_template("h5_reserve_邮件_个人.html", user=user, venues=venues, venue=default_venue)

    return render_template("h5_reserve_邮件_个人.html", user=user, venues=venues, venue=default_venue)


@h5_bp.route("/h5/history")
@login_required
def history():
    user = db.session.get(User, session["user_id"])
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
    user = db.session.get(User, session["user_id"])
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
        # F11: Python weekday() 0=周一 → 转换为 0=周日
        day_of_week = (visit_date_obj.weekday() + 1) % 7
        
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
                "available_group": getattr(slot, 'is_group_active', True)
            })
        
        return {"slots": available_slots}
    except Exception as e:
        logger.error("获取可用时段失败: %s", e)
        return {"error": "获取可用时段失败"}, 500
