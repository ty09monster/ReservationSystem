#!/usr/bin/env python3
"""
直接数据库测试并发预约功能
绕过登录，直接操作数据库测试并发安全改进是否有效
"""

import threading
import time
import random
from archive_system import create_app, db
from archive_system.models import VenueTimeSlot, Reservation, User
from datetime import datetime

# 创建应用上下文
app = create_app()
app.app_context().push()

# 测试配置
TEST_VENUE_ID = 2  # 测试场馆ID
TEST_DATE = "2026-02-10"  # 测试日期
TEST_TIME_SLOT = "09:00-10:30"  # 测试时间段
TEST_CAPACITY = 3  # 测试容量限制
TEST_USER_COUNT = 5  # 测试用户数量

# 全局变量
success_count = 0
fail_count = 0
error_count = 0
results = []

# 准备测试数据
def prepare_test_data():
    """准备测试数据"""
    print("准备测试数据...")
    
    # 确保测试场馆存在
    venue_slot = VenueTimeSlot.query.filter_by(
        venue_id=TEST_VENUE_ID,
        day_of_week=datetime.strptime(TEST_DATE, "%Y-%m-%d").weekday(),
        time_slot=TEST_TIME_SLOT
    ).first()
    
    if not venue_slot:
        # 创建测试时段
        venue_slot = VenueTimeSlot(
            venue_id=TEST_VENUE_ID,
            day_of_week=datetime.strptime(TEST_DATE, "%Y-%m-%d").weekday(),
            time_slot=TEST_TIME_SLOT,
            individual_capacity=TEST_CAPACITY,
            is_group_active=True,
            is_active=True
        )
        db.session.add(venue_slot)
        db.session.commit()
        print(f"创建测试时段: {TEST_TIME_SLOT}，容量: {TEST_CAPACITY}")
    else:
        # 更新容量
        venue_slot.individual_capacity = TEST_CAPACITY
        db.session.commit()
        print(f"更新测试时段: {TEST_TIME_SLOT}，容量: {TEST_CAPACITY}")
    
    # 清空测试日期的预约记录
    Reservation.query.filter_by(
        venue_id=TEST_VENUE_ID,
        visit_date=datetime.strptime(TEST_DATE, "%Y-%m-%d").date(),
        visit_time=TEST_TIME_SLOT
    ).delete()
    db.session.commit()
    print(f"清空测试日期 {TEST_DATE} 的预约记录")
    
    # 确保有足够的测试用户
    for i in range(1, TEST_USER_COUNT + 1):
        user = User.query.filter_by(phone=f"1380000000{i}").first()
        if not user:
            user = User(
                phone=f"1380000000{i}",
                name=f"测试用户{i}",
                is_admin=False
            )
            db.session.add(user)
    db.session.commit()
    print(f"准备 {TEST_USER_COUNT} 个测试用户")

# 模拟用户提交预约
def submit_reservation(user_id):
    """模拟用户提交预约请求"""
    global success_count, fail_count, error_count
    
    try:
        # 获取测试用户
        user = User.query.filter_by(phone=f"1380000000{user_id}").first()
        if not user:
            error_count += 1
            results.append(f"用户{user_id}: 用户不存在")
            return
        
        # 开始事务
        db.session.begin()
        
        # 获取时段配置（加锁）
        venue_slot = VenueTimeSlot.query.filter_by(
            venue_id=TEST_VENUE_ID,
            day_of_week=datetime.strptime(TEST_DATE, "%Y-%m-%d").weekday(),
            time_slot=TEST_TIME_SLOT,
            is_active=True
        ).with_for_update().first()
        
        if not venue_slot:
            db.session.rollback()
            error_count += 1
            results.append(f"用户{user_id}: 时段未开放")
            return
        
        # 检查名额（加锁）
        existing_reservations = Reservation.query.filter_by(
            venue_id=TEST_VENUE_ID,
            visit_date=datetime.strptime(TEST_DATE, "%Y-%m-%d").date(),
            visit_time=TEST_TIME_SLOT,
            res_type="个人"
        ).filter(
            Reservation.status.in_(["待审核", "已同意"])
        ).with_for_update().all()
        
        # 计算已预约人数
        reserved = sum(res.group_size for res in existing_reservations)
        
        if reserved + 1 > venue_slot.individual_capacity:
            db.session.rollback()
            fail_count += 1
            results.append(f"用户{user_id}: 预约失败 - 人数已满")
            return
        
        # 创建预约记录
        reservation = Reservation(
            user_id=user.id,
            venue_id=TEST_VENUE_ID,
            visit_date=datetime.strptime(TEST_DATE, "%Y-%m-%d").date(),
            visit_time=TEST_TIME_SLOT,
            reason=f"测试预约{user_id}",
            res_type="个人",
            group_size=1,
            identity="校内师生",
            campus="文化路校区"
        )
        db.session.add(reservation)
        db.session.commit()
        
        success_count += 1
        results.append(f"用户{user_id}: 预约成功")
        
    except Exception as e:
        db.session.rollback()
        error_count += 1
        results.append(f"用户{user_id}: 预约失败 - {str(e)}")

# 运行并发测试
def run_concurrency_test():
    """运行并发测试"""
    global success_count, fail_count, error_count, results
    
    # 重置统计数据
    success_count = 0
    fail_count = 0
    error_count = 0
    results = []
    
    print(f"\n开始并发测试，模拟 {TEST_USER_COUNT} 个用户同时预约...")
    print(f"测试场馆: {TEST_VENUE_ID}")
    print(f"测试日期: {TEST_DATE}")
    print(f"测试时间段: {TEST_TIME_SLOT}")
    print(f"测试容量限制: {TEST_CAPACITY}")
    print("=" * 60)
    
    # 创建并启动线程
    threads = []
    for i in range(1, TEST_USER_COUNT + 1):
        thread = threading.Thread(target=submit_reservation, args=(i,))
        threads.append(thread)
        thread.start()
        # 稍微延迟，模拟真实用户操作
        time.sleep(0.05)
    
    # 等待所有线程完成
    for thread in threads:
        thread.join()
    
    # 打印测试结果
    print("=" * 60)
    print("测试结果:")
    print(f"成功: {success_count}")
    print(f"失败(人数已满): {fail_count}")
    print(f"错误: {error_count}")
    print(f"总请求数: {success_count + fail_count + error_count}")
    print("=" * 60)
    
    # 打印详细结果
    print("详细结果:")
    for result in results:
        print(result)
    print("=" * 60)
    
    # 验证测试结果
    if success_count <= TEST_CAPACITY:
        print("✅ 测试通过: 成功预约数未超过容量限制")
        print(f"   成功预约数: {success_count}, 容量限制: {TEST_CAPACITY}")
    else:
        print("❌ 测试失败: 成功预约数超过容量限制")
        print(f"   成功预约数: {success_count}, 容量限制: {TEST_CAPACITY}")
    
    # 验证数据库中的实际预约数量
    actual_reservations = Reservation.query.filter_by(
        venue_id=TEST_VENUE_ID,
        visit_date=datetime.strptime(TEST_DATE, "%Y-%m-%d").date(),
        visit_time=TEST_TIME_SLOT,
        res_type="个人"
    ).filter(
        Reservation.status.in_(["待审核", "已同意"])
    ).count()
    
    print(f"\n数据库实际预约数量: {actual_reservations}")
    if actual_reservations <= TEST_CAPACITY:
        print("✅ 数据库验证通过: 实际预约数未超过容量限制")
    else:
        print("❌ 数据库验证失败: 实际预约数超过容量限制")

if __name__ == "__main__":
    try:
        prepare_test_data()
        run_concurrency_test()
    finally:
        # 清理测试数据
        Reservation.query.filter_by(
            venue_id=TEST_VENUE_ID,
            visit_date=datetime.strptime(TEST_DATE, "%Y-%m-%d").date(),
            visit_time=TEST_TIME_SLOT
        ).delete()
        db.session.commit()
        print("\n清理测试数据完成")
