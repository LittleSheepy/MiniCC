#!/usr/bin/env python3

import threading
import time

from hooks import register_hook, trigger_hooks
from mcp_plugin import assemble_tool_pool
from message_bus import consume_lead_inbox
from model import client
from utils import execute_tool

try:
    import readline
    readline.parse_and_bind('set bind-tty-special-chars off')
    READLINE_AVAILABLE = True
except ImportError:
    try:
        import pyreadline3 as readline  # type: ignore
        READLINE_AVAILABLE = True
    except ImportError:
        READLINE_AVAILABLE = False

from assembly_prompt import assemble_system_prompt_hook, update_context
from error_recovery import with_retry, RecoveryState, is_prompt_too_long_error, MAX_RECOVERY_RETRIES
from console_broker import CONSOLE


from tools_bash import TOOLS_BASH, TOOL_HANDLERS_BASH
from tools_file import TOOLS_FILE, TOOL_HANDLERS_FILE
from tools_todo_write import TOOLS_TODOWRITE, TOOL_HANDLERS_TODOWRITE
from tools_subagent import TOOLS_SUBAGENT, TOOL_HANDLERS_SUBAGENT
from skills import TOOLS_SKILLS, TOOL_HANDLERS_SKILLS
from context_compact import TOOLS_COMPACT, TOOL_HANDLERS_COMPACT, COMPACTOR
from tools_task import TOOLS_TASK, TOOL_HANDLERS_TASK
from teams import TOOLS_TEAMS, TOOL_HANDLERS_TEAMS
from worktrees import TOOLS_WORKTREE, TOOL_HANDLERS_WORKTREE

from teams import format_team_events, active_teammates, BUS, release_completed_assignment

CLI_ACTIVE = False
PROMPT = "\033[36muser >> \033[0m"
agent_lock = threading.Lock()
DEFAULT_MAX_TOKENS = 8000
ESCALATED_MAX_TOKENS = 16000
CONTINUATION_PROMPT = "继续从上一次的回答开始。不要重复已完成的内容。"

TOOLS = (TOOLS_BASH + TOOLS_FILE + TOOLS_TODOWRITE + TOOLS_SUBAGENT + TOOLS_SKILLS +
         TOOLS_COMPACT + TOOLS_TASK + TOOLS_TEAMS + TOOLS_WORKTREE
         )
TOOL_HANDLERS = (TOOL_HANDLERS_BASH | TOOL_HANDLERS_FILE | TOOL_HANDLERS_TODOWRITE |
                 TOOL_HANDLERS_SUBAGENT | TOOL_HANDLERS_SKILLS | TOOL_HANDLERS_COMPACT |
                 TOOL_HANDLERS_TASK | TOOL_HANDLERS_TEAMS | TOOL_HANDLERS_WORKTREE
                 )

register_hook("BeginOfCallLLM", assemble_system_prompt_hook)

def has_tool_use(response) -> bool:
    # Do not rely on stop_reason alone; the concrete tool_use block is the
    # continuation signal used by the loop.
    return (any(getattr(block, "type", None) == "tool_use" for block in response.content)
            and (response.stop_reason == "tool_use"))

def call_llm(messages: list, tools: list, state: RecoveryState, max_tokens: int, context: dict={}):
    trigger_output_BeginOfCallLLM = {}
    trigger_hooks("BeginOfCallLLM", messages, trigger_output_BeginOfCallLLM)
    SYSTEM = trigger_output_BeginOfCallLLM.get("system", "")
    return with_retry(
        lambda: client.messages.create(model=state.current_model, system=SYSTEM, messages=messages, tools=tools,
            max_tokens=max_tokens),
        state)


def agent_loop(messages: list, context: dict, active_request: str):
    state = RecoveryState()
    trigger_output_Start = {}
    trigger_hooks("Start", messages, trigger_output_Start)
    max_tokens = DEFAULT_MAX_TOKENS
    while True:
        active_request = messages[-1]["content"]

        trigger_hooks("BeginOfLoop", messages)

        trigger_output_BeginOfCallLLM = {}
        trigger_hooks("BeginOfCallLLM", messages, trigger_output_BeginOfCallLLM)
        SYSTEM = trigger_output_BeginOfCallLLM.get("system", "")
        tools_mcp, handlers_mcp = assemble_tool_pool()
        global TOOLS, TOOL_HANDLERS
        TOOLS = TOOLS + tools_mcp
        TOOL_HANDLERS = TOOL_HANDLERS | handlers_mcp

        # 调用模型
        try:
            response = call_llm(messages, tools=TOOLS, state=state, max_tokens=max_tokens)
        except Exception as e:
            if is_prompt_too_long_error(e) and not state.has_attempted_reactive_compact:
                messages[:] = COMPACTOR.reactive_compact(messages, active_request)
                state.has_attempted_reactive_compact = True
                continue
            messages.append({"role": "assistant",
                             "content": [{"type": "text", "text": f"[Error] {type(e).__name__}: {e}"}]})
            release_completed_assignment("agent")
            trigger_hooks("Stop", messages)
            return

        # 上下文空间不足
        if response.stop_reason == "max_tokens":
            if not state.has_escalated:
                max_tokens = ESCALATED_MAX_TOKENS
                state.has_escalated = True
                print(f"  \033[33m[max_tokens] retry with {max_tokens}\033[0m")
                continue
            messages.append({"role": "assistant", "content": response.content})
            if state.recovery_count < MAX_RECOVERY_RETRIES:
                messages.append({"role": "user", "content": CONTINUATION_PROMPT})
                state.recovery_count += 1
                continue
            release_completed_assignment("agent")
            trigger_hooks("Stop", messages)
            return

        max_tokens = DEFAULT_MAX_TOKENS
        state.has_escalated = False

        messages.append({"role": "assistant", "content": response.content})     # 添加AI返回的内容

        if not has_tool_use(response):      # 如果该模型没有调用任何工具，那么我们就完成了。
            release_completed_assignment("agent")
            trigger_output_Stop = {}
            trigger_hooks("Stop", messages, trigger_output_Stop)
            force = trigger_output_Stop.get("force", False)
            if force:
                messages.append({"role": "user", "content": force})
                continue
            return

        trigger_hooks("PreAllToolsUse", response)

        # 执行每个工具调用，并收集结果
        results = []
        for block in response.content:
            if block.type == "thinking":        # 思考
                print(f"\033[35m 思考: {block.thinking}\033[0m")
                continue
            if block.type == "text":            # text
                print(f"\033[95m Text: {block.text}\033[0m")
                continue
            if block.type != "tool_use":        # 不是工具，就打印内容
                print(f"\033[95m {block.type}: 其他类型 \033[0m")
                continue
            output = execute_tool(block, TOOL_HANDLERS)
            if not output:
                output = f"已完成调用工具 block.name"
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": output})

        trigger_hooks("PostAllToolsUse", response, results)

        # 反馈工具的结果，循环继续进行
        messages.append({"role": "user", "content": results})

        trigger_hooks("EndOfLoop", messages, active_request)


def block_type(block):
    return block.get("type") if isinstance(block, dict) else getattr(block, "type", None)

def terminal_print(text: str):
    if threading.current_thread() is threading.main_thread() or not CLI_ACTIVE:
        print(text)
        return
    line = ""
    if READLINE_AVAILABLE:
        try:
            line = readline.get_line_buffer()
        except Exception:
            line = ""
    print(f"\r\033[K{text}")
    print(PROMPT + line, end="", flush=True)

def print_turn_assistants(messages: list, turn_start: int):
    for msg in messages[turn_start:]:
        if msg.get("role") != "assistant":
            continue
        for block in msg.get("content", []):
            if block_type(block) == "text":
                terminal_print(block["text"] if isinstance(block, dict) else block.text)


def async_event_loop(history: list, context: dict, session_state: dict):
    while True:
        time.sleep(1)
        with agent_lock:
            inbox = consume_lead_inbox()
            if not inbox:
                continue
            turn_start = len(history)
            scheduled_requests = []
            if inbox:
                history.append({"role": "user", "content": format_team_events(inbox)})
                terminal_print(f"  \033[33m[team auto] {len(inbox)} events\033[0m")
            active_request = (
                "\n".join(scheduled_requests)
                if scheduled_requests
                else session_state["active_user_request"]
            )
            agent_loop(history, context, active_request)
            context.update(update_context(context, history))
            print_turn_assistants(history, turn_start)



# ── Entry point ──────────────────────────────────────────
if __name__ == "__main__":
    print("\nCC 助手")
    print("输入问题，回车发送。输入 q 退出。\n")

    CLI_ACTIVE = True
    history = []
    had_teammates = False
    context = update_context({}, [])
    session_state = {"active_user_request": "(no active user request)"}
    threading.Thread(target=async_event_loop, args=(history, context, session_state), daemon=True).start()

    while True:
        try:
            query = CONSOLE.ask(PROMPT)
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        with agent_lock:
            trigger_hooks("UserPromptSubmit", query)
            turn_start = len(history)
            session_state["active_user_request"] = query
            history.append({"role": "user", "content": query})
            agent_loop(history, context, query)
            context = update_context(context, history)
            print_turn_assistants(history, turn_start)

        if active_teammates:
            had_teammates = True
        elif had_teammates and not BUS.peek("lead"):
            print("[all teammates shut down]")
            had_teammates = False
        print("")


"""
spawn_teammate 直接调这个工具,任命Alice为后端开发人员，任务是task_07e38f83
创建一个任务:创建一个名为“hello.py”的文件，该文件需输出“Hello, World!”这一信息。然后为每个任务创建工作区。任命Alice为后端开发人员，发送任务
创建一个任务:创建一个名为“hello.py”的文件，该文件需输出“Hello, World!”这一信息。任命Alice为后端开发人员，发送任务
创建一个任务:创建一个名为‘schema.sql’的文件，并在其中建立一个‘teacher’表。
1. 任命Alice为后端开发人员。要求她创建一个名为‘schema.sql’的文件，并在其中建立一个‘user’表。
2. 请查看您的收件箱，查看Alice的结果。
3. “创建Bob这个角色作为测试人员。要求他检查一下 schema.sql 文件是否存在，并列出其内容。”

把后端重构拆到共享任务板，在依赖允许时并行完成配置、认证和测试。
认证任务使用 worktree，保持现有接口，并在最后汇总结果。

开始吧
"""
"""
创建一个名为“hello.py”的文件，该文件需输出“Hello, World!”这一信息。
在当前目录下创建一个名为“test.txt”的文件
删除 test.txt
通过一个task 创建路径为 string_tools.py的文件，在其中实现一个接收字符串参数的slugify(text: str)函数，随后由父代理对该函数进行验证.请使用中文思考。
Load the code-review skill
加载代码审查功能并按照其说明操作

print(run_git(["rev-parse", "--show-toplevel"]))
"""