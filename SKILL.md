---
name: cross-model-shared-memory
description: "Cross-Model Shared Memory — Real-time memory sharing between Claude Sonnet, Opus, and Haiku. Auto-saves conversation summaries and syncs across sessions so each model can see what the others discussed. Triggers: 'sync', 'memory', 'refresh memory', 'check other sessions', 'load memory', 'what did Sonnet/Opus do', 'what did we talk about', 'continue from last time', 'save conversation', '同步', '记忆', '刷新记忆', '看看其他对话', '更新记忆', 'sincronizar', 'mémoire', 'メモリ同期', '동기화', 'Synchronisieren'. MANDATORY: use for any cross-session memory or model sync request."
---

# Cross-Model Shared Memory

Real-time memory sharing between Claude Sonnet, Opus, and Haiku. Solves the core problem: when you talk to Sonnet in one session and Opus in another, neither knows what the other discussed. This skill bridges that gap.

## How It Works

There are two operations: **save** (write a summary of the current session) and **sync** (read summaries from other sessions). Both use shared files in the Downloads folder as the interchange format.

### Architecture

```
~/Downloads/
├── CLAUDE.md                          # Auto-loaded as project Instructions by Cowork
├── session-memory-context.md          # Full cross-session memory (auto-updated)
├── session-memory/                    # Skill source code (GitHub repo)
│   ├── SKILL.md
│   ├── README.md
│   └── scripts/
│       ├── save_session.py            # Core transcript parser & summary generator
│       ├── cowork_save.py             # Runs inside Cowork VM, saves to Downloads
│       ├── watch_save.py              # Host daemon, polls every 10s, saves every 30s
│       └── sync_sessions.py           # Reads and displays saved memories
├── .cowork_memories/                  # Staging area for cross-VM sync
└── cowork_memory_*.md                 # Individual session memory files
```

### Host Watcher (Background Daemon)
- Polls `~/.claude/projects/*/` every 10 seconds for transcript changes
- Re-saves memory when changes detected (min 30s interval)
- Updates `~/Downloads/session-memory-context.md` and `~/Downloads/CLAUDE.md`

### Cowork VM Save (In-Session)
- Runs inside Cowork VM via `cowork_save.py`
- Saves to `/mnt/Downloads/` (mounted host folder)
- Triggered automatically every 3 exchanges by CLAUDE.md instructions

## Trigger Commands

Sync can be triggered in multiple languages:

| Language | Commands |
|----------|----------|
| English  | sync, refresh memory, check other sessions, load memory, what did Sonnet/Opus do |
| 中文     | 同步, 刷新记忆, 看看其他对话, 更新记忆, Sonnet/Opus做了什么 |
| 日本語   | メモリ同期, 他のセッションを確認, 同期して |
| 한국어   | 동기화, 메모리 새로고침, 다른 세션 확인 |
| Español  | sincronizar, actualizar memoria, verificar otras sesiones |
| Français | synchroniser, rafraîchir mémoire, vérifier autres sessions |
| Deutsch  | synchronisieren, Speicher aktualisieren, andere Sitzungen prüfen |

## Commands

### 1. Save Current Session

Trigger phrases: `save memory`, `记住这次对话`, `save conversation`, `保存对话`

```bash
python3 <skill-path>/scripts/save_session.py \
  --transcript <path-to-current-session.jsonl> \
  --memory-dir <project-memory-dir> \
  --model <current-model-name>
```

The script will:
1. Parse the JSONL transcript
2. Extract user messages and assistant responses (skipping tool calls and thinking blocks)
3. Generate a structured summary with: key topics, decisions made, files created, pending tasks, and important context
4. Save it as a timestamped markdown file
5. Update the memory index

### 2. Sync Other Sessions

Trigger phrases: `sync`, `同步`, `synchroniser`, `sincronizar`, `メモリ同期`, `동기화`

```bash
python3 <skill-path>/scripts/sync_sessions.py \
  --memory-dir <project-memory-dir> \
  --current-session <current-session-id> \
  --limit 5
```

This reads all saved memory files (excluding the current session) and presents them chronologically. The output includes which model was used, when the session happened, and the key points.

### 3. Auto-Save (No User Action Needed)

CLAUDE.md instructs Claude to automatically:
- **Save** every 3 exchanges (silently run cowork_save.py)
- **Refresh** every 5 exchanges (re-read session-memory-context.md)
- **Load** at session start (read session-memory-context.md before first response)

## Summary Format

Each saved memory follows this structure:

```markdown
## Session: [Date] ([Model]) — [N] exchanges

**Topics**: Topic1, Topic2, ...

**Key outcomes**:
- Files created/modified
- Decisions made
- Important results

**Conversation flow**:
  1. **User**: [summary of message]
     **Claude**: [summary of response]
  ...
```

## Implementation Notes

- The save script intelligently extracts content — it skips `thinking` blocks, tool call details, and base64 image data to keep memories compact
- Each memory file is typically 1-3KB, small enough to load several into context without issues
- The memory index (`memory_index.json`) enables quick lookups without reading every file
- Memories are project-scoped, so different project folders maintain separate memory banks
- `detect_model()` uses the LATEST model field in transcript to correctly identify the model even after context compaction (e.g., session starts as Sonnet, continues as Opus)
- The scripts handle multilingual content naturally (English, Chinese, Japanese, Korean, etc.)

## Finding the Right Paths

The transcript file and memory directory locations depend on the environment:

**Cowork environment:**
```
Transcripts: /sessions/<session-name>/mnt/.claude/projects/<project-id>/<session-uuid>.jsonl
Memory dir:  /sessions/<session-name>/mnt/.claude/projects/<project-id>/memory/
Downloads:   /sessions/<session-name>/mnt/Downloads/
```

**Claude Code (local):**
```
Transcripts: ~/.claude/projects/<project-path>/<session-uuid>.jsonl
Memory dir:  ~/.claude/projects/<project-path>/memory/
Downloads:   ~/Downloads/
```

To find the current transcript, look for the most recently modified `.jsonl` file in the project directory. The script handles both environments automatically.

## Edge Cases

- If the memory directory doesn't exist, create it
- If a transcript is too large (>10MB), the save script samples the most recent portion
- If there are no other session memories to sync, tell the user clearly
- Handle multilingual user messages gracefully
- If CLAUDE.md gets overwritten, the watcher will regenerate it within 10 seconds
