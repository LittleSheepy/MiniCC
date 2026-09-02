#!/usr/bin/env python3
from pathlib import Path

WORKDIR = Path.cwd()

HOOKS = {"UserPromptSubmit": [], "Start": [], "BeginOfLoop": [], "BeginOfCallLLM": [], "PreToolUse": [],
         "PostToolUse": [], "PreAllToolsUse": [], "PostAllToolsUse": [], "EndOfLoop": [], "Stop": []}

def register_hook(event: str, callback):
    HOOKS[event].append(callback)

def trigger_hooks(event: str, *args):
    for callback in HOOKS[event]:
        result = callback(*args)
        if result is not None:  # A hook result blocks this tool call.
            return result
    return None


# s03 permission check logic, now wrapped as a hook

def log_hook(block, *args):
    """PreToolUse: log every tool call."""
    args_preview = str(list(block.input.values())[:2])[:200]
    print(f"\033[90m[HOOK] {block.name}({args_preview})\033[0m")
    return None

def large_output_hook(block, output):
    """PostToolUse: warn on large output."""
    if len(str(output)) > 100000:
        print(f"\033[33m[HOOK] Large output from {block.name}: {len(str(output))} chars\033[0m")
    return None

# UserPromptSubmit hook: log user input before it reaches the LLM
def context_inject_hook(query: str):
    print(f"\033[90m[HOOK] UserPromptSubmit: 工作目录 {WORKDIR}\033[0m")
    return None

# Stop hook: 在循环即将结束时打印摘要信息
def summary_hook(messages: list, *args):
    tool_count = sum(1 for m in messages
                     for b in (m.get("content") if isinstance(m.get("content"), list) else [])
                     if isinstance(b, dict) and b.get("type") == "tool_result")
    print(f"\033[90m[HOOK] Stop: session used {tool_count} tool calls\033[0m")
    return None

register_hook("UserPromptSubmit", context_inject_hook)
register_hook("PreToolUse", log_hook)
register_hook("PostToolUse", large_output_hook)
register_hook("Stop", summary_hook)


if __name__ == "__main__":
    pass
