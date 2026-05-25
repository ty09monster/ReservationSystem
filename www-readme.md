在进行 3. 配置数据库 步骤时，需要先设置mysql开机自启并且设置密码为000000

在新服务器上首次运行时，设置环境变量：
export FLASK_INITDB=1
python run.py
或
FLASK_INITDB=1 python run.py

首次运行run.py后可能会出现只有本地服务器能访问，外部无法访问的情况。这时首先测试改为80端口能否外部访问，因为有的服务器策略是只开放80、443等常用端口。如果可以，那么情况是正常的。在nginx反向代理后，会把80段的请求返回给8000（默认）段，是正常的。

Nginx 默认的请求体大小限制是 1MB，当上传图片超过这个限制时会返回 413 错误。
编辑 Nginx 配置文件：sudo nano /etc/nginx/nginx.conf
在 http 块中添加或修改：
```nginx
http {
    # 其他配置...
    sendfile on;
    tcp_nopush on;
    types_hash_max_size 2048;
    # server_tokens off;
    
    # 增加上传文件大小限制
    client_max_body_size 20M;
    
    # 其他配置...
}
```
保存并退出 Nginx 配置文件。
