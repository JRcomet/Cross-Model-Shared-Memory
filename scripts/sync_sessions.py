#!/usr/bin/env python3
"""
sync_sessions.py — Read and display memories from other Claude sessions.

Scans the shared memory directory and presents summaries from other sessions,
enabling cross-model context sharing (e.g., Opus reading what Sonnet discussed).
"""

import argparse
import json
import os
import sys
from pathlib import Path


def load_index(memory_dir: str) -> list[dict]:
    """Load the memory index."""
    index_path = os.path.join(memory_dir, "memory_index.json")
    if not os.path.exists(index_path):
        return []

    with open(index_path, "r") as f:
        index = json.load(f)

    return index.get("memories", [])


def read_memory_file(memory_dir: str, filename: str) -> str:
    """Read a memory markdown file."""
    filepath = os.path.join(memory_dir, filename)
    if not os.path.exists(filepath):
        return ""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def sync(memory_dir: str, current_session: str = "", limit: int = 5, model_filter: str = ""):
    """Read and display memories from other sessions."""
    if not os.path.exists(memory_dir):
        print("No memory directory found. No previous sessions have been saved.")
        print(f"Expected location: {memory_dir}")
        return

    entries = load_index(memory_dir)

    if not entries:
        # Fall back to scanning .md files directly
        md_files = sorted(Path(memory_dir).glob("session_*.md"), reverse=True)
        if not md_files:
            print("No session memories found. Use 'save memory' to create one.")
            return

        for md_file in md_files[:limit]:
            print(f"\n{'='*60}")
            print(read_memory_file(memory_dir, md_file.name))
        return

    # Filter and sort
    filtered = entries
    if model_filter:
        filtered = [e for e in filtered if e.get("model", "") == model_filter]

    # Sort by timestamp descending
    filtered.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    if not filtered:
        print(f"No memories found" + (f" for model={model_filter}" if model_filter else "") + ".")
        return

    print(f"Found {len(filtered)} session memories" +
          (f" (showing latest {limit})" if len(filtered) > limit else "") + ":\n")

    for entry in filtered[:limit]:
        filename = entry.get("file", "")
        model = entry.get("model", "unknown")
        timestamp = entry.get("timestamp", "unknown")
        preview = entry.get("preview", "")

        print(f"{'='*60}")
        print(f"📌 {filename} | Model: {model} | Time: {timestamp}")
        print(f"   Preview: {preview}")
        print()

        content = read_memory_file(memory_dir, filename)
        if content:
            print(content)
        else:
            print("   (Memory file not found)")

        print()


def main():
    parser = argparse.ArgumentParser(description="Sync session memories")
    parser.add_argument("--memory-dir", required=True, help="Path to memory directory")
    parser.add_argument("--current-session", default="", help="Current session ID to exclude")
    parser.add_argument("--limit", type=int, default=5, help="Max memories to show")
    parser.add_argument("--model", default="", help="Filter by model (opus/sonnet/haiku)")
    args = parser.parse_args()

    sync(args.memory_dir, args.current_session, args.limit, args.model)


if __name__ == "__main__":
    main()
