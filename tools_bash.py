#!/usr/bin/env python3
import os
import subprocess
from pathlib import Path
WORKDIR = Path.cwd()

TOOLS_BASH = [{
    "name": "bash",
    "description": "运行一个 shell 命令。",
    "input_schema": {
        "type": "object",
        "properties": {"command": {"type": "string"}},
        "required": ["command"],
    },
}]


def run_bash(command: str, cwd: Path | None = None) -> str:
    try:
        result = subprocess.run(command, shell=True, cwd=cwd or WORKDIR,
            capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
        output = (result.stdout + result.stderr).strip()
        output = output[:50000] if output else "(no output)"
        if result.returncode:
            return f"Error: command exited with status {result.returncode}\n{output}"
        return output
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"
    except OSError as exc:
        return f"Error: {type(exc).__name__}: {exc}"

TOOL_HANDLERS_BASH = {
    "bash": run_bash
}

if __name__ == "__main__":
    output = run_bash("""echo print("Hello, World!") > hello.py""")
    print(output[:1000])