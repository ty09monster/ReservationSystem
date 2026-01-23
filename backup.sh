#!/bin/bash
BACKUP_DIR="./backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
DB_USER="henau"  # 使用新用户名
DB_NAME="archive_system"

# 创建备份目录
mkdir -p $BACKUP_DIR

# 执行备份
mysqldump -u $DB_USER -p'henau123456' $DB_NAME > "$BACKUP_DIR/archive_system_$TIMESTAMP.sql"

# 压缩备份文件
gzip "$BACKUP_DIR/archive_system_$TIMESTAMP.sql"

# 保留最近7天的备份
find $BACKUP_DIR -name "archive_system_*.sql.gz" -mtime +7 -delete

echo "备份完成: $BACKUP_DIR/archive_system_$TIMESTAMP.sql.gz"