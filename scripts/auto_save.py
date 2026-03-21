#!/usr/bin/env python3
"""
auto_save.py — Automatically scan for new/updated session transcripts and save memories.

Designed to be run as a scheduled task. It:
1. Scans all project directories for JSONL transcripts
2. Compares against the memory index to find new/updated sessions
3. Saves memories only for sessions that have changed since last save
"""

import json
import os
import sys
import hashlib
from datetime import datetime
from pathlib import Path

# Add parent dir to import save_session
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from save_session import parse_transcript, generate_summary, detect_model


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


def find_transcripts(project_dir: Path) -> list[Path]:
    """Find all JSONL transcript files in a project directory."""
    return sorted(project_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)


def get_file_fingerprint(filepath: Path) -> str:
    """Get a fingerprint (size + mtime) to detect changes without reading the whole file."""
    stat = filepath.stat()
    return f"{stat.st_size}:{stat.st_mtime}"


def load_save_state(memory_dir: Path) -> dict:
    """Load the auto-save state file that tracks what's been saved."""
    state_file = memory_dir / ".auto_save_state.json"
    if state_file.exists():
        with open(state_file, "r") as f:
            return json.load(f)
    return {"saved_sessions": {}}


def update_save_state(memory_dir: Path, session_path: str, fingerprint: str, memory_file: str):
    """Update the auto-save state."""
    state = load_save_state(memory_dir)
    state["saved_sessions"][session_path] = {
        "fingerprint": fingerprint,
        "memory_file": memory_file,
        "saved_at": datetime.now().isoformat(),
    }
    state_file = memory_dir / ".auto_save_state.json"
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def auto_save_all():
    """Main auto-save logic: scan, diff, save new memories."""
    project_dirs = find_claude_dirs()

    if not project_dirs:
        print("No Claude project directories found.")
        return

    total_saved = 0
    total_skipped = 0

    for project_dir in project_dirs:
        memory_dir = project_dir / "memory"
        memory_dir.mkdir(exist_ok=True)

        state = load_save_state(memory_dir)
        transcripts = find_transcripts(project_dir)

        for transcript in transcripts:
            transcript_key = str(transcript)
            fingerprint = get_file_fingerprint(transcript)

            # Check if already saved with same fingerprint
            prev = state["saved_sessions"].get(transcript_key, {})
            if prev.get("fingerprint") == fingerprint:
                total_skipped += 1
                continue

            # New or updated transcript — save it
            print(f"Saving memory for: {transcript.name}")
            try:
                messages = parse_transcript(str(transcript))
                if not messages:
                    print(f"  No messages found, skipping.")
                    continue

                model = detect_model(messages)
                summary = generate_summary(messages, model)

                # If we previously saved this session, remove old file
                old_file = prev.get("memory_file")
                if old_file:
                    old_path = memory_dir / old_file
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

                # Remove old entry for this transcript if exists
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
                update_save_state(memory_dir, transcript_key, fingerprint, filename)

                total_saved += 1
                print(f"  Saved: {filename} ({len(messages)} messages)")

            except Exception as e:
                print(f"  Error processing {transcript.name}: {e}")

    print(f"\nDone. Saved: {total_saved}, Skipped (unchanged): {total_skipped}")


if __name__ == "__main__":
    auto_save_all()
