import re
from pathlib import Path

WORKDIR = Path.cwd()

WORKTREES_DIR = WORKDIR / ".worktrees"
WORKTREES_ROOT = WORKTREES_DIR.resolve()
VALID_WORKTREE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def task_worktree_cwd(task) -> tuple[Path, str | None]:
    return WORKDIR, None


def assignment_cwd(owner: str) -> Path:
    return WORKDIR

