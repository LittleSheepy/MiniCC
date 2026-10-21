#!/usr/bin/env python3
import json
import sys
import os
import re
import secrets
import threading
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from global_variables import task_lock, teammate_assignments, assignment_versions, Task

if sys.platform == "win32":
    import msvcrt
    def _lock(f): msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
    def _unlock(f): msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl
    def _lock(f): fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    def _unlock(f): fcntl.flock(f.fileno(), fcntl.LOCK_UN)


WORKDIR = Path.cwd()
TASKS_DIR = WORKDIR / ".tasks"
TASKS_ROOT = TASKS_DIR.resolve()
TASK_ID_PATTERN = re.compile(r"^task_[0-9a-f]{8}$")

"""
    多线程锁
"""
TASK_LOCK_PATH = TASKS_DIR / ".lock"
_task_store_state = threading.local()

def advance_assignment_version(owner: str):
    """Invalidate old approvals without clearing an explicit plan requirement.在未明确遵循计划要求的情况下就撤销旧的审批决定。"""
    with task_lock:
        assignment_versions[owner] = assignment_versions.get(owner, 0) + 1
        gates = globals().get("plan_gates")
        request_ids = globals().get("plan_request_ids")
        team = globals().get("team_lock")
        if team is not None:
            team.acquire()
        try:
            if isinstance(gates, dict) and gates.get(owner, "") != "not_required":
                gates[owner] = "required"
            if isinstance(request_ids, dict):
                request_ids.pop(owner, None)
        finally:
            if team is not None:
                team.release()


def release_completed_assignment(owner: str) -> bool:
    """Release a completed cwd lease only at a model turn boundary."""
    with task_lock:
        assignment = teammate_assignments.get(owner)
        if not assignment:
            return False
        task = load_task(str(assignment["task_id"]))
        if task.status != "completed" or task.owner != owner:
            return False
        teammate_assignments.pop(owner, None)
        advance_assignment_version(owner)
        if owner in globals().get("plan_gates", {}):
            globals()["plan_gates"][owner] = "not_required"
        return True


def release_teammate_assignment(owner: str):
    """Return abandoned teammate work to the task board on thread exit."""
    with task_lock:
        try:
            task = _owner_in_progress(owner)
            if task:
                task.status = "pending"
                task.owner = None
                save_task(task)
        finally:
            teammate_assignments.pop(owner, None)
            advance_assignment_version(owner)
            if owner in globals().get("plan_gates", {}):
                globals()["plan_gates"][owner] = "not_required"

@contextmanager
def task_store_lock():
    """在各个线程和主机进程中对任务的变更进行序列化处理。"""
    with task_lock:
        depth = getattr(_task_store_state, "depth", 0)
        if depth == 0:
            TASKS_DIR.mkdir(parents=True, exist_ok=True)
            handle = TASK_LOCK_PATH.open("a+")
            # 加排他锁（阻塞等待）
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            _task_store_state.handle = handle
        _task_store_state.depth = depth + 1
        try:
            yield
        finally:
            _task_store_state.depth -= 1
            if _task_store_state.depth == 0:
                handle = _task_store_state.handle
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                handle.close()
                del _task_store_state.handle


def _task_path(task_id: str) -> Path:
    if not isinstance(task_id, str) or not TASK_ID_PATTERN.fullmatch(task_id):
        raise ValueError(f"Invalid task ID: {task_id!r}")
    path = (TASKS_DIR / f"{task_id}.json").resolve()
    if not TASKS_ROOT.is_relative_to(WORKDIR.resolve()) or not path.is_relative_to(TASKS_ROOT):
        raise ValueError(f"Invalid task ID: {task_id!r}")
    return path

def _owner_in_progress(owner: str) -> Task | None:
    return next((task for task in list_tasks() if task.status == "in_progress" and task.owner == owner), None)

class TaskStore:
    def __init__(self, directory: Path):
        self.directory = directory

    def _root(self, create: bool = False) -> Path:
        if create:
            self.directory.mkdir(parents=True, exist_ok=True)
        root = self.directory.resolve()
        if not root.is_relative_to(WORKDIR.resolve()):
            raise ValueError("任务目录不在工作区")
        return root

    def _path(self, task_id: str, create_root: bool = False) -> Path:
        if not isinstance(task_id, str) or not TASK_ID_PATTERN.fullmatch(task_id):
            raise ValueError(f"Invalid task ID: {task_id!r}")
        root = self._root(create=create_root)
        path = (root / f"{task_id}.json").resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"Invalid task ID: {task_id!r}")
        return path

    def exists(self, task_id: str) -> bool:
        return self._path(task_id).is_file()

    def create(self, subject: str, description: str = "", blocked_by: list[str] | None = None) -> Task:
        subject = subject.strip()
        if not subject:
            raise ValueError("任务主题不能为空")

        dependencies = list(dict.fromkeys(blocked_by or []))
        with task_store_lock():
            for dependency in dependencies:
                if not _task_path(dependency).is_file():
                    raise ValueError(f"Dependency not found: {dependency}")
            for _ in range(100):
                task = Task(f"task_{secrets.token_hex(4)}", subject, description, "pending", None, dependencies)
                try:
                    with _task_path(task.id).open("x", encoding="utf-8") as handle:
                        json.dump(asdict(task), handle, indent=2, ensure_ascii=False)
                    return task
                except FileExistsError:
                    continue
        raise RuntimeError("Could not allocate a unique task ID")

    def save(self, task: Task) -> None:
        with task_store_lock():
            path = _task_path(task.id)
            temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
            try:
                temporary.write_text(json.dumps(asdict(task), indent=2, ensure_ascii=False), encoding="utf-8")
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)

    def load(self, task_id: str) -> Task:
        with task_lock:
            data = json.loads(_task_path(task_id).read_text(encoding="utf-8"))
            task = Task(**data)
            if task.id != task_id:
                raise ValueError(f"Task file ID does not match {task_id}")
            if task.status not in {"pending", "in_progress", "completed"}:
                raise ValueError(f"Invalid task status: {task.status}")
            return task

    def list(self) -> list[Task]:
        with task_lock:
            if not self.directory.exists():
                return []
            root = self._root()
            return [self.load(path.stem) for path in sorted(root.glob("task_*.json"))]


TASKS = TaskStore(TASKS_DIR)


def create_task(subject: str, description: str = "", blockedBy: list[str] | None = None) -> Task:
    return TASKS.create(subject, description, blockedBy)

def save_task(task: Task):
    TASKS.save(task)

def load_task(task_id: str) -> Task:
    return TASKS.load(task_id)


def list_tasks() -> list[Task]:
    return TASKS.list()


def get_task(task_id: str) -> str:
    return json.dumps(asdict(load_task(task_id)), indent=2, ensure_ascii=False)

def get_task_json(task_id: str) -> str:
    return json.dumps(asdict(load_task(task_id)), indent=2, ensure_ascii=False)


def incomplete_dependencies(task: Task) -> list[str]:
    incomplete = []
    for dependency in task.blockedBy:
        try:
            dep_path = _task_path(dependency)
            if not dep_path.exists() or load_task(dependency).status != "completed":
                incomplete.append(dependency)
        except (FileNotFoundError, ValueError):
            incomplete.append(dependency)
    return incomplete


def can_start(task_id: str) -> bool:
    return not incomplete_dependencies(load_task(task_id))

# 获取一个依赖项已完成的待办任务。
def claim_task(task_id: str, owner: str = "agent") -> str:
    from worktrees import task_worktree_cwd
    """Atomically claim one task and bind the owner's filesystem cwd."""
    with task_store_lock():
        task = load_task(task_id)
        if task.status != "pending":
            return f"Task {task_id} is {task.status}, cannot claim"
        if task.owner:
            return f"Task {task_id} is already owned by {task.owner}"

        assignment = teammate_assignments.get(owner)
        if assignment:
            return f"所有者 {owner} 必须先完成当前任务 {assignment['task_id']} 的工作轮次，才能申领下一个任务"
        current = _owner_in_progress(owner)
        if current:
            return (f"所有者 {owner} 必须先完成 {current.id}，才能申领其他任务")

        if not can_start(task_id):
            return f"Blocked by: {incomplete_dependencies(task)}"
        cwd, error = task_worktree_cwd(task)
        if error:
            return f"Cannot claim {task_id}: {error}"
        task.owner = owner
        task.status = "in_progress"
        save_task(task)
        teammate_assignments[owner] = {"task_id": task.id, "cwd": cwd}
        advance_assignment_version(owner)
    print(f"  [claim] {task.subject} -> in_progress (owner: {owner})")
    return f"Claimed {task.id} ({task.subject})"

# def complete_task(task_id: str, owner: str = "agent") -> str:
#     task = load_task(task_id)
#     if task.status != "in_progress":
#         return f"Task {task_id} is {task.status}, cannot complete"
#     if task.owner != owner:
#         return f"Task {task_id} is owned by {task.owner}, not {owner}"
#     ready_before = {
#         candidate.id
#         for candidate in list_tasks()
#         if candidate.status == "pending"
#         and candidate.blockedBy
#         and can_start(candidate.id)
#     }
#     task.status = "completed"
#     TASKS.save(task)
#     unblocked = [candidate.subject for candidate in list_tasks()
#                  if candidate.status == "pending"
#                  and candidate.blockedBy
#                  and candidate.id not in ready_before
#                  and can_start(candidate.id)]
#     print(f"  [complete] {task.subject}")
#     message = f"Completed {task.id} ({task.subject})"
#     if unblocked:
#         message += f"\nUnblocked: {', '.join(unblocked)}"
#         print(f"  [unblocked] {', '.join(unblocked)}")
#     return message

def complete_task(task_id: str, owner: str = "agent") -> str:
    from worktrees import task_worktree_cwd
    """Complete an assignment only when the caller owns it."""
    with task_store_lock():
        task = load_task(task_id)
        if task.status != "in_progress":
            return f"Task {task_id} is {task.status}, cannot complete"
        if task.owner != owner:
            return f"Task {task_id} is owned by {task.owner}, not {owner}; cannot complete"
        gate = globals().get("plan_gates", {}).get(owner, "not_required")
        if gate in {"required", "pending", "rejected"}:
            return f"Task {task_id} cannot complete while plan status is {gate}"
        assignment = teammate_assignments.get(owner)
        if not assignment or assignment.get("task_id") != task.id:
            cwd, error = task_worktree_cwd(task)
            if error:
                return f"Task {task_id} cannot complete: {error}"
            teammate_assignments[owner] = {"task_id": task.id, "cwd": cwd}
        task.status = "completed"
        save_task(task)
        unblocked = [t.subject for t in list_tasks()
                     if t.status == "pending" and t.blockedBy and can_start(t.id)]
    print(f"  [complete] {task.subject}")
    msg = f"Completed {task.id} ({task.subject})"
    if unblocked:
        msg += f"\nUnblocked: {', '.join(unblocked)}"
        print(f"  [unblocked] {', '.join(unblocked)}")
    return msg

def run_create_task(subject: str, description: str = "", blockedBy: list[str] | None = None) -> str:
    task = create_task(subject, description, blockedBy)
    deps = f" (blockedBy: {', '.join(blockedBy)})" if blockedBy else ""
    print(f"  \033[34m[create] {task.subject}{deps}\033[0m")
    return f"Created {task.id}: {task.subject}{deps}"

def run_list_tasks() -> str:
    tasks = list_tasks()
    if not tasks:
        return "No tasks. Use create_task to add some."
    lines = []
    for t in tasks:
        icon = {"pending": "[ ]", "in_progress": "[~]", "completed": "[x]"}.get(t.status, "[?]")
        deps = f" (blockedBy: {', '.join(t.blockedBy)})" if t.blockedBy else ""
        owner = f" [{t.owner}]" if t.owner else ""
        worktree = f" (worktree: {t.worktree})" if t.worktree else ""
        lines.append(f"  {icon} {t.id}: {t.subject} [{t.status}]{owner}{deps}{worktree}")
    return "\n".join(lines)


def run_get_task(task_id: str) -> str:
    try:
        return get_task(task_id)
    except ValueError as exc:
        return f"Error: {exc}"
    except FileNotFoundError:
        return f"Error: Task {task_id} not found"



def run_claim_task(task_id: str) -> str:
    try:
        return claim_task(task_id, owner="agent")
    except ValueError as exc:
        return f"Error: {exc}"
    except FileNotFoundError:
        return f"Error: Task {task_id} not found"


def run_complete_task(task_id: str) -> str:
    try:
        return complete_task(task_id, owner="agent")
    except ValueError as exc:
        return f"Error: {exc}"
    except FileNotFoundError:
        return f"Error: Task {task_id} not found"

TOOLS_TASK = [
    {"name": "create_task",
     "description": "Create a task with optional dependencies.",
     "input_schema": {"type": "object",
                      "properties": {
                          "subject": {"type": "string"},
                          "description": {"type": "string"},
                          "blockedBy": {"type": "array",
                                        "items": {"type": "string"}}},
                      "required": ["subject"]}},
    {"name": "list_tasks", "description": "List shared tasks.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_task", "description": "Get one task by ID.",
     "input_schema": {"type": "object",
                      "properties": {"task_id": {"type": "string"}},
                      "required": ["task_id"]}},
    {"name": "claim_task", "description": "Claim a ready task.",
     "input_schema": {"type": "object",
                      "properties": {"task_id": {"type": "string"}},
                      "required": ["task_id"]}},
    {"name": "complete_task", "description": "Complete an owned task.",
     "input_schema": {"type": "object",
                      "properties": {"task_id": {"type": "string"}},
                      "required": ["task_id"]}},
]

TOOL_HANDLERS_TASK = {
    "create_task": run_create_task,
    "list_tasks": run_list_tasks,
    "get_task": run_get_task,
    "claim_task": run_claim_task,
    "complete_task": run_complete_task,
}

"""
创建任务：建立数据库架构、创建 API 端点（取决于架构）、编写测试（取决于端点）、编写文档（取决于架构）
列出所有任务及其状态
选取第一个未被阻塞的任务并完成它
再次列出任务——哪些任务现在已不再受阻？
"""
