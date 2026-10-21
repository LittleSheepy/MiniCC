#!/usr/bin/env python3

import threading

from agent_loop import async_event_loop, PROMPT, agent_lock, agent_loop, print_turn_assistants
from hooks import trigger_hooks

READLINE_AVAILABLE = True


from assembly_prompt import update_context
from console_broker import CONSOLE

from teams import active_teammates, BUS

if __name__ == "__main__":
    print("\nMiniCC 助手")
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