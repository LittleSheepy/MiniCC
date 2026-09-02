---
name: user_table_schema
description: 项目中user数据库表的结构设计，包含字段、类型、约束及索引信息
type: project
---

定义在schema.sql文件中。字段包括：id (INTEGER, 主键自增), username (VARCHAR(32), 唯一非空), email (VARCHAR(255), 唯一非空), password_hash (VARCHAR(255), 非空), status (TINYINT, 非空, 默认1), created_at (DATETIME, 非空, 默认当前时间), updated_at (DATETIME, 非空, 默认当前时间)。附加索引：idx_user_email, idx_user_username, idx_user_status。约束包括主键自增、唯一约束、非空约束、默认值设置。
