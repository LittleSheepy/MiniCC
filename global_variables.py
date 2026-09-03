""""""
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
WORKDIR = Path.cwd()

# task
task_lock = threading.RLock()

@dataclass
class Task:
    id: str
    subject: str
    description: str
    status: str                     # pending | in_progress | completed  待定 | 进行中 | 已完成
    owner: str | None
    blockedBy: list[str]
    worktree: str | None = None

# team
# working | waiting_approval | idle | stopping
active_teammates: dict[str, str] = {}
plan_gates: dict[str, str] = {}
plan_request_ids: dict[str, str] = {}
team_lock = threading.RLock()
# 每个团队成员只会接一项任务，并且每个文件系统工具都是通过这个注册表来确定其当前工作目录的。
teammate_assignments: dict[str, dict[str, object]] = {}
assignment_versions: dict[str, int] = {}
RESERVED_TEAMMATE_NAMES = {"lead", "agent"}

# MessageBus

IDLE_SCAN_INTERVAL = 2.0
@dataclass
class ProtocolState:
    request_id: str
    type: str
    sender: str
    target: str
    status: str
    payload: str
    work_version: int | None = None
    task_id: str | None = None
    created_at: float = field(default_factory=time.time)


pending_requests: dict[str, ProtocolState] = {}


# MCP









