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
        if file_size > max_bytes:
            f.seek(file_size - max_bytes)
            f.readline()

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

            text_parts = []
            tools_used = []

            if isinstance(content, str):
                text_parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        btype = block.get("type", "")
                        if btype == "text":
                            text_parts.append(block.get("text", ""))
                        elif btype == "tool_use":
                            tool_name = block.get("name", "unknown")
                            tools_used.append(tool_name)
                            # Extract meaningful tool inputs
                            tool_input = block.get("input", {})
                            if isinstance(tool_input, dict):
                                # Capture file paths from Write/Edit tools
                                fp = tool_input.get("file_path", "")
                                if fp:
                                    text_parts.append(f"[File: {fp}]")
                                # Capture commands from Bash
                                cmd = tool_input.get("command", "")
                                if cmd and len(cmd) < 200:
                                    text_parts.append(f"[Command: {cmd}]")
                        elif btype == "tool_result":
                            # Skip large tool results but note them
                            pass
                    elif isinstance(block, str):
                        text_parts.append(block)

            text = "\n".join(text_parts).strip()
            if not text and not tools_used:
                continue

            model = msg.get("model", "")

            messages.append({
                "role": role,
                "text": text[:3000],
                "model": model,
                "tools": tools_used,
            })

    return messages


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


def extract_topics(messages: list[dict]) -> list[str]:
    """Extract key topics from the conversation using keyword analysis."""
    all_text = " ".join(m["text"] for m in messages).lower()

    topic_keywords = {
        "Polymarket交易机器人": ["polymarket", "clob", "trading bot", "bet", "wager"],
        "天气预测模型": ["weather", "temperature", "forecast", "open-meteo", "sigmoid"],
        "Python脚本开发": ["python", ".py", "script", "pip install"],
        "数据分析": ["csv", "pandas", "dataframe", "analysis", "calibration"],
        "AI自动化服务": ["automation", "ai service", "闲鱼", "小红书", "变现"],
        "文件处理": ["docx", "pdf", "xlsx", "pptx", "document"],
        "网页开发": ["html", "css", "react", "javascript", "frontend"],
        "API对接": ["api", "endpoint", "request", "response", "token"],
        "Git/GitHub": ["git", "github", "commit", "push", "repo"],
        "Telegram Bot": ["telegram", "bot token", "chat_id"],
        "图片生成": ["image", "pillow", "pil", "png", "封面"],
        "翻译/字幕": ["translate", "subtitle", "srt", "翻译", "字幕"],
        "系统配置": ["config", "setup", "install", "environment"],
        "Chrome浏览器操作": ["browser", "chrome", "navigate", "click"],
        "记忆/跨会话": ["memory", "session", "sync", "记忆", "同步"],
    }

    found = []
    for topic, keywords in topic_keywords.items():
        if any(kw in all_text for kw in keywords):
            found.append(topic)

    return found[:8]  # Max 8 topics


def extract_key_outcomes(messages: list[dict]) -> list[str]:
    """Extract key outcomes — files created, decisions made, results achieved."""
    outcomes = []
    files_created = set()
    commands_run = set()

    for msg in messages:
        text = msg["text"]

        # Files created/modified
        file_matches = re.findall(r'\[File: ([^\]]+)\]', text)
        for f in file_matches:
            if any(ext in f for ext in ['.py', '.md', '.html', '.jsx', '.docx', '.pdf', '.pptx', '.xlsx', '.png', '.csv', '.sh']):
                files_created.add(f)

        # Key commands
        cmd_matches = re.findall(r'\[Command: ([^\]]+)\]', text)
        for c in cmd_matches:
            if any(kw in c for kw in ['git push', 'pip install', 'npm', 'nohup', 'python3']):
                commands_run.add(c[:100])

        # Look for success indicators in assistant messages
        if msg["role"] == "assistant":
            if any(kw in text for kw in ['成功', 'success', '✓', 'Done', '完成', 'saved', 'created']):
                # Extract the sentence containing the success
                for sentence in re.split(r'[。.!\n]', text):
                    if any(kw in sentence for kw in ['成功', 'success', '✓', 'Done', '完成']):
                        clean = sentence.strip()[:150]
                        if len(clean) > 15:
                            outcomes.append(clean)
                            break

    if files_created:
        outcomes.insert(0, f"创建/修改了文件: {', '.join(sorted(files_created)[:10])}")
    if commands_run:
        notable = [c for c in commands_run if 'git push' in c or 'nohup' in c]
        if notable:
            outcomes.append(f"执行了关键命令: {'; '.join(sorted(notable)[:3])}")

    return outcomes[:8]


def generate_summary(messages: list[dict], model_name: str) -> str:
    """Generate a structured markdown summary of the session."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    user_msgs = [m for m in messages if m["role"] == "user"]
    asst_msgs = [m for m in messages if m["role"] == "assistant"]
    model = model_name or detect_model(messages)
    topics = extract_topics(messages)
    outcomes = extract_key_outcomes(messages)

    # Build meaningful conversation pairs
    pairs = []
    for i, msg in enumerate(messages):
        if msg["role"] == "user":
            user_text = msg["text"].replace("\n", " ").strip()
            # Skip very short or tool-only messages
            if len(user_text) < 10:
                continue
            # Skip terminal output pastes (very long with special chars)
            if user_text.count('%') > 3 or user_text.count('$') > 5:
                user_text = user_text[:200] + "... [terminal output]"

            asst_text = ""
            if i + 1 < len(messages) and messages[i + 1]["role"] == "assistant":
                asst_text = messages[i + 1]["text"].replace("\n", " ").strip()
                # Remove tool call noise
                asst_text = re.sub(r'\[Used tool: \w+\]\s*', '', asst_text)
                asst_text = re.sub(r'\[File: [^\]]+\]\s*', '', asst_text)
                asst_text = re.sub(r'\[Command: [^\]]+\]\s*', '', asst_text)

            if user_text and (len(user_text) > 15 or asst_text):
                pairs.append((user_text[:400], asst_text[:400]))

    # Select representative pairs: first 3, middle 2, last 3
    if len(pairs) > 8:
        mid = len(pairs) // 2
        selected = pairs[:3] + pairs[mid:mid+2] + pairs[-3:]
    else:
        selected = pairs

    lines = [
        f"## Session: {now} ({model}) — {len(user_msgs)} exchanges",
        "",
    ]

    if topics:
        lines.append(f"**Topics**: {', '.join(topics)}")
        lines.append("")

    if outcomes:
        lines.append("**Key outcomes**:")
        for o in outcomes:
            lines.append(f"- {o}")
        lines.append("")

    if selected:
        lines.append("**Conversation flow**:")
        for j, (u, a) in enumerate(selected, 1):
            u_short = u[:250]
            a_short = a[:250] if a else "(tool execution)"
            lines.append(f"  {j}. **User**: {u_short}")
            lines.append(f"     **Claude**: {a_short}")
        lines.append("")

    return "\n".join(lines)


def generate_compact_summary(messages: list[dict], model_name: str) -> str:
    """Generate a very compact summary for CLAUDE.md injection (max ~300 chars)."""
    model = model_name or detect_model(messages)
    user_msgs = [m for m in messages if m["role"] == "user"]
    topics = extract_topics(messages)

    if not user_msgs:
        return ""

    # Get the first meaningful user request
    first_request = ""
    for m in user_msgs:
        text = m["text"].replace("\n", " ").strip()
        if len(text) > 15 and not text.startswith("["):
            first_request = text[:120]
            break

    topic_str = ", ".join(topics[:4]) if topics else "general"
    now = datetime.now().strftime("%m-%d %H:%M")

    return f"[{now} {model}] Topics: {topic_str}. First request: {first_request}"


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
        "preview": summary_preview[:300],
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

    os.makedirs(args.memory_dir, exist_ok=True)

    print(f"Parsing transcript: {args.transcript}")
    messages = parse_transcript(args.transcript)
    print(f"Extracted {len(messages)} messages")

    if not messages:
        print("No messages found in transcript.")
        sys.exit(0)

    model = args.model or detect_model(messages)
    summary = generate_summary(messages, model)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"session_{timestamp}_{model}.md"
    filepath = os.path.join(args.memory_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(summary)

    print(f"Memory saved: {filepath}")

    preview = generate_compact_summary(messages, model)
    update_index(args.memory_dir, filename, model, preview)
    print("Memory index updated.")


if __name__ == "__main__":
    main()
