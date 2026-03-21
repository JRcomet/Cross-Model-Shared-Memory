# Cross-Model Shared Memory

A Claude skill that enables **real-time memory sharing between Sonnet, Opus, and Haiku**. When you talk to Sonnet in one session and Opus in another, neither knows what the other discussed — this skill bridges that gap.

## Features

- **Auto-save**: Automatically saves session summaries when significant work is done
- **Auto-load**: New conversations automatically load context from previous sessions
- **Cross-model sync**: Sonnet can see what Opus discussed, and vice versa
- **Deduplication**: Only saves when a session has actually changed
- **Bilingual**: Handles English and Chinese content natively
- **Zero dependencies**: Pure Python stdlib, no pip install needed

## Quick Install

```bash
git clone https://github.com/JRcomet/session-memory.git
cd session-memory
bash scripts/setup.sh
```

The setup script will:
1. Install the skill to your Claude skills directory
2. Create a `CLAUDE.md` with auto-load instructions so every new conversation starts with memory
3. Optionally set up a cron job to auto-save sessions every 2 hours

## How It Works

```
Session A (Sonnet)          Session B (Opus)
    │                           │
    ▼                           ▼
[auto_save.py]              [auto_save.py]
    │                           │
    ▼                           ▼
┌──────────────────────────────────┐
│   memory/                        │
│   ├── session_..._sonnet.md      │
│   ├── session_..._opus.md        │
│   └── memory_index.json          │
└──────────────────────────────────┘
    │                           │
    ▼                           ▼
[sync on new session start]  [sync on new session start]
```

1. **Save**: Parses the JSONL transcript → extracts user requests, files, key exchanges → writes a compact markdown summary
2. **Sync**: Reads all saved memories → presents them to the current session as context
3. **Auto-save**: Runs periodically, detects changed transcripts by fingerprint (size + mtime), only re-saves what's new

## Usage

### Automatic (after setup)

Just use Claude normally. Memory works in the background:
- Sessions are saved automatically (via cron or at session end)
- New conversations load previous context on startup

### Manual triggers in chat

- **"save memory"** / **"记住这次对话"** — Force save current session
- **"sync sessions"** / **"同步一下"** — Reload memories from other sessions
- **"what did Sonnet/Opus do?"** — Check what another model discussed

### CLI usage

```bash
# Save a specific session
python3 scripts/save_session.py \
  --transcript ~/.claude/projects/<project>/<session>.jsonl \
  --memory-dir ~/.claude/projects/<project>/memory/ \
  --model opus

# Read all saved memories
python3 scripts/sync_sessions.py \
  --memory-dir ~/.claude/projects/<project>/memory/ \
  --limit 5

# Auto-save all changed sessions
python3 scripts/auto_save.py
```

## File Structure

```
session-memory/
├── SKILL.md                  # Claude skill definition
├── README.md
└── scripts/
    ├── setup.sh              # One-time setup
    ├── save_session.py       # Save one session transcript to memory
    ├── sync_sessions.py      # Read and display saved memories
    └── auto_save.py          # Batch auto-save with deduplication
```

## Memory Format

Each saved memory is a compact Markdown file (~1-3KB):

- Session metadata (model, date, message count)
- Chronological list of user requests
- Files referenced in the conversation
- Key conversation highlights

## Requirements

- Python 3.8+
- No external dependencies (stdlib only)
- Works in both Cowork and Claude Code environments

## License

MIT
