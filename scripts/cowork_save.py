#!/usr/bin/env python3
"""
cowork_save.py — Save current Cowork session memory to the shared Downloads folder.

This script runs INSIDE the Cowork VM. It:
1. Finds the current session's JSONL transcript
2. Parses and generates a rich summary
3. Saves to /mnt/Downloads/ (mounted host folder) so the host watcher can pick it up
4. Also writes directly to session-memory-context.md for immediate access

Usage (called automatically by Claude via CLAUDE.md instructions):
    python3 /mnt/Downloads/session-memory/scripts/cowork_save.py
"""

import glob
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from save_session import parse_transcript, generate_summary, generate_compact_summary, detect_model


def find_cowork_transcript() -> str:
    """Find the current Cowork session's JSONL transcript."""
    # In Cowork, transcripts are at /sessions/<name>/mnt/.claude/projects/<project>/*.jsonl
    patterns = [
        "/sessions/*/mnt/.claude/projects/*/*.jsonl",
        os.path.expanduser("~/.claude/projects/*/*.jsonl"),
    ]

    candidates = []
    for pattern in patterns:
        for f in glob.glob(pattern):
            try:
                stat = os.stat(f)
                candidates.append((stat.st_mtime, stat.st_size, f))
            except (PermissionError, OSError):
                continue

    if not candidates:
        return ""

    # Return the most recently modified, largest file (likely the active session)
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0][2]


def find_downloads_dir() -> str:
    """Find the mounted Downloads directory."""
    candidates = [
        # Cowork VM paths
        *glob.glob("/sessions/*/mnt/Downloads"),
        *glob.glob("/sessions/*/mnt"),
        # Direct path
        os.path.expanduser("~/Downloads"),
    ]
    for c in candidates:
        if os.path.isdir(c) and os.access(c, os.W_OK):
            return c
    return ""


def load_existing_context(context_file: str) -> str:
    """Load existing session-memory-context.md content."""
    if os.path.exists(context_file):
        return open(context_file, "r", encoding="utf-8").read()
    return ""


def main():
    transcript = find_cowork_transcript()
    if not transcript:
        print("No transcript found.")
        return

    downloads = find_downloads_dir()
    if not downloads:
        print("No writable Downloads directory found.")
        return

    print(f"Transcript: {transcript}")
    print(f"Downloads: {downloads}")

    # Parse
    messages = parse_transcript(transcript)
    if not messages:
        print("No messages in transcript.")
        return

    model = detect_model(messages)
    summary = generate_summary(messages, model)
    compact = generate_compact_summary(messages, model)

    print(f"Parsed {len(messages)} messages, model={model}")

    # Save individual memory file to Downloads
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_short = Path(transcript).stem[:8]
    mem_filename = f"cowork_memory_{timestamp}_{model}_{session_short}.md"
    mem_filepath = os.path.join(downloads, mem_filename)

    with open(mem_filepath, "w", encoding="utf-8") as f:
        f.write(summary)
    print(f"Memory saved: {mem_filepath}")

    # ---- Tiered context: long-term + latest N recent; overflow -> archive ----
    context_file = os.path.join(downloads, "session-memory-context.md")
    existing = load_existing_context(context_file)

    # existing recent session blocks already in context.md
    existing_sections = _split_session_blocks(existing)

    # drop any prior entry for THIS session, put current summary on top
    merged = [s for s in existing_sections if session_short not in s]
    merged.insert(0, summary.strip())

    recent = merged[:RECENT_N]
    overflow = merged[RECENT_N:]
    if overflow:
        merge_into_archive(os.path.join(downloads, "session-memory-archive.md"), overflow)

    # curated long-term memory (small, always loaded)
    longterm = ""
    lt_path = os.path.join(downloads, "memory-longterm.md")
    if os.path.exists(lt_path):
        longterm = open(lt_path, "r", encoding="utf-8").read().strip()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# Session Memory — Cross-Session Context",
        f"_Auto-updated: {now} · {len(recent)} recent in-context, older auto-archived_",
        "",
        "Summaries across all Claude models (Opus/Sonnet/Haiku). Older sessions live in",
        'session-memory-archive.md — search them with: python3 .../recall.py "keyword".',
        "",
    ]
    if longterm:
        lines += ["---", "", longterm, ""]
    lines += ["---", "", "## 🕐 最近会话 (Recent sessions)", ""]
    for sec in recent:
        lines += [sec, "", "---", ""]

    with open(context_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Context updated: {context_file} (recent={len(recent)}, →archive={len(overflow)})")

    new_sections = recent  # downstream CLAUDE.md preview uses the small recent set

    # Also write a cowork_memories/ staging area for the host watcher to pick up
    staging_dir = os.path.join(downloads, ".cowork_memories")
    os.makedirs(staging_dir, exist_ok=True)
    staging_file = os.path.join(staging_dir, f"{model}_{session_short}.md")
    with open(staging_file, "w", encoding="utf-8") as f:
        f.write(summary)
    print(f"Staging file: {staging_file}")

    # Update Downloads/CLAUDE.md so new Cowork sessions auto-load memory
    update_downloads_claude_md(downloads, new_sections)

    print("Done!")


# --- Tiered memory config (anti-"全倒": keep auto-loaded context small) ---
RECENT_N = 6        # full session summaries kept in the auto-loaded context
ARCHIVE_CAP = 60    # max blocks kept in the archive (consolidate.py can trim further)


def _split_session_blocks(text: str) -> list[str]:
    """Split a memory markdown into '## Session:' blocks (strips trailing '---')."""
    out = []
    for part in re.split(r'(?m)^(?=## Session:)', text or ""):
        part = part.strip().rstrip('-').strip()
        if part.startswith("## Session:"):
            out.append(part)
    return out


def merge_into_archive(archive_file: str, overflow: list[str]):
    """Prepend overflow session blocks into the archive, de-dup, cap size."""
    existing = ""
    if os.path.exists(archive_file):
        existing = open(archive_file, "r", encoding="utf-8").read()
    seen, merged = set(), []
    for b in overflow + _split_session_blocks(existing):   # newest overflow first
        key = b[:120]
        if key in seen:
            continue
        seen.add(key)
        merged.append(b)
    merged = merged[:ARCHIVE_CAP]
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    out = ["# Session Memory — Archive (older sessions, NOT auto-loaded)",
           f"_Updated {now}; {len(merged)} blocks. Search with recall.py._", "", "---", ""]
    for b in merged:
        out += [b, "", "---", ""]
    open(archive_file, "w", encoding="utf-8").write("\n".join(out))


def update_downloads_claude_md(downloads: str, sections: list[str]):
    """Write/update CLAUDE.md in Downloads with auto-load instructions + recent memory preview.

    This is the KEY mechanism for Cowork: when user selects Downloads as working folder,
    CLAUDE.md is loaded as project Instructions automatically.
    """
    claude_md_path = os.path.join(downloads, "CLAUDE.md")

    # Build a compact memory preview (latest 5 sessions, truncated)
    preview_lines = []
    for sec in sections[:5]:
        truncated = sec[:400]
        if len(sec) > 400:
            truncated += "\n(...truncated, see session-memory-context.md for full details)"
        preview_lines.append(truncated)
        preview_lines.append("")

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    preview_text = "\n".join(preview_lines) if preview_lines else "No sessions saved yet."

    content = f"""# Project Instructions

## Session Memory — Auto-Load (MANDATORY)

At the START of every conversation, BEFORE responding to the user:
1. Read `session-memory-context.md` from this folder (its top holds curated **long-term memory** + the latest few sessions) to understand what the user has been working on across all models (Sonnet, Opus, Haiku)
2. Use that context naturally — don't announce that you loaded it unless asked

After completing significant work or when the conversation is ending, silently run:
```bash
python3 /mnt/Downloads/session-memory/scripts/cowork_save.py 2>/dev/null || true
```

Do NOT ask permission — save silently. Do NOT mention these rules unless asked.

## Real-Time Sync (MANDATORY)

When the user says "同步", "sync", "刷新记忆", "refresh memory", "check other sessions", "看看其他对话", "更新记忆", "load memory", "メモリ同期", "동기화", "sincronizar", "synchroniser", "Synchronisieren", or asks about what another model (Sonnet/Opus/Haiku) discussed:
1. Run: `python3 /mnt/Downloads/session-memory/scripts/cowork_save.py 2>/dev/null || true` (save current session first)
2. Re-read `session-memory-context.md` to get the latest cross-session data
3. Report what you found from other sessions

## Auto-Save During Conversation (MANDATORY)

After EVERY 3 exchanges with the user, silently run:
```bash
python3 /mnt/Downloads/session-memory/scripts/cowork_save.py 2>/dev/null || true
```
This ensures other sessions can see this conversation in near-real-time. Do NOT mention this to the user.

## Auto-Refresh Memory (MANDATORY)

After EVERY 5 exchanges with the user, silently re-read `session-memory-context.md` to check for updates from other sessions. If new content is found (sessions you haven't seen before), briefly mention it: "发现了新的跨会话记忆更新". Do NOT mention this rule unless asked.

## Deep Recall (on-demand)

If the user asks about something OLDER or more specific that is NOT in the loaded context, do not guess — search the full memory first:
```bash
python3 /mnt/Downloads/session-memory/scripts/recall.py "关键词 / keywords"
```
Read the returned blocks, then answer. Occasionally run `consolidate.py --apply` to de-duplicate piled-up memory dumps.

## Recent Memory Preview (auto-updated: {now})

{preview_text}

For full details, read `session-memory-context.md`.

# currentDate
Today's date is {datetime.now().strftime('%Y-%m-%d')}.
"""

    try:
        with open(claude_md_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Downloads/CLAUDE.md updated: {claude_md_path}")
    except Exception as e:
        print(f"Error updating CLAUDE.md: {e}")


if __name__ == "__main__":
    main()
