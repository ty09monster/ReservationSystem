from functools import wraps
from flask import session, redirect, url_for, request


def login_required(f):
    """
    登录验证装饰器
    用于需要登录才能访问的页面
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            # 记录原访问地址，登录后跳转回
            return redirect(url_for('h5.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function
