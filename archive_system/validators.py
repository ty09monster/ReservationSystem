import re
from datetime import datetime

def validate_id_card(id_code):
    """
    校验中国大陆身份证 (18位) 及 港澳台居民居住证
    算法：ISO 7064:1983.MOD 11-2
    """
    if len(id_code) != 18:
        return False, "长度必须为18位"

    # 1. 格式校验 (前17位数字，最后一位数字或X)
    if not re.match(r'^\d{17}[\dX]$', id_code):
        return False, "格式错误，包含非法字符"

    # 2. 省份校验 (简单校验前两位是否在编码表中，此处略去庞大的字典，主要靠校验码)
    
    # 3. 生日日期校验
    try:
        birth_str = id_code[6:14]
        birth_date = datetime.strptime(birth_str, '%Y%m%d')
        if birth_date > datetime.now() or birth_date.year < 1900:
            return False, "出生日期无效"
    except ValueError:
        return False, "出生日期非法"

    # 4. 校验码计算 (核心算法)
    factor = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    parity = ['1', '0', 'X', '9', '8', '7', '6', '5', '4', '3', '2']
    
    checksum = 0
    for i in range(17):
        checksum += int(id_code[i]) * factor[i]
    
    expected_last = parity[checksum % 11]
    
    if id_code[-1] != expected_last:
        return False, "身份证校验位错误（可能是假号或输入错误）"
        
    return True, "校验通过"

def validate_certificate(cert_type, cert_no):
    """
    统一入口：根据证件类型分发校验逻辑
    """
    cert_no = cert_no.upper().strip() # 统一转大写，去空格

    if cert_type in ['身份证', '港澳台居民居住证']:
        return validate_id_card(cert_no)
    
    elif cert_type == '港澳居民来往内地通行证':
        # 规则：H或M开头 + 8位或10位数字 (部分旧版是10位)
        if re.match(r'^[HM]\d{8,10}$', cert_no):
            return True, "格式正确"
        return False, "格式应为 H/M + 8或10位数字"

    elif cert_type == '台湾居民来往大陆通行证':
        # 规则：8位数字 (台胞证) 或 新版卡式可能带字母
        # 普遍规则：8位数字 或 1位字母+7位数字(极少) 
        # 这里采用较通用的 8位数字校验
        if re.match(r'^\d{8}$', cert_no):
            return True, "格式正确"
        return False, "格式应为 8位数字"

    elif cert_type == '外国人永久居留身份证':
        # 旧版：15位 (3字母+12数字)
        # 新版(五星卡)：18位 (9开头，算法同身份证)
        if len(cert_no) == 18 and cert_no.startswith('9'):
            return validate_id_card(cert_no) # 复用身份证算法
        elif re.match(r'^[A-Z]{3}\d{12}$', cert_no):
            return True, "格式正确"
        return False, "格式不正确"

    elif cert_type == '护照':
        # 护照规则复杂，全球标准不一。
        # 中国护照通常是 E/G/E + 数字，外国护照长度不一
        # 策略：宽松校验，长度5-20位，只含数字和字母
        if re.match(r'^[A-Z0-9]{5,20}$', cert_no):
            return True, "格式正确"
        return False, "护照号码格式异常"
    
    return True, "未知证件类型，跳过校验"

def validate_phone(phone):
    """
    校验中国大陆手机号
    规则：
    1. 必须是11位数字
    2. 第一位是1
    3. 第二位是3-9 (目前涵盖了13x, 14x, 15x, 16x, 17x, 18x, 19x)
    """
    if not phone:
        return False, "手机号不能为空"
    
    # 正则表达式解释：
    # ^1      : 以1开头
    # [3-9]   : 第二位必须是3到9之间的数字
    # \d{9}$  : 后面紧跟9个数字，直到结束
    if not re.match(r'^1[3-9]\d{9}$', phone):
        return False, "请输入有效的11位手机号码"
        
    return True, "校验通过"