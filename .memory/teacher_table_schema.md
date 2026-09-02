---
name: teacher_table_schema
description: 项目中teacher数据库表的详细结构设计，包含字段、类型、约束、索引及代码风格说明
type: project
---

表名: teacher。字段包括: id (INTEGER PK AUTOINCREMENT, 自增主键), name (VARCHAR(64) NOT NULL, 教师姓名), email (VARCHAR(255) NOT NULL UNIQUE, 邮箱), subject (VARCHAR(64) NOT NULL, 所教科目), title (VARCHAR(64) DEFAULT '', 职称), status (TINYINT DEFAULT 1, 状态:1在职/0离职), created_at (DATETIME, 创建时间), updated_at (DATETIME, 更新时间)。索引: idx_teacher_email, idx_teacher_subject, idx_teacher_status。代码风格与user表一致（包含行内注释和末尾字段说明汇总），定义位于 schema.sql 文件末尾。
