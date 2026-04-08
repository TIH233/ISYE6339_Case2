#!/usr/bin/env zsh

# A simple wrapper for standard Git operations.
# Usage:
#   ./git_tools.sh status
#   ./git_tools.sh commit "Your message here"
#   ./git_tools.sh pull
#   ./git_tools.sh sync "Optional commit message"

COMMAND=$1
MSG=$2

case "$COMMAND" in
    "status")
        echo "Checking repository status..."
        git status -s
        ;;
    "commit")
        if [ -z "$MSG" ]; then
            echo "Error: Please provide a commit message."
            echo "Usage: ./git_tools.sh commit 'Your message here'"
            exit 1
        fi
        echo "Staging all changes and committing..."
        git add .
        git commit -m "$MSG"
        ;;
    "pull")
        echo "Pulling latest changes from remote..."
        git pull origin main
        ;;
    "sync")
        echo "Executing full sync (Pull → Add → Commit → Push)..."
        if [ -z "$MSG" ]; then
            MSG="Auto-sync update"
        fi
        git pull origin main
        git add .
        git commit -m "$MSG"
        git push origin main
        echo "Sync complete."
        ;;
    *)
        echo "Usage: ./git_tools.sh {status|commit|pull|sync} ['commit message']"
        exit 1
        ;;
esac
