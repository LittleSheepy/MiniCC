#!/usr/bin/env python3
from pathlib import Path

import yaml

WORKDIR = Path.cwd()
SKILLS_DIR = WORKDIR / "skills"

class SkillLoader:
    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self.skills: dict[str, dict[str, str]] = {}
        self.scan()

    @staticmethod
    def parse_frontmatter(text: str) -> tuple[dict, str]:
        if not text.startswith("---"):
            return {}, text
        parts = text.split("---", 2)
        if len(parts) < 3:
            return {}, text
        try:
            metadata = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError:
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        return metadata, parts[2].lstrip()

    def scan(self):
        self.skills.clear()
        if not self.skills_dir.exists():
            return

        for manifest in sorted(self.skills_dir.glob("*/SKILL.md")):
            content = manifest.read_text(encoding="utf-8")
            metadata, body = self.parse_frontmatter(content)
            name = str(metadata.get("name") or manifest.parent.name).strip()
            description = metadata.get("description") or body.splitlines()[0]
            description = " ".join(str(description).lstrip("# ").split())
            self.skills[name] = {
                "name": name,
                "description": description,
                "content": content,
            }

    def catalog(self) -> str:
        if not self.skills:
            return "(no skills found)"
        return "\n".join(
            f"- {skill['name']}: {skill['description']}"
            for skill in self.skills.values()
        )

    def load(self, name: str) -> str:
        skill = self.skills.get(name)
        if skill:
            return skill["content"]
        available = ", ".join(self.skills) or "none"
        return f"Error: Unknown skill '{name}'. Available: {available}"


SKILL_LOADER = SkillLoader(SKILLS_DIR)

PROMPT_SECTIONS_SKILLS = {
    "skills":f"可用技能:\n{SKILL_LOADER.catalog()}"
}

def build_system_prompt() -> str:
    return (
        f"You are a coding agent at {WORKDIR}. Use tools to solve tasks. "
        "Act, don't explain.\n\n"
        f"Skills available:\n{SKILL_LOADER.catalog()}\n\n"
        "Use load_skill to read the full instructions when a skill applies."
    )


SYSTEM = build_system_prompt()


TOOLS_SKILLS = [
    {"name": "load_skill", "description": "Load the full SKILL.md content by skill name.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
]

TOOL_HANDLERS_SKILLS = {"load_skill": SKILL_LOADER.load}




if __name__ == "__main__":
    SKILL_LOADER = SkillLoader(SKILLS_DIR)
    print(f"Skills available:\n{SKILL_LOADER.catalog()}\n\n")
