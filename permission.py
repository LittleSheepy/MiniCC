#!/usr/bin/env python3
"""
permission.py - 权限系统
在工具执行前插入了三个检查门：
门 1：硬拒绝列表（rm -rf /、sudo 等）
门 2：规则匹配（工作区外的写操作？破坏性命令？）
门 3：用户批准（暂停并等待确认）
"""
from pathlib import Path

from hooks import register_hook
from mcp_plugin import check_rules_mcp
from console_broker import CONSOLE
WORKDIR = Path.cwd()

# 门 1：严格拒绝名单 - 一律禁止执行
DENY_LIST = ["rm -rf /", "sudo", "shutdown", "reboot", "mkfs", "dd if=", "> /dev/sda"]

def check_deny_list(command: str):
    for pattern in DENY_LIST:
        if pattern in command:
            print(f"\n\033[31m[blocked] Blocked: '{pattern}' is on the deny list\033[0m")
            return True
    return None

# Gate 2: 规则匹配 - context-dependent checks
DESTRUCTIVE = ["rm ", "del ", "> /etc/", "chmod 777"]
PERMISSION_RULES = [
    {"tools": ["read_file", "write_file", "edit_file"],
     "check": lambda args: not (WORKDIR / args.get("path", "")).resolve().is_relative_to(WORKDIR),
     "message": "在工作区域之外操作"},
    {"tools": ["bash"],
     "check": lambda args: any(kw in args.get("command", "") for kw in DESTRUCTIVE),
     "message": "具有破坏性的命令"},
]

def check_rules(tool_name: str, args: dict) -> str | None:
    for rule in PERMISSION_RULES:
        if tool_name in rule["tools"] and rule["check"](args):
            return rule["message"]
        if tool_name in rule["tools"] and rule["check"](args):
            return rule["message"]
    reason = check_rules_mcp(tool_name, args)
    if reason:
        return reason
    return None


# Gate 3: 用户审批 - 在规则匹配后等待确认
def ask_user(tool_name: str, args: dict, reason: str) -> str:
    print(f"\n\033[33m[permission] {reason}\033[0m")
    print(f"   Tool: {tool_name}({args})")
    choice = CONSOLE.ask("  Allow? [y/N] ").strip().lower()
    return "allow" if choice in ("y", "yes") else "deny"


def check_permission(block, prompt_user: bool = True) -> str | None:
    if block.name == "bash":
        command = block.input.get("command", "")
        reason = check_deny_list(command)
        if reason:
            return f"bash命令在禁止执行列表：{command}"
        if any(keyword in command for keyword in DESTRUCTIVE):
            if not prompt_user:
                return "Permission required: ask Lead to run this command."
            print(f"\n[permission] {block.name}({block.input})")
            choice = CONSOLE.ask("  Allow? [y/N] ").strip().lower()
            if choice not in {"y", "yes"}:
                return "Permission denied by user"

    reason = check_rules(block.name, block.input)
    if reason:
        if not prompt_user:
            return reason
        decision = ask_user(block.name, block.input, reason)
        if decision == "deny":
            return f"用户拒绝授权执行 Tool: {block.name}({block.input})。"
    return None

def permission_hook(block, prompt_user: bool = True):
    return check_permission(block, prompt_user=prompt_user)

register_hook("PreToolUse", permission_hook)

if __name__ == "__main__":
    from dataclasses import dataclass
    @dataclass
    class Block:
        name: str
        input: dict
    block = Block(name="bash", input={"command":"rm "})
    print(permission_hook(block))
    pass