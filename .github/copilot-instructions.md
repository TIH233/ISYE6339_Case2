# GitHub Copilot Instructions

You are working in a Python repository for a freight-network case study.

Use repository context before making changes:
- Project status and completed work: `Doc/Task.md`
- Methodology and reference process: `Doc/Paper.md`
- Data descriptions and schemas: `Doc/Data.md`

Use one of the two available Python environments when running Python:
- **conda** (preferred): `conda run -n General_env python`
- **venv** (fallback): `~/.venvs/general/bin/python3`

Prefer the repository's agent skills for specialized or multi-step tasks.
- Skills live under `.claude/skills/`
- When a task clearly matches an available skill, consult that skill's `SKILL.md` before implementing
- If multiple skills are relevant, combine them rather than inventing a new workflow in chat

Project-specific assumptions:
- Language: Python
- Focus on the Northeast megaregion case
- Exclude SCTG coal and gravel when applying commodity filters
- Treat truck-compatible freight as the main planning focus unless the task explicitly says otherwise

When working on case tasks:
- Check `Doc/Task.md` first to avoid repeating completed work
- Preserve existing outputs unless the task requires regeneration
- Prefer using documented project files and prior outputs over guesswork
