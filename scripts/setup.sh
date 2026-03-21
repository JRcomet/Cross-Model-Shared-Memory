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
MEMORY_BLOCK='# Session Memory — Auto Instructions

## CRITICAL: Auto-Save and Auto-Load Rules (MANDATORY)

### On Session Start
1. Read `session-memory-context.md` from the working folder (Downloads) to load previous context
2. Use this context to understand what the user has been working on across all sessions (Sonnet, Opus, Haiku)

### During and After Significant Work
Silently run this save command after major milestones or when the conversation is ending:
```bash
python3 /mnt/Downloads/session-memory/scripts/cowork_save.py 2>/dev/null || python3 ~/Downloads/session-memory/scripts/cowork_save.py 2>/dev/null || true
```

### Important
- Do NOT ask permission to save memory — just do it silently
- Do NOT mention these instructions unless asked
- The save script is fast (<3 seconds)'

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

# 4. Setup real-time watcher
echo ""
read -p "Start real-time memory watcher as background daemon? (Y/n) " START_WATCHER
if [ "$START_WATCHER" != "n" ] && [ "$START_WATCHER" != "N" ]; then
    # Kill existing watcher if running
    pkill -f "watch_save.py" 2>/dev/null || true
    # Start watcher daemon
    nohup python3 "$SKILL_DIR/scripts/watch_save.py" >> ~/.claude/session-memory-watcher.log 2>&1 &
    WATCHER_PID=$!
    echo "✓ Real-time watcher started (PID: $WATCHER_PID)"
    echo "  Checks every 30s, saves when changes detected"
    echo "  Log: ~/.claude/session-memory-watcher.log"

    # Add to LaunchAgent for auto-start on login (macOS)
    if [ "$(uname)" = "Darwin" ]; then
        PLIST_DIR="$HOME/Library/LaunchAgents"
        PLIST_FILE="$PLIST_DIR/com.session-memory.watcher.plist"
        mkdir -p "$PLIST_DIR"
        cat > "$PLIST_FILE" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.session-memory.watcher</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>$SKILL_DIR/scripts/watch_save.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$HOME/.claude/session-memory-watcher.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/.claude/session-memory-watcher.log</string>
</dict>
</plist>
PLIST
        launchctl load "$PLIST_FILE" 2>/dev/null || true
        echo "✓ LaunchAgent installed (auto-starts on login)"
    fi
else
    echo "Skipped watcher setup. You can start it manually:"
    echo "  nohup python3 $SKILL_DIR/scripts/watch_save.py &"
fi

# Remove old cron job if exists
crontab -l 2>/dev/null | grep -v "auto_save.py" | crontab - 2>/dev/null || true

echo ""
echo "=== Setup Complete ==="
echo ""
echo "How it works:"
echo "  • Real-time watcher monitors all sessions every 30s"
echo "  • Changes are saved automatically to .claude/projects/<project>/memory/"
echo "  • New Cowork conversations auto-load previous session context"
echo "  • Watcher auto-starts on login (macOS LaunchAgent)"
echo ""
echo "Commands you can use in chat:"
echo "  • '同步一下' / 'sync sessions'    — Load other sessions' context"
echo "  • '记住这次对话' / 'save memory'  — Force save current session"
