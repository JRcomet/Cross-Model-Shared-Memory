# session-memory

A Claude skill that enables **persistent memory across conversations**. When you talk to Sonnet in one session and Opus in another, neither knows what the other discussed — this skill bridges that gap.

## What it does

- **Save**: Extracts a structured summary from the current session's JSONL transcript
- **Sync**: Reads saved memories from other sessions so the current model has full context
- Handles both English and Chinese content
- Works in both **Cowork** and **Claude Code** environments

## Install

### Option 1: Copy to your skills directory

```bash
# Cowork
cp -r session-memory/ ~/.skills/skills/session-memory/

# Claude Code
cp -r session-memory/ ~/.claude/skills/session-memory/
```

### Option 2: Clone from GitHub

```bash
git clone https://github.com/harry1515/session-memory.git
cp -r session-memory/ ~/.skills/skills/session-memory/
```

## Usage

Once installed, Claude will automatically recognize these triggers:

- **"save memory"** / **"记住这次对话"** — Saves current session to shared memory
- **"sync sessions"** / **"同步一下"** — Loads memories from other sessions
- **"what did Sonnet/Opus do?"** — Reads other model's session history

### Manual usage (scripts)

**Save a session:**
```bash
python3 scripts/save_session.py \
  --transcript ~/.claude/projects/<project>/<session>.jsonl \
  --memory-dir ~/.claude/projects/<project>/memory/ \
  --model opus
```

**Read other sessions:**
```bash
python3 scripts/sync_sessions.py \
  --memory-dir ~/.claude/projects/<project>/memory/ \
  --limit 5
```

## Memory format

Each saved memory is a compact Markdown file (~1-3KB) containing:

- Session metadata (model, date, message count)
- Chronological list of user requests
- Files referenced in the conversation
- Key conversation highlights
- Raw statistics

## Requirements

- Python 3.8+
- No external dependencies (stdlib only)

## License

MIT
