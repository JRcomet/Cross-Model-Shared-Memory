---
name: cross-model-shared-memory
description: "Cross-Model Shared Memory — Real-time memory sharing between Claude Sonnet, Opus, and Haiku. Auto-saves conversation summaries and syncs across sessions so each model can see what the others discussed. Triggers: 'sync', 'memory', 'refresh memory', 'check other sessions', 'load memory', 'what did Sonnet/Opus do', 'what did we talk about', 'continue from last time', 'save conversation', '同步', '记忆', '刷新记忆', '看看其他对话', '更新记忆'. MANDATORY: use for any cross-session memory or model sync request."
---

# Cross-Model Shared Memory

Real-time memory sharing between Claude Sonnet, Opus, and Haiku. Solves the core problem: when you talk to Sonnet in one session and Opus in another, neither knows what the other discussed. This skill bridges that gap.

## How It Works

There are two operations: **save** (write a summary of the current session) and **sync** (read summaries from other sessions). Both use a shared `memory/` directory as the interchange format.

### Memory Storage Location

All memories are stored in the project's memory directory:
```
.claude/projects/<project-id>/memory/
├── session_<timestamp>_<model>.md    # Individual session summaries
├── memory_index.json                  # Index of all saved memories
└── shared_context.md                  # Rolling shared context file
```

## Commands

### 1. Save Current Session (`save memory` / `记住这次对话`)

When the user asks to save the current conversation, run the save script:

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

### 2. Sync Other Sessions (`sync sessions` / `同步一下`)

When the user wants to know what happened in other sessions, run:

```bash
python3 <skill-path>/scripts/sync_sessions.py \
  --memory-dir <project-memory-dir> \
  --current-session <current-session-id> \
  --limit 5
```

This reads all saved memory files (excluding the current session) and presents them chronologically. The output includes which model was used, when the session happened, and the key points.

### 3. Auto-Save on Important Moments

When you detect that significant work has been completed (files created, decisions made, multi-step tasks finished), proactively suggest saving a memory snapshot. Don't wait for the user to ask.

## Summary Format

Each saved memory follows this structure:

```markdown
# Session Memory — [Date] [Model]

## Session Info
- **Model**: claude-sonnet-4-6 / claude-opus-4-6
- **Date**: 2026-03-21 15:30
- **Session ID**: abc123...

## Key Topics
- [Topic 1]: Brief description
- [Topic 2]: Brief description

## Decisions & Outcomes
- [Decision]: What was decided and why

## Files Created/Modified
- `filename.py` — What it does
- `report.docx` — What it contains

## Pending Tasks
- [ ] Task that still needs to be done
- [ ] Another pending item

## Important Context
Any critical context that future sessions should know about.
Key variables, credentials references (not actual values), API endpoints, preferences expressed by the user.

## Conversation Highlights
Up to 5 key exchanges that capture the most important moments.
```

## Implementation Notes

- The save script intelligently extracts content — it skips `thinking` blocks, tool call details, and base64 image data to keep memories compact
- Each memory file is typically 1-3KB, small enough to load several into context without issues
- The memory index (`memory_index.json`) enables quick lookups without reading every file
- Memories are project-scoped, so different project folders maintain separate memory banks
- The scripts handle both English and Chinese content naturally

## Finding the Right Paths

The transcript file and memory directory locations depend on the environment:

**Cowork environment:**
```
Transcripts: /sessions/<session-name>/mnt/.claude/projects/<project-id>/<session-uuid>.jsonl
Memory dir:  /sessions/<session-name>/mnt/.claude/projects/<project-id>/memory/
```

**Claude Code (local):**
```
Transcripts: ~/.claude/projects/<project-path>/<session-uuid>.jsonl
Memory dir:  ~/.claude/projects/<project-path>/memory/
```

To find the current transcript, look for the most recently modified `.jsonl` file in the project directory. The script handles both environments automatically.

## Edge Cases

- If the memory directory doesn't exist, create it
- If a transcript is too large (>10MB), the save script samples the most recent portion
- If there are no other session memories to sync, tell the user clearly
- Handle both English and Chinese user messages gracefully
