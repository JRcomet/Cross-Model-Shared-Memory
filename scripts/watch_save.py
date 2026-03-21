#!/usr/bin/env python3
"""
watch_save.py — Real-time session memory watcher.

Monitors Claude transcript files for changes and automatically saves
updated memories. Runs as a background daemon.

Usage:
    python3 watch_save.py              # Run in foreground
    nohup python3 watch_save.py &      # Run as background daemon
"""

import json
import os
import sys
import time
import signal
from datetime import datetime
from pathlib import Path

# Add parent dir to import save_session
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from save_session import parse_transcript, generate_summary, detect_model

# Config
CHECK_INTERVAL = 30  # seconds between checks
MIN_SAVE_INTERVAL = 120  # minimum seconds between saves for same file
LOG_FILE = Path.home() / ".claude" / "session-memory-watcher.log"

# State
running = True
file_states = {}  # path -> {fingerprint, last_saved_at}


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
    """Find all possible Claude project directories."""
    candidates = []

    # Cowork environment
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

    # Local Claude Code environment
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

        # Remove old memory file
        if old_memory_file:
            old_path = memory_dir / old_memory_file
            if old_path.exists():
                old_path.unlink()

        # Save new memory
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
        index["memories"].append({
            "file": filename,
            "model": model,
            "timestamp": datetime.now().isoformat(),
            "source_transcript": transcript.name,
            "message_count": len(messages),
        })
        with open(index_path, "w") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)

        # Update state
        if not state_file.exists():
            state = {"saved_sessions": {}}
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


def watch_loop():
    """Main watch loop — check for changes every CHECK_INTERVAL seconds."""
    log(f"Session Memory Watcher started (interval: {CHECK_INTERVAL}s)")
    log(f"Log file: {LOG_FILE}")

    while running:
        try:
            project_dirs = find_claude_dirs()

            for project_dir in project_dirs:
                memory_dir = project_dir / "memory"
                transcripts = list(project_dir.glob("*.jsonl"))

                for transcript in transcripts:
                    fp = get_fingerprint(transcript)
                    key = str(transcript)

                    prev = file_states.get(key, {})
                    prev_fp = prev.get("fingerprint", "")
                    last_saved = prev.get("last_saved_at", 0)

                    # Skip if unchanged
                    if fp == prev_fp:
                        continue

                    # Throttle: don't save same file more than once per MIN_SAVE_INTERVAL
                    now = time.time()
                    if now - last_saved < MIN_SAVE_INTERVAL:
                        continue

                    # Changed! Save it
                    memory_dir.mkdir(exist_ok=True)
                    log(f"Change detected: {transcript.name}")
                    save_memory(transcript, memory_dir)

                    file_states[key] = {
                        "fingerprint": fp,
                        "last_saved_at": now,
                    }

        except Exception as e:
            log(f"Watch loop error: {e}")

        # Sleep in small chunks so we can respond to signals
        for _ in range(CHECK_INTERVAL):
            if not running:
                break
            time.sleep(1)

    log("Watcher stopped.")


if __name__ == "__main__":
    watch_loop()
