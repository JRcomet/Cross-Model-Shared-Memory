#!/usr/bin/env python3
"""
watch_save.py — Real-time session memory watcher.

Monitors Claude transcript files for changes and automatically saves
updated memories. Also writes:
1. session-memory-context.md in ~/Downloads (for Cowork access)
2. Memory section in ~/CLAUDE.md (auto-loaded by every new session)

Usage:
    python3 watch_save.py              # Run in foreground
    nohup python3 watch_save.py &      # Run as background daemon
"""

import json
import os
import re
import sys
import time
import signal
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from save_session import parse_transcript, generate_summary, generate_compact_summary, detect_model

# Config
CHECK_INTERVAL = 30
MIN_SAVE_INTERVAL = 120
LOG_FILE = Path.home() / ".claude" / "session-memory-watcher.log"
CLAUDE_MD = Path.home() / "CLAUDE.md"
SHARED_FILE = Path.home() / "Downloads" / "session-memory-context.md"
MEMORY_MARKER_START = "<!-- SESSION-MEMORY-START -->"
MEMORY_MARKER_END = "<!-- SESSION-MEMORY-END -->"

running = True
file_states = {}


def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def signal_handler(sig, frame):
    global running
    log("Received stop signal, shutting down...")
    running = False


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def find_claude_dirs() -> list[Path]:
    candidates = []
    cowork_base = Path("/sessions")
    if cowork_base.exists():
        for session_dir in cowork_base.iterdir():
            try:
                claude_dir = session_dir / "mnt" / ".claude" / "projects"
                if claude_dir.exists():
                    for project_dir in claude_dir.iterdir():
                        if project_dir.is_dir():
                            candidates.append(project_dir)
            except PermissionError:
                continue

    home_claude = Path.home() / ".claude" / "projects"
    if home_claude.exists():
        for project_dir in home_claude.iterdir():
            if project_dir.is_dir():
                candidates.append(project_dir)
    return candidates


def get_fingerprint(filepath: Path) -> str:
    try:
        stat = filepath.stat()
        return f"{stat.st_size}:{stat.st_mtime}"
    except Exception:
        return ""


def save_memory(transcript: Path, memory_dir: Path):
    """Save a memory file for a transcript."""
    try:
        messages = parse_transcript(str(transcript))
        if not messages:
            return

        model = detect_model(messages)
        summary = generate_summary(messages, model)

        # Load state to find old file to replace
        state_file = memory_dir / ".auto_save_state.json"
        old_memory_file = None
        if state_file.exists():
            with open(state_file, "r") as f:
                state = json.load(f)
            prev = state.get("saved_sessions", {}).get(str(transcript), {})
            old_memory_file = prev.get("memory_file")
        else:
            state = {"saved_sessions": {}}

        if old_memory_file:
            old_path = memory_dir / old_memory_file
            if old_path.exists():
                old_path.unlink()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_short = transcript.stem[:8]
        filename = f"session_{timestamp}_{model}_{session_short}.md"
        filepath = memory_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(summary)

        # Update index
        index_path = memory_dir / "memory_index.json"
        if index_path.exists():
            with open(index_path, "r") as f:
                index = json.load(f)
        else:
            index = {"memories": []}

        index["memories"] = [
            m for m in index["memories"]
            if m.get("source_transcript") != transcript.name
        ]

        compact = generate_compact_summary(messages, model)
        index["memories"].append({
            "file": filename,
            "model": model,
            "timestamp": datetime.now().isoformat(),
            "source_transcript": transcript.name,
            "message_count": len(messages),
            "preview": compact,
        })
        with open(index_path, "w") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)

        state["saved_sessions"][str(transcript)] = {
            "fingerprint": get_fingerprint(transcript),
            "memory_file": filename,
            "saved_at": datetime.now().isoformat(),
        }
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

        log(f"  Saved: {filename} ({len(messages)} msgs)")

    except Exception as e:
        log(f"  Error: {e}")


def collect_all_memories(memory_dirs: list[Path]) -> list[tuple]:
    """Collect all memory files across all project dirs, sorted by time."""
    all_memories = []
    for memory_dir in memory_dirs:
        if not memory_dir.exists():
            continue
        for md_file in memory_dir.glob("session_*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
                stat = md_file.stat()
                all_memories.append((stat.st_mtime, md_file.name, content))
            except Exception:
                continue
    all_memories.sort(key=lambda x: x[0], reverse=True)
    return all_memories


def write_shared_summary(memory_dirs: list[Path]):
    """Write detailed memory to ~/Downloads/session-memory-context.md"""
    all_memories = collect_all_memories(memory_dirs)
    if not all_memories:
        return

    latest = all_memories[:15]

    lines = [
        "# Session Memory — Cross-Session Context",
        f"_Auto-updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_",
        f"_Total sessions: {len(all_memories)}, showing latest {len(latest)}_",
        "",
        "Use this file to understand what the user has been working on across different conversations and models (Sonnet, Opus, Haiku).",
        "",
        "---",
        "",
    ]

    for _, name, content in latest:
        lines.append(content)
        lines.append("")
        lines.append("---")
        lines.append("")

    try:
        with open(SHARED_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        log(f"Shared summary updated: {SHARED_FILE} ({len(latest)} sessions)")
    except Exception as e:
        log(f"Error writing shared summary: {e}")


def update_claude_md(memory_dirs: list[Path]):
    """Inject recent memory summaries directly into ~/CLAUDE.md so every new
    session (Cowork, Claude Code, Chat with Projects) auto-loads them."""
    all_memories = collect_all_memories(memory_dirs)
    if not all_memories:
        return

    # Build compact memory block (keep it under ~2000 chars to not bloat CLAUDE.md)
    latest = all_memories[:8]
    mem_lines = [
        MEMORY_MARKER_START,
        "# Cross-Session Memory (Auto-updated)",
        f"_Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
        "Below are summaries of recent conversations. Use this context to maintain continuity.",
        "The user (harry) has been working on multiple projects. Key context:",
        "",
    ]

    for _, name, content in latest:
        # Truncate each memory to keep total size reasonable
        truncated = content[:600]
        if len(content) > 600:
            truncated += "\n  (...truncated)"
        mem_lines.append(truncated)
        mem_lines.append("")

    mem_lines.append("For full details, read `session-memory-context.md` in the Downloads folder.")
    mem_lines.append(MEMORY_MARKER_END)

    memory_block = "\n".join(mem_lines)

    # Read existing CLAUDE.md
    existing = ""
    if CLAUDE_MD.exists():
        existing = CLAUDE_MD.read_text(encoding="utf-8")

    # Replace existing memory block or append
    if MEMORY_MARKER_START in existing and MEMORY_MARKER_END in existing:
        pattern = re.escape(MEMORY_MARKER_START) + r".*?" + re.escape(MEMORY_MARKER_END)
        new_content = re.sub(pattern, memory_block, existing, flags=re.DOTALL)
    elif MEMORY_MARKER_START in existing:
        # Broken marker — replace from start marker to end
        idx = existing.index(MEMORY_MARKER_START)
        new_content = existing[:idx] + memory_block
    else:
        # Append
        new_content = existing.rstrip() + "\n\n" + memory_block + "\n"

    try:
        with open(CLAUDE_MD, "w", encoding="utf-8") as f:
            f.write(new_content)
        log(f"CLAUDE.md updated with {len(latest)} session memories")
    except Exception as e:
        log(f"Error updating CLAUDE.md: {e}")


def watch_loop():
    """Main watch loop."""
    log(f"Session Memory Watcher started (interval: {CHECK_INTERVAL}s)")
    log(f"Log: {LOG_FILE}")

    while running:
        any_saved = False
        try:
            project_dirs = find_claude_dirs()
            memory_dirs = []

            for project_dir in project_dirs:
                memory_dir = project_dir / "memory"
                memory_dirs.append(memory_dir)
                transcripts = list(project_dir.glob("*.jsonl"))

                for transcript in transcripts:
                    fp = get_fingerprint(transcript)
                    key = str(transcript)

                    prev = file_states.get(key, {})
                    prev_fp = prev.get("fingerprint", "")
                    last_saved = prev.get("last_saved_at", 0)

                    if fp == prev_fp:
                        continue

                    now = time.time()
                    if now - last_saved < MIN_SAVE_INTERVAL:
                        continue

                    memory_dir.mkdir(exist_ok=True)
                    log(f"Change detected: {transcript.name}")
                    save_memory(transcript, memory_dir)

                    file_states[key] = {
                        "fingerprint": fp,
                        "last_saved_at": now,
                    }
                    any_saved = True

            if any_saved:
                write_shared_summary(memory_dirs)
                update_claude_md(memory_dirs)

        except Exception as e:
            log(f"Watch loop error: {e}")

        for _ in range(CHECK_INTERVAL):
            if not running:
                break
            time.sleep(1)

    log("Watcher stopped.")


if __name__ == "__main__":
    watch_loop()
