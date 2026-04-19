#!/usr/bin/env zsh
# preflight.sh — Pull task context from project knowledge base before coding
#
# Usage:
#   .claude/skills/coder/scripts/preflight.sh <task_number> [data_file ...]
#
# What it does:
#   1. Extracts the task block from Doc/Task.md  (status, methodology, outputs)
#   2. Extracts the matching reference methodology from Doc/Paper.md
#   3. Pulls data-file schemas from Doc/Data.md for any files listed as arguments
#
# Example:
#   .claude/skills/coder/scripts/preflight.sh 3 raw.parquet ne_state_summary.csv

set -euo pipefail

TASK_NUM=${1:?"Usage: preflight.sh <task_number> [data_file ...]"}
shift
DATA_FILES=("$@")

# ── Task-to-Paper section mapping ────────────────────────────────────
# Each task maps to one or more §-headers in Doc/Paper.md.
# Multiple patterns separated by | are searched independently.
declare -A PAPER_MAP
PAPER_MAP=(
  [1]="§2.1"
  [2]="§2.1"
  [3]="§2.2"
  [4]="§2.3|§2.5"
  [5]="§2.3"
  [6]="§2.4|§2.5"
  [7]="§2.3|§2.4|§2.5"
  [8]="§2.6"
  [9]=""   # synthesis — no single methodology section
)

echo "══════════════════════════════════════════════════"
echo "  PREFLIGHT — Task $TASK_NUM"
echo "══════════════════════════════════════════════════"

# ── 1. Task status & plan from Task.md ───────────────────────────────
echo ""
echo "── Task Status & Plan ─────────────────────────────"
TASK_BLOCK=$(awk "/^### Task $TASK_NUM /{flag=1; print; next} /^###/{if(flag) exit} flag" Doc/Task.md)
if [[ -z "$TASK_BLOCK" ]]; then
  echo "  ⚠  No entry found for Task $TASK_NUM in Doc/Task.md"
else
  echo "$TASK_BLOCK"
fi

# Parse status tag from the header line
STATUS=$(echo "$TASK_BLOCK" | head -1 | grep -oE '\[.*\]' || echo "[unknown]")
echo ""
echo "  → Parsed status: $STATUS"

# ── 2. Reference methodology from Paper.md ──────────────────────────
echo ""
echo "── Reference Methodology (Paper.md) ───────────────"
SECTION_KEY=${PAPER_MAP[$TASK_NUM]:-""}
if [[ -n "$SECTION_KEY" ]]; then
  IFS='|' read -rA PATTERNS <<< "$SECTION_KEY"
  for pat in "${PATTERNS[@]}"; do
    awk "/^### .*${pat}/{flag=1; print; next} /^###/{if(flag) exit} flag" Doc/Paper.md
    echo ""
  done
else
  echo "  (No direct methodology mapping for Task $TASK_NUM)"
fi

# ── 3. Data file schemas from Data.md ────────────────────────────────
if [[ ${#DATA_FILES[@]} -gt 0 ]]; then
  echo "── Data Schemas ─────────────────────────────────────"
  for file in "${DATA_FILES[@]}"; do
    SCHEMA=$(awk "/^## .*${file}/{flag=1; print; next} /^#/{if(flag) exit} flag" Doc/Data.md)
    if [[ -z "$SCHEMA" ]]; then
      echo "  ⚠  No schema found for '$file' in Doc/Data.md"
    else
      echo "$SCHEMA"
    fi
    echo ""
  done
fi

echo "══════════════════════════════════════════════════"
echo "  Preflight complete.  Status: $STATUS"
echo "══════════════════════════════════════════════════"
