#!/bin/bash
# session-memory setup script
# Run this once to install the skill and configure auto-memory

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SKILL_NAME="session-memory"

echo "=== Session Memory Setup ==="
echo ""

# 1. Detect environment
if [ -d "$HOME/.skills/skills" ]; then
    SKILL_DIR="$HOME/.skills/skills/$SKILL_NAME"
    echo "Detected: Cowork environment"
elif [ -d "$HOME/.claude" ]; then
    SKILL_DIR="$HOME/.claude/skills/$SKILL_NAME"
    echo "Detected: Claude Code environment"
else
    SKILL_DIR="$HOME/.claude/skills/$SKILL_NAME"
    echo "No existing Claude directory found, creating one."
    mkdir -p "$HOME/.claude/skills"
fi

# 2. Install skill
echo ""
echo "Installing skill to: $SKILL_DIR"
mkdir -p "$SKILL_DIR/scripts"
cp "$SCRIPT_DIR/SKILL.md" "$SKILL_DIR/SKILL.md"
cp "$SCRIPT_DIR/scripts/"*.py "$SKILL_DIR/scripts/"
echo "✓ Skill installed"

# 3. Create CLAUDE.md for auto-loading memory
CLAUDE_MD="$HOME/CLAUDE.md"
MEMORY_BLOCK='# Session Memory (Auto-loaded)

At the START of every new conversation, automatically run:
```bash
python3 ~/.claude/skills/session-memory/scripts/sync_sessions.py --memory-dir <project-memory-dir> --limit 3
```
This loads context from previous sessions so you have continuity across conversations.

At the END of significant work, automatically run:
```bash
python3 ~/.claude/skills/session-memory/scripts/save_session.py --transcript <current-transcript> --memory-dir <project-memory-dir>
```
This saves the current session for future reference.'

if [ -f "$CLAUDE_MD" ]; then
    if grep -q "Session Memory" "$CLAUDE_MD" 2>/dev/null; then
        echo "✓ CLAUDE.md already contains session memory instructions"
    else
        echo "" >> "$CLAUDE_MD"
        echo "$MEMORY_BLOCK" >> "$CLAUDE_MD"
        echo "✓ Added session memory instructions to existing CLAUDE.md"
    fi
else
    echo "$MEMORY_BLOCK" > "$CLAUDE_MD"
    echo "✓ Created CLAUDE.md with session memory instructions"
fi

# 4. Setup auto-save cron (optional)
echo ""
read -p "Set up auto-save every 2 hours via cron? (y/N) " SETUP_CRON
if [ "$SETUP_CRON" = "y" ] || [ "$SETUP_CRON" = "Y" ]; then
    CRON_CMD="0 */2 * * * python3 $SKILL_DIR/scripts/auto_save.py >> /tmp/session-memory-auto-save.log 2>&1"
    (crontab -l 2>/dev/null | grep -v "auto_save.py"; echo "$CRON_CMD") | crontab -
    echo "✓ Cron job installed (runs every 2 hours)"
else
    echo "Skipped cron setup. You can run auto_save.py manually anytime."
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "How it works:"
echo "  • New conversations will auto-load previous session context"
echo "  • Session memories are saved to .claude/projects/<project>/memory/"
echo "  • Run 'python3 $SKILL_DIR/scripts/auto_save.py' to save all sessions now"
echo ""
echo "Commands you can use in chat:"
echo "  • '记住这次对话' / 'save memory'  — Save current session"
echo "  • '同步一下' / 'sync sessions'    — Load other sessions' context"
