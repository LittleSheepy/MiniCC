#!/usr/bin/env python3
from pathlib import Path

from hooks import trigger_hooks
from model import client, MODEL
from prompts import SUB_SYSTEM
from utils import execute_tool
from tools_bash import TOOLS_BASH, TOOL_HANDLERS_BASH
from tools_file import TOOLS_FILE, TOOL_HANDLERS_FILE

SUB_TOOLS = TOOLS_BASH + TOOLS_FILE
SUB_HANDLERS = TOOL_HANDLERS_BASH | TOOL_HANDLERS_FILE


def extract_text(content) -> str:
    if not isinstance(content, list):
        return str(content)
    return "\n".join(
        getattr(block, "text", "")
        for block in content
        if getattr(block, "type", None) == "text"
    )


def run_subagent(prompt: str) -> str:
    print("\n\033[35m[Subagent started]\033[0m")
    messages = [{"role": "user", "content": prompt}]

    for _ in range(30):
        response = client.messages.create(model=MODEL, system=SUB_SYSTEM, messages=messages,tools=SUB_TOOLS, max_tokens=8000)

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            force = trigger_hooks("Stop", messages)
            if force:
                messages.append({"role": "user", "content": force})
                continue
            print("\033[35m[Subagent done]\033[0m")
            return extract_text(response.content) or "(no summary)"

        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            output = execute_tool(block, SUB_HANDLERS)
            print(f"  \033[90m[sub] {block.name}: {output[:100]}\033[0m")
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": output,
            })
        messages.append({"role": "user", "content": results})

    print("\033[35m[Subagent stopped]\033[0m")
    return "Subagent stopped after 30 turns without a final answer."


TOOLS_SUBAGENT = [{
    "name": "subagent",
    "description": "运行一个子代理，使其具备全新的对话情境，并返回其最终的文本内容。",
    "input_schema": {
        "type": "object",
        "properties": {"prompt": {"type": "string", "minLength": 1}},
        "required": ["prompt"],
    },
}]

TOOL_HANDLERS_SUBAGENT = {"subagent": run_subagent}


if __name__ == "__main__":
    result = run_subagent("你好")
    print(result)