#!/usr/bin/env python3
from hooks import trigger_hooks

def execute_tool(block, handlers: dict) -> str:
    blocked = trigger_hooks("PreToolUse", block, True)
    if blocked:
        return str(blocked)

    handler = handlers.get(block.name)
    try:
        output = handler(**block.input) if handler else f"Unknown: {block.name}"
    except Exception as exc:
        output = f"Error: {type(exc).__name__}: {exc}"

    trigger_hooks("PostToolUse", block, output)
    return str(output)




