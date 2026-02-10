# 部署指南

本指南详细说明如何在远程服务器上部署河南农业大学校史馆与标本馆预约系统。

## 一、服务器准备

### 1. 服务器要求
- **操作系统**：Ubuntu 20.04 LTS 或 CentOS 7+
- **内存**：至少 2GB
- **CPU**：至少 2核
- **磁盘空间**：至少 20GB
- **网络**：稳定的网络连接，可访问互联网

### 2. 系统更新
```bash
# Ubuntu 系统
sudo apt update && sudo apt upgrade -y

# CentOS 系统
sudo yum update -y
```

## 二、环境配置

### 1. 安装必要的软件
```bash
# Ubuntu 系统
sudo apt install -y python3 python3-pip python3-venv nginx git mysql-server

# CentOS 系统
sudo yum install -y python3 python3-pip python3-venv nginx git mysql-server
```

### 2. 创建Python虚拟环境
```bash
# 创建虚拟环境目录
mkdir -p ~/Flask

# 创建虚拟环境
python3 -m venv ~/Flask/bin

# 激活虚拟环境
source ~/Flask/bin/activate

# 升级pip
pip install --upgrade pip
```

## 三、项目部署

### 1. 克隆项目
```bash
# 克隆项目到服务器
cd /var/www
sudo git clone https://github.com/yourusername/reservation-system.git

# 切换到项目目录
cd reservation-system

# 更改权限
sudo chown -R $USER:$USER /var/www/reservation-system
```

### 2. 安装依赖
```bash
# 激活虚拟环境
source ~/Flask/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 3. 配置数据库
```bash
# 登录MySQL
mysql -u root -p

# 创建数据库和用户
CREATE DATABASE archive_system CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'henau'@'localhost' IDENTIFIED BY 'henau123456';
GRANT ALL PRIVILEGES ON archive_system.* TO 'henau'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

### 4. 配置环境变量
```bash
# 创建.env文件
nano .env

# 添加以下内容
SECRET_KEY=your_secret_key_here
DATABASE_URL=mysql://henau:henau123456@localhost/archive_system

# 保存并退出
Ctrl+O, Enter, Ctrl+X
```

### 5. 初始化数据库
```bash
# 激活虚拟环境
source ~/Flask/bin/activate

# 运行应用，初始化数据库
python run.py

# 按 Ctrl+C 停止应用
```

### 6. 配置Gunicorn
```bash
# 启动Gunicorn服务器
source ~/Flask/bin/activate
gunicorn -c gunicorn_config.py run:app
```

### 7. 配置Nginx
```bash
# 创建Nginx配置文件
sudo nano /etc/nginx/sites-available/reservation-system

# 添加以下内容
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static {
        alias /var/www/reservation-system/archive_system/static;
        expires 30d;
    }
}

# 保存并退出
Ctrl+O, Enter, Ctrl+X

# 启用站点
sudo ln -s /etc/nginx/sites-available/reservation-system /etc/nginx/sites-enabled/

# 测试Nginx配置
sudo nginx -t

# 重启Nginx
sudo systemctl restart nginx
```

## 四、HTTPS配置

### 1. 安装Certbot
```bash
# Ubuntu 系统
sudo apt install -y certbot python3-certbot-nginx

# CentOS 系统
sudo yum install -y epel-release
sudo yum install -y certbot python3-certbot-nginx
```

### 2. 申请SSL证书
```bash
# 申请证书
sudo certbot --nginx -d your-domain.com

# 按提示操作，选择自动重定向HTTP到HTTPS
```

## 五、微信公众号配置

### 1. 公众号设置
1. 登录微信公众号后台
2. 进入"公众号设置" → "功能设置"
3. 在"业务域名"和"JS接口安全域名"中添加您的域名
4. 下载MP_verify_xxx.txt文件，上传到服务器的`/var/www/reservation-system/archive_system/static`目录

### 2. 服务器配置
1. 进入"开发" → "基本配置"
2. 启用服务器配置
3. 设置服务器地址(URL)为：`https://your-domain.com/admin`
4. 设置Token为您在`.env`文件中配置的SECRET_KEY
5. 点击"提交"完成配置

## 六、服务管理

### 1. 启动服务
```bash
# 启动Gunicorn服务器
source ~/Flask/bin/activate
cd /var/www/reservation-system
./start.sh
```

### 2. 停止服务
```bash
# 停止Gunicorn服务器
cd /var/www/reservation-system
./stop.sh
```

### 3. 查看服务状态
```bash
# 查看Gunicorn进程
ps aux | grep gunicorn

# 查看Nginx状态
sudo systemctl status nginx
```

## 七、故障排查

### 1. 常见问题

#### 502 Bad Gateway 错误
- 检查Gunicorn是否正在运行
- 检查Gunicorn日志：`logs/gunicorn_error.log`
- 检查Nginx配置是否正确

#### 数据库连接错误
- 检查数据库是否正在运行：`sudo systemctl status mysql`
- 检查数据库连接配置是否正确
- 检查数据库用户权限是否正确

#### 微信公众号配置错误
- 检查域名是否已添加到公众号的业务域名
- 检查服务器配置的URL和Token是否正确
- 检查SSL证书是否有效

### 2. 日志查看
```bash
# 查看Gunicorn访问日志
cat logs/gunicorn_access.log

# 查看Gunicorn错误日志
cat logs/gunicorn_error.log

# 查看Nginx访问日志
sudo cat /var/log/nginx/access.log

# 查看Nginx错误日志
sudo cat /var/log/nginx/error.log
```

## 八、性能优化

### 1. 数据库优化
- **创建适当的索引**：为频繁查询的字段创建索引，特别是预约表中的时间、场馆和状态字段
- **优化查询语句**：避免使用SELECT *，只查询必要的字段
- **定期清理无用数据**：设置定时任务清理过期的预约记录
- **启用查询缓存**：在MySQL配置中启用查询缓存
- **设置适当的连接池**：在Flask配置中设置SQLAlchemy连接池大小

### 2. 缓存配置
- **使用Redis缓存热点数据**：缓存场馆信息、时间槽容量等频繁访问的数据
- **配置Nginx缓存静态资源**：为CSS、JS、图片等静态资源设置缓存
- **启用浏览器缓存**：在Nginx配置中添加适当的缓存头

### 3. 应用优化
- **启用Gunicorn多进程**：根据服务器CPU核心数配置适当的worker进程数
- **使用异步处理**：对于邮件发送等耗时操作，使用异步处理
- **优化模板渲染**：使用模板缓存，避免重复渲染
- **压缩响应内容**：在Nginx中启用gzip压缩

### 4. 负载均衡（可选）
- 如果流量较大，考虑使用负载均衡
- 配置多个应用服务器实例
- 使用Redis作为Session存储，支持多实例部署

### 5. 监控与调优
- **安装监控工具**：使用Prometheus + Grafana监控服务器和应用状态
- **设置告警**：针对高负载、错误率等指标设置告警
- **定期分析日志**：使用ELK Stack分析应用日志，发现性能瓶颈

### 6. 微信H5优化
- **减少页面大小**：压缩CSS和JS文件
- **优化图片**：使用适当尺寸和格式的图片
- **延迟加载**：实现图片和非关键资源的延迟加载
- **预加载**：预加载可能需要的资源
- **避免重定向**：减少不必要的HTTP重定向

## 九、安全加固

### 1. 服务器安全
- **配置防火墙**：使用UFW或FirewallD配置防火墙，只开放必要的端口（80、443、SSH）
- **禁用root远程登录**：在SSH配置中禁用root远程登录，使用普通用户+sudo
- **定期更新系统和软件包**：设置自动更新或定期手动更新
- **使用密钥认证**：禁用密码认证，使用SSH密钥认证
- **限制SSH访问**：只允许特定IP访问SSH
- **监控登录尝试**：使用Fail2ban监控和阻止恶意登录尝试

### 2. 应用安全
- **定期更新依赖包**：使用`pip list --outdated`检查并更新过期的依赖包
- **实施输入验证**：对所有用户输入进行严格验证，防止SQL注入和XSS攻击
- **输出转义**：对输出到页面的内容进行适当转义
- **使用HTTPS加密传输**：确保所有通信都通过HTTPS进行
- **设置安全的HTTP头**：在Nginx配置中添加安全相关的HTTP头
- **使用CSRF保护**：为表单添加CSRF令牌
- **限制上传文件类型**：对用户上传的文件类型和大小进行严格限制

### 3. 数据库安全
- **限制数据库用户权限**：遵循最小权限原则，只授予必要的权限
- **定期备份数据库**：设置自动备份，将备份存储在安全的位置
- **使用强密码**：为数据库用户设置复杂的密码
- **禁用远程数据库访问**：除非必要，否则禁用远程数据库访问
- **定期审计数据库**：检查数据库中的异常活动
- **加密敏感数据**：对用户个人信息等敏感数据进行加密存储

### 4. 微信公众号安全
- **保护AppSecret**：不要在代码中硬编码AppSecret，使用环境变量
- **设置IP白名单**：在微信公众平台设置服务器IP白名单
- **验证消息来源**：对微信服务器发送的消息进行签名验证
- **使用HTTPS**：确保服务器地址(URL)使用HTTPS

### 5. 日志与审计
- **启用详细日志**：记录所有关键操作和异常情况
- **保护日志文件**：设置适当的权限，防止日志文件被篡改
- **定期分析日志**：检查日志中的异常活动
- **存储日志备份**：将日志备份到安全的位置，保留足够的时间

### 6. 应急响应
- **制定应急响应计划**：明确安全事件的处理流程
- **准备回滚方案**：在部署前准备好回滚方案
- **定期演练**：定期进行安全演练，测试应急响应能力

## 十、更新系统

### 1. 获取最新代码
```bash
# 进入项目目录
cd /var/www/reservation-system

# 拉取最新代码
git pull

# 安装新依赖
pip install -r requirements.txt

# 重启服务
./stop.sh
./start.sh
```

### 2. 数据库迁移
如果数据库结构有变更，需要运行数据库迁移命令：
```bash
# 运行数据库迁移
python manage.py db upgrade
```

## 十一、联系支持

如果在部署过程中遇到问题，请联系系统管理员：
- 邮箱：admin@example.com
- 电话：12345678900

---

**部署完成后，请访问以下地址：**
- 前台：`https://your-domain.com`
- 后台：`https://your-domain.com/admin`
- 管理员账号：admin
- 管理员密码：admin

请在首次登录后立即修改管理员密码！
