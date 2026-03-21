#!/usr/bin/env python3
"""
save_session.py — Extract and save a structured memory from a Claude session transcript.

Parses the JSONL transcript, extracts key information, and writes a compact
markdown summary to the shared memory directory.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path


def parse_transcript(jsonl_path: str, max_bytes: int = 10 * 1024 * 1024) -> list[dict]:
    """Parse a JSONL transcript file, extracting user and assistant messages."""
    messages = []
    file_size = os.path.getsize(jsonl_path)

    with open(jsonl_path, "r", encoding="utf-8") as f:
        # If file is too large, seek to the last max_bytes
        if file_size > max_bytes:
            f.seek(file_size - max_bytes)
            f.readline()  # Skip partial line

        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg = entry.get("message")
            if not msg:
                continue

            role = msg.get("role")
            if role not in ("user", "assistant"):
                continue

            content = msg.get("content")
            if not content:
                continue

            # Extract text content, skip thinking/tool blocks
            text_parts = []
            if isinstance(content, str):
                text_parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif block.get("type") == "tool_use":
                            # Just note which tool was used
                            tool_name = block.get("name", "unknown")
                            text_parts.append(f"[Used tool: {tool_name}]")
                    elif isinstance(block, str):
                        text_parts.append(block)

            text = "\n".join(text_parts).strip()
            if not text:
                continue

            # Detect model name from assistant messages
            model = msg.get("model", "")

            messages.append({
                "role": role,
                "text": text[:2000],  # Truncate very long messages
                "model": model,
            })

    return messages


def extract_files_mentioned(messages: list[dict]) -> list[str]:
    """Extract file paths mentioned in the conversation."""
    files = set()
    pattern = r'(?:/[\w.-]+)+\.\w+'
    for msg in messages:
        matches = re.findall(pattern, msg["text"])
        for m in matches:
            # Filter out common non-file paths
            if not any(x in m for x in ["/http", "/www", "/.git/objects"]):
                files.add(m)
    return sorted(files)[:20]  # Cap at 20 files


def extract_user_messages(messages: list[dict]) -> list[str]:
    """Get all user messages for topic extraction."""
    return [m["text"] for m in messages if m["role"] == "user"]


def detect_model(messages: list[dict]) -> str:
    """Detect which model was used in this session."""
    for msg in messages:
        model = msg.get("model", "")
        if model:
            if "opus" in model:
                return "opus"
            elif "sonnet" in model:
                return "sonnet"
            elif "haiku" in model:
                return "haiku"
    return "unknown"


def generate_summary(messages: list[dict], model_name: str) -> str:
    """Generate a structured markdown summary of the session."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    user_msgs = extract_user_messages(messages)
    files = extract_files_mentioned(messages)
    detected_model = model_name or detect_model(messages)

    # Build conversation highlights (sample key exchanges)
    highlights = []
    for i, msg in enumerate(messages):
        if msg["role"] == "user" and len(msg["text"]) > 20:
            # Get the user message and the following assistant response
            user_text = msg["text"][:300]
            assistant_text = ""
            if i + 1 < len(messages) and messages[i + 1]["role"] == "assistant":
                assistant_text = messages[i + 1]["text"][:300]
            highlights.append((user_text, assistant_text))

    # Take first 3 and last 2 highlights for coverage
    if len(highlights) > 5:
        selected = highlights[:3] + highlights[-2:]
    else:
        selected = highlights

    # Build the markdown
    lines = [
        f"# Session Memory — {now} ({detected_model})",
        "",
        "## Session Info",
        f"- **Model**: {detected_model}",
        f"- **Date**: {now}",
        f"- **Total exchanges**: {len(user_msgs)} user messages, {len(messages) - len(user_msgs)} assistant messages",
        "",
        "## User Requests (chronological)",
    ]

    for i, um in enumerate(user_msgs[:15], 1):
        # First 150 chars of each user message
        preview = um.replace("\n", " ")[:150]
        lines.append(f"{i}. {preview}")

    lines.append("")
    lines.append("## Files Referenced")
    if files:
        for f in files:
            lines.append(f"- `{f}`")
    else:
        lines.append("- (none detected)")

    lines.append("")
    lines.append("## Conversation Highlights")
    for j, (user_text, asst_text) in enumerate(selected, 1):
        u_preview = user_text.replace("\n", " ")[:200]
        a_preview = asst_text.replace("\n", " ")[:200]
        lines.append(f"\n### Exchange {j}")
        lines.append(f"**User**: {u_preview}")
        if a_preview:
            lines.append(f"**Assistant**: {a_preview}")

    lines.append("")
    lines.append("## Raw Stats")
    lines.append(f"- Total messages parsed: {len(messages)}")
    lines.append(f"- User messages: {len(user_msgs)}")
    lines.append(f"- Files mentioned: {len(files)}")

    return "\n".join(lines)


def update_index(memory_dir: str, memory_file: str, model: str, summary_preview: str):
    """Update the memory index JSON."""
    index_path = os.path.join(memory_dir, "memory_index.json")

    if os.path.exists(index_path):
        with open(index_path, "r") as f:
            index = json.load(f)
    else:
        index = {"memories": []}

    index["memories"].append({
        "file": memory_file,
        "model": model,
        "timestamp": datetime.now().isoformat(),
        "preview": summary_preview[:200],
    })

    with open(index_path, "w") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="Save session memory")
    parser.add_argument("--transcript", required=True, help="Path to session JSONL transcript")
    parser.add_argument("--memory-dir", required=True, help="Path to memory directory")
    parser.add_argument("--model", default="", help="Model name override")
    parser.add_argument("--session-id", default="", help="Session ID for deduplication")
    args = parser.parse_args()

    if not os.path.exists(args.transcript):
        print(f"Error: Transcript not found: {args.transcript}", file=sys.stderr)
        sys.exit(1)

    # Ensure memory dir exists
    os.makedirs(args.memory_dir, exist_ok=True)

    # Parse and summarize
    print(f"Parsing transcript: {args.transcript}")
    messages = parse_transcript(args.transcript)
    print(f"Extracted {len(messages)} messages")

    if not messages:
        print("No messages found in transcript.")
        sys.exit(0)

    model = args.model or detect_model(messages)
    summary = generate_summary(messages, model)

    # Save memory file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"session_{timestamp}_{model}.md"
    filepath = os.path.join(args.memory_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(summary)

    print(f"Memory saved: {filepath}")

    # Update index
    preview = f"Session with {model} — {len(messages)} messages"
    update_index(args.memory_dir, filename, model, preview)
    print("Memory index updated.")


if __name__ == "__main__":
    main()
