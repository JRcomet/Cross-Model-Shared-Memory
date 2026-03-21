# Cross-Model Shared Memory

A Claude skill that enables **real-time memory sharing between Sonnet, Opus, and Haiku**. When you talk to Sonnet in one session and Opus in another, neither knows what the other discussed — this skill bridges that gap.

## Features

- **Auto-save**: Saves session summaries every 3 exchanges (configurable)
- **Auto-load**: New conversations automatically load context from previous sessions
- **Auto-refresh**: Re-reads memory every 5 exchanges to catch updates from other sessions
- **Cross-model sync**: Sonnet can see what Opus discussed, and vice versa
- **Near-real-time**: Host watcher polls every 10 seconds, saves every 30 seconds
- **Multilingual triggers**: Sync commands work in English, 中文, 日本語, 한국어, Español, Français, Deutsch
- **Deduplication**: Only saves when a session has actually changed
- **Zero dependencies**: Pure Python stdlib, no pip install needed

## Quick Install

```bash
git clone https://github.com/JRcomet/session-memory.git
cd session-memory
bash scripts/setup.sh
```

The setup script will:
1. Install the skill to your Claude skills directory
2. Create a `CLAUDE.md` in `~/Downloads/` with auto-load/save/sync instructions
3. Start a background watcher daemon for real-time sync

## How It Works

```
Session A (Sonnet)              Session B (Opus)
    │                               │
    ▼                               ▼
[cowork_save.py]               [cowork_save.py]
(auto every 3 exchanges)      (auto every 3 exchanges)
    │                               │
    ▼                               ▼
┌────────────────────────────────────────┐
│  ~/Downloads/                          │
│  ├── CLAUDE.md (auto-loaded)           │
│  ├── session-memory-context.md         │
│  └── .cowork_memories/                 │
│      ├── sonnet_<id>.md                │
│      └── opus_<id>.md                  │
└────────────────────────────────────────┘
    │                               │
    ▼                               ▼
[auto-refresh every 5 exchanges] [auto-refresh every 5 exchanges]
```

1. **Save**: Parses the JSONL transcript → extracts topics, files, key exchanges → writes a compact markdown summary
2. **Sync**: Reads `session-memory-context.md` → presents cross-session context
3. **Watcher**: Host daemon polls every 10s, detects changed transcripts by fingerprint (size + mtime), re-saves and updates shared files

## Sync Trigger Commands

Works in multiple languages:

| Language | Commands |
|----------|----------|
| English  | sync, refresh memory, check other sessions, load memory |
| 中文     | 同步, 刷新记忆, 看看其他对话, 更新记忆 |
| 日本語   | メモリ同期, 他のセッションを確認 |
| 한국어   | 동기화, 메모리 새로고침 |
| Español  | sincronizar, actualizar memoria |
| Français | synchroniser, rafraîchir mémoire |
| Deutsch  | synchronisieren, Speicher aktualisieren |

## Usage

### Automatic (after setup)

Just use Claude normally. Memory works in the background:
- Sessions are saved automatically every 3 exchanges
- New conversations load previous context on startup
- Memory refreshes every 5 exchanges to catch cross-session updates

### Manual triggers in chat

- **"sync"** / **"同步"** / **"メモリ同期"** — Force sync with other sessions
- **"save memory"** / **"保存对话"** — Force save current session
- **"what did Sonnet/Opus do?"** / **"Opus做了什么"** — Check what another model discussed

## File Structure

```
session-memory/
├── SKILL.md                  # Claude skill definition
├── README.md
└── scripts/
    ├── setup.sh              # One-time setup
    ├── save_session.py       # Core transcript parser & summary generator
    ├── cowork_save.py        # Runs inside Cowork VM, saves to Downloads
    ├── watch_save.py         # Host background daemon (10s poll, 30s save)
    └── sync_sessions.py      # Read and display saved memories
```

## Requirements

- Python 3.8+
- No external dependencies (stdlib only)
- Works in Cowork, Claude Code, and Chat with Projects

## License

MIT
