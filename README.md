<div align="center">

# MiniCC

**一个受 Claude Code 启发的轻量级 AI 编程智能体框架**

[快速开始](#快速开始) · [架构概览](#架构概览) · [功能特性](#功能特性) · [配置说明](#配置说明)

</div>

---

MiniCC 是一个基于 Anthropic Claude API 构建的命令行 AI 编程智能体。它具备工具调用、上下文压缩、任务管理、多智能体协作、记忆系统、MCP 插件扩展等能力，是一个可运行的完整 Agent Harness。

本项目是学习 [learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) 后的实践产物，在理解其核心架构的基础上，将所有部件组装为一个可独立运行的简化版 Claude Code。

## 快速开始

### 环境要求

- Python 3.10+
- Anthropic API Key（或兼容的 API 端点）

### 安装

```bash
# 克隆项目
git clone https://github.com/LittleSheepy/MiniCC.git
cd MiniCC

# 安装依赖
pip install -r requirements.txt
```

### 配置

在项目根目录创建 `.env` 文件：

```env
# 必需：你的 Anthropic API Key
ANTHROPIC_API_KEY=sk-ant-xxxxx

# 必需：模型 ID（如 claude-sonnet-4-20250514）
MODEL_ID=claude-sonnet-4-20250514

# 可选：自定义 API 端点（用于代理或兼容服务）
# ANTHROPIC_BASE_URL=https://your-proxy.com/v1

# 可选：备用模型（当主模型过载时自动切换）
# FALLBACK_MODEL_ID=claude-3-5-haiku-latest
```

### 运行

```bash
python main.py
```

启动后在提示符处输入任务描述，回车发送。输入 `q` 或 `exit` 退出。

## 架构概览

```
main.py                  入口：启动主线程 + 异步事件循环线程
  │
  ├── agent_loop.py      核心循环：调用模型 → 解析响应 → 执行工具 → 反馈结果
  ├── model.py           API 客户端初始化与模型配置
  ├── assembly_prompt.py 系统提示词组装（每次循环动态更新）
  │
  ├── 工具层（每层独立定义 tool schema + handler）
  │   ├── tools_bash.py        Shell 命令执行
  │   ├── tools_file.py        文件读写与编辑（read/write/edit/glob）
  │   ├── tools_subagent.py    子智能体（独立上下文，最多 30 轮）
  │   ├── tools_task.py        任务看板（创建/认领/完成/依赖管理）
  │   ├── tools_todo_write.py  当前会话的 TODO 列表
  │   ├── teams.py             多智能体协作（spawn/shutdown/plan 审批）
  │   ├── worktrees.py         Git Worktree 隔离（并行任务文件系统隔离）
  │   ├── context_compact.py   上下文压缩（大输出持久化/自动摘要/reactive 压缩）
  │   └── skills.py            技能加载器（扫描 skills/ 目录）
  │
  ├── 横切关注点
  │   ├── hooks.py             事件钩子系统（10 个生命周期事件）
  │   ├── permission.py        权限门控（拒绝列表 → 规则匹配 → 用户确认）
  │   ├── error_recovery.py    错误恢复（429/529 重试、模型降级、上下文溢出压缩）
  │   ├── memory.py            记忆系统（自动提取/召回/整合持久化知识）
  │   ├── mcp_plugin.py        MCP 协议插件（动态发现外部工具）
  │   ├── message_bus.py       消息总线（线程安全的文件邮箱）
  │   └── global_variables.py  共享状态定义
  │
  └── console_broker.py  终端 I/O 序列化（多线程安全的 stdin 读取）
```

## 功能特性

### 核心工具

| 工具 | 说明 |
|------|------|
| `bash` | 执行 Shell 命令（120s 超时，输出截断 50KB） |
| `read_file` / `write_file` / `edit_file` | 文件读写与精确替换编辑 |
| `glob` | 按模式搜索文件 |
| `subagent` | 启动独立上下文的子智能体（最多 30 轮对话） |
| `todo_write` | 管理当前会话任务列表（最多 20 项） |
| `compact` | 手动触发上下文压缩 |
| `load_skill` | 加载 `skills/` 目录中的技能定义 |

### 任务协作系统

支持多智能体并行工作：

- **Task Board**：共享任务看板，支持依赖关系（`blockedBy`）
- **Teammates**：通过 `spawn_teammate` 创建持久化的协作者，各自拥有独立消息上下文
- **Plan 审批**：Lead 可要求 Teammate 提交工作计划，审批后才允许执行写操作
- **Git Worktree**：为并行任务创建独立的 Git 工作树，避免文件编辑冲突
- **消息总线**：基于文件邮箱的线程安全通信（`.mailboxes/` 目录）

### 上下文管理

采用分层压缩策略，确保长对话不溢出：

1. **Micro Compact**：压缩早期工具输出为简短占位符
2. **Snip Compact**：当消息数超过 50 条时，裁剪中间段落并归档
3. **Tool Result Budget**：超大工具输出持久化到 `.task_outputs/` 目录
4. **Summary Compact**：调用模型生成对话摘要，替换完整历史
5. **Reactive Compact**：收到 prompt-too-long 错误时自动触发紧急压缩

### 记忆系统

- **自动提取**：每轮结束后，模型从对话中提取值得长期保存的知识
- **智能召回**：每轮开始前，根据当前请求语义召回相关记忆
- **自动整合**：当记忆文件超过 10 条时，自动合并去重
- **持久化存储**：`.memory/` 目录下的 Markdown 文件，带 YAML frontmatter

### 安全机制

- **三级权限门控**：硬拒绝列表 → 规则匹配 → 用户确认
- **路径沙箱**：文件工具限制在工作目录内（`safe_path` 检查）
- **MCP 工具策略**：外部工具按 allow/confirm 策略管控

### 错误恢复

- **429 限流**：指数退避重试（最多 3 次）
- **529 过载**：连续 2 次后自动切换到备用模型
- **上下文溢出**：自动触发 reactive compact
- **max_tokens 截断**：升级 token 限制后重试，最多 2 次续写

### MCP 插件

支持通过 MCP 协议接入外部工具服务器（内置 `docs` 和 `deploy` 两个 mock server）。连接后工具自动发现，以 `mcp__{server}__{tool}` 前缀注册。

## 配置说明

### 环境变量

| 变量 | 必需 | 说明 |
|------|------|------|
| `ANTHROPIC_API_KEY` | 是 | Anthropic API 密钥 |
| `MODEL_ID` | 是 | 主模型 ID |
| `ANTHROPIC_BASE_URL` | 否 | 自定义 API 端点 |
| `FALLBACK_MODEL_ID` | 否 | 备用模型 ID |

### 自定义系统提示词

编辑 `assembly_prompt.py` 中的 `PROMPT_SECTIONS` 字典，可修改智能体的身份、行为规则和语言偏好。

### 添加技能

在 `skills/` 目录下创建子目录，包含 `SKILL.md` 文件（支持 YAML frontmatter），智能体可通过 `load_skill` 工具动态加载。

### 扩展工具

参照 `tools_file.py` 的模式：

1. 定义工具 schema（JSON Schema 格式的 `TOOLS_XXX` 列表）
2. 实现 handler 函数（`TOOL_HANDLERS_XXX` 字典）
3. 在 `agent_loop.py` 中注册到全局 `TOOLS` 和 `TOOL_HANDLERS`

## 项目目录结构

```
MiniCC/
├── main.py                # 入口
├── agent_loop.py          # 核心 Agent 循环
├── model.py               # API 客户端
├── assembly_prompt.py     # 系统提示词组装
├── tools_*.py             # 各类工具定义
├── teams.py               # 多智能体协作
├── worktrees.py           # Git Worktree 管理
├── context_compact.py     # 上下文压缩
├── memory.py              # 记忆系统
├── mcp_plugin.py          # MCP 插件
├── message_bus.py         # 消息总线
├── hooks.py               # 事件钩子
├── permission.py          # 权限系统
├── error_recovery.py      # 错误恢复
├── skills/                # 技能定义目录
│   ├── agent-builder/
│   ├── code-review/
│   ├── mcp-builder/
│   └── pdf/
├── .memory/               # 记忆存储（运行时生成）
├── .tasks/                # 任务文件（运行时生成）
├── .mailboxes/            # 消息邮箱（运行时生成）
├── .transcripts/          # 对话归档（运行时生成）
├── .task_outputs/         # 大输出持久化（运行时生成）
├── .worktrees/            # Git 工作树（运行时生成）
└── requirements.txt       # 依赖
```

## 使用示例

```
user >> 在当前目录创建一个 hello.py，输出 Hello World

user >> 创建一个任务：实现一个字符串工具库 string_tools.py，
        包含 slugify 函数。任命 Alice 为后端开发人员来完成。

user >> 请查看收件箱，看 Alice 的结果。

user >> 创建 Bob 作为测试人员，让他检查 string_tools.py 并验证 slugify 函数。
```

## 致谢

- [learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) — 本项目的学习蓝本

## 许可证

MIT
