#!/usr/bin/env python3
import ast
import json

from hooks import register_hook

class TodoManager:
    def __init__(self):
        self.items: list[dict] = []

    def update(self, todos: list | str) -> str:
        if isinstance(todos, str):
            try:
                todos = json.loads(todos)
            except json.JSONDecodeError:
                try:
                    todos = ast.literal_eval(todos)
                except (SyntaxError, ValueError) as e:
                    raise ValueError("todos must be a list or JSON array string") from e

        if not isinstance(todos, list):
            raise ValueError("todos must be a list")
        if len(todos) > 20:
            raise ValueError("Max 20 todos allowed")

        validated = []
        in_progress_count = 0
        for index, todo in enumerate(todos):
            if not isinstance(todo, dict):
                raise ValueError(f"todos[{index}] must be an object")

            content = str(todo.get("content", "")).strip()
            status = str(todo.get("status", "pending")).lower()
            if not content:
                raise ValueError(f"todos[{index}] requires content")
            if status not in ("pending", "in_progress", "completed"):
                raise ValueError(f"todos[{index}] has invalid status '{status}'")
            if status == "in_progress":
                in_progress_count += 1
            validated.append({"content": content, "status": status})

        if in_progress_count > 1:
            raise ValueError("Only one todo can be in_progress at a time")

        self.items = validated
        return self.render()

    def render(self) -> str:
        if not self.items:
            return "No todos."

        lines = []
        for todo in self.items:
            marker = {
                "pending": "[ ]",
                "in_progress": "[>]",
                "completed": "[x]",
            }[todo["status"]]
            lines.append(f"{marker} {todo['content']}")

        done = sum(todo["status"] == "completed" for todo in self.items)
        lines.append(f"\n({done}/{len(self.items)} completed)")
        return "\n".join(lines)


TODO = TodoManager()


def run_todo_write(todos: list | str) -> str:
    try:
        output = TODO.update(todos)
    except ValueError as e:
        return f"Error: {e}"
    print(f"\n\033[33m## Current Tasks\033[0m\n{output}")
    return output

TOOLS_TODOWRITE = [
    {"name": "todo_write", "description": "Create and manage a task list for your current coding session.",
     "input_schema": {"type": "object",
                      "properties": {
                          "todos": {
                              "type": "array",
                              "maxItems": 20,
                              "items": {
                                  "type": "object",
                                  "properties": {
                                      "content": {"type": "string", "minLength": 1},
                                      "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]}
                                  },
                                  "required": ["content", "status"]
                              }
                          }
                      },
                      "required": ["todos"]
                      }},
]

TOOL_HANDLERS_TODOWRITE = {"todo_write": run_todo_write}


rounds_since_todo = 0
def reminder_todo_hook(response, results: list):
    global rounds_since_todo
    used_todo = False
    for block in response.content:
        if block.type != "tool_use":        # 不是工具，就打印内容
            continue
        if block.name == "todo_write":
            used_todo = True
            break
    rounds_since_todo = 0 if used_todo else rounds_since_todo + 1
    if rounds_since_todo >= 2:
        results.append({"type": "text", "text": "<reminder>Update your todos.</reminder>"})
        rounds_since_todo = 0
    return None

register_hook("PostAllToolsUse", reminder_todo_hook)

