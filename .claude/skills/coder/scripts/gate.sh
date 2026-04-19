#!/usr/bin/env zsh
# gate.sh — Commit/rollback gate for subtask completion
#
# Usage:
#   .claude/skills/coder/scripts/gate.sh status              # show uncommitted changes
#   .claude/skills/coder/scripts/gate.sh commit "message"     # stage + commit + push
#   .claude/skills/coder/scripts/gate.sh rollback             # hard reset to HEAD
#
# This script wraps the decision point at the end of every subtask.
# The coder skill calls it after sanity checks pass (or fail).

set -euo pipefail

ACTION=${1:?"Usage: gate.sh {status|commit|rollback} ['commit message']"}
MSG=${2:-""}

case "$ACTION" in
  status)
    echo "══════════════════════════════════════════════════"
    echo "  GATE — Uncommitted Changes"
    echo "══════════════════════════════════════════════════"
    git diff --stat HEAD
    echo ""
    echo "Untracked files:"
    git ls-files --others --exclude-standard
    echo "══════════════════════════════════════════════════"
    ;;

  commit)
    if [[ -z "$MSG" ]]; then
      echo "Error: commit message required."
      echo "Usage: gate.sh commit 'Task N — subtask description'"
      exit 1
    fi
    echo "══════════════════════════════════════════════════"
    echo "  GATE — Committing"
    echo "══════════════════════════════════════════════════"
    echo "Message: $MSG"
    echo ""
    ./git_tools.sh sync "$MSG"
    echo "══════════════════════════════════════════════════"
    ;;

  rollback)
    echo "══════════════════════════════════════════════════"
    echo "  GATE — Rolling back to last commit"
    echo "══════════════════════════════════════════════════"
    echo "Changes that will be discarded:"
    git diff --stat HEAD
    echo ""
    git reset --hard HEAD
    echo "Rollback complete."
    echo "══════════════════════════════════════════════════"
    ;;

  *)
    echo "Usage: gate.sh {status|commit|rollback} ['commit message']"
    exit 1
    ;;
esac
