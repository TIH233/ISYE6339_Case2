---
name: retriever
description: >
  LLM-only knowledge-base retriever for this project. Use this skill whenever you need to look up
  the documentation for a specific data file (its schema, path, column types, context) or a specific
  task (its objective, methodology, status, key outputs) before writing code or making a plan.
  Trigger on any internal need like "what columns does raw.parquet have?", "what did Task 2 do?",
  "what is the path to ne_state_summary.csv?", "what is the status of Task 3?".
  Always call this before touching a data file you haven't read yet, or before starting / resuming a task.
user-invocable: false
allowed-tools: Bash
---

# Retriever — Project Knowledge Base Lookup

This skill extracts a single targeted documentation block from one of two project knowledge bases.
It exists so you never have to read an entire file to get one section — just run the right Bash command
and the relevant block is printed to stdout, surfacing directly in your context.

## The two knowledge bases

| File | What it documents | Header level |
|------|-------------------|--------------|
| `Doc/Data.md` | Schema, path, shape, column types, and context for every data file | `##` |
| `Doc/Task.md` | Objective, methodology implemented, status, and key outputs for every task | `###` |

---

## How to call this skill

Identify which knowledge base you need and what you are looking for, then choose a mode.

### Mode A — Targeted fetch (you already know the name)

**Looking up a data file in Data.md:**
The query is the filename (or a distinctive substring of it). The header in Data.md looks like
`` ## `raw.parquet` — Full NE county-to-county O-D flow matrix ``, so any unique part of the filename works.

```bash
awk '/^## .*QUERY/{flag=1; print; next} /^#/{if(flag) exit} flag' Doc/Data.md
```

Example — get the schema for `raw.parquet`:
```bash
awk '/^## .*raw\.parquet/{flag=1; print; next} /^#/{if(flag) exit} flag' Doc/Data.md
```

Example — get the schema for `ne_state_summary.csv`:
```bash
awk '/^## .*ne_state_summary/{flag=1; print; next} /^#/{if(flag) exit} flag' Doc/Data.md
```

**Looking up a task in Task.md:**
The query is the task number or a distinctive word from its title. The header looks like
`### Task 1 — County-to-County Freight Flow Matrix`.

```bash
awk '/^### .*QUERY/{flag=1; print; next} /^###/{if(flag) exit} flag' Doc/Task.md
```

Example — get the full entry for Task 2:
```bash
awk '/^### Task 2/{flag=1; print; next} /^###/{if(flag) exit} flag' Doc/Task.md
```

> **Why awk here:** The command sets a flag at the matching header, prints every line until the
> next same-level header is found, then immediately exits — it never reads the rest of the file.
> This keeps token usage minimal when the files grow.

---

### Mode B — Table of Contents (you need to discover what's available)

Use this when you are unsure of the exact name to query. It prints only the headers — one line per entry.

```bash
# List all documented data files
grep "^## " Doc/Data.md

# List all tasks
grep "^### " Doc/Task.md
```

Read the list, identify the exact header name, then switch to Mode A for the full block.

---

## Execution steps

1. Decide: am I looking up a **data file** (→ Data.md) or a **task** (→ Task.md)?
2. Do I know the exact name? → Mode A. Unsure? → Mode B first, then Mode A.
3. Run the Bash command. The output is your retrieved documentation block.
4. Use that block to inform your next action (writing code, planning, loading the file, etc.).
5. Do **not** open or read the actual data files (`.parquet`, `.csv`) just to learn their schema —
   Data.md already has everything you need.

---

## Quick reference card

```
Data file schema    → awk '/^## .*FILENAME/{flag=1; print; next} /^#/{if(flag) exit} flag' Doc/Data.md
Task documentation  → awk '/^### TASK_NAME/{flag=1; print; next} /^###/{if(flag) exit} flag' Doc/Task.md
List all data files → grep "^## " Doc/Data.md
List all tasks      → grep "^### " Doc/Task.md
```
