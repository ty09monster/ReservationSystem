#!/usr/bin/env python3
"""
测试并发预约功能
模拟多个用户同时提交预约请求，测试并发安全改进是否有效
"""

import requests
import threading
import time
import random

# 测试配置
BASE_URL = "http://127.0.0.1:8000"
TEST_USER_COUNT = 5  # 测试用户数量
TEST_VENUE_ID = 2  # 测试场馆ID
TEST_DATE = "2026-02-10"  # 测试日期
TEST_TIME_SLOT = "09:00-10:30"  # 测试时间段
TEST_CAPACITY = 3  # 测试容量限制

# 全局变量
success_count = 0
fail_count = 0
error_count = 0
results = []

# 模拟用户登录
def login():
    """模拟用户登录，获取会话"""
    session = requests.Session()
    # 这里需要根据实际的登录逻辑进行调整
    # 假设登录接口为 /h5/login
    login_data = {
        "phone": f"138{random.randint(1000, 9999)}{random.randint(1000, 9999)}",
        "name": f"测试用户{random.randint(1, 1000)}"
    }
    try:
        response = session.post(f"{BASE_URL}/h5/login", data=login_data)
        if response.status_code == 200:
            return session
    except Exception as e:
        print(f"登录失败: {e}")
    return None

# 模拟用户提交预约
def submit_reservation(user_id):
    """模拟用户提交预约请求"""
    global success_count, fail_count, error_count
    
    try:
        # 登录获取会话
        session = login()
        if not session:
            error_count += 1
            results.append(f"用户{user_id}: 登录失败")
            return
        
        # 准备预约数据
        reservation_data = {
            "campus_venue_id": TEST_VENUE_ID,
            "visit_date": TEST_DATE,
            "visit_time": TEST_TIME_SLOT,
            "reason": f"测试预约{user_id}",
            "identity": "校内师生",
            "group_size": 1
        }
        
        # 提交预约
        response = session.post(f"{BASE_URL}/h5/reserve/xiaoshi/individual", data=reservation_data)
        
        if response.status_code == 200:
            if "预约提交成功" in response.text:
                success_count += 1
                results.append(f"用户{user_id}: 预约成功")
            elif "所选时段个人预约人数已满" in response.text:
                fail_count += 1
                results.append(f"用户{user_id}: 预约失败 - 人数已满")
            else:
                error_count += 1
                results.append(f"用户{user_id}: 预约失败 - 未知错误")
        else:
            error_count += 1
            results.append(f"用户{user_id}: 预约失败 - 状态码 {response.status_code}")
            
    except Exception as e:
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
    
    print(f"开始并发测试，模拟 {TEST_USER_COUNT} 个用户同时预约...")
    print(f"测试场馆: {TEST_VENUE_ID}")
    print(f"测试日期: {TEST_DATE}")
    print(f"测试时间段: {TEST_TIME_SLOT}")
    print(f"测试容量限制: {TEST_CAPACITY}")
    print("=" * 60)
    
    # 创建并启动线程
    threads = []
    for i in range(TEST_USER_COUNT):
        thread = threading.Thread(target=submit_reservation, args=(i+1,))
        threads.append(thread)
        thread.start()
        # 稍微延迟，模拟真实用户操作
        time.sleep(0.1)
    
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

if __name__ == "__main__":
    run_concurrency_test()
