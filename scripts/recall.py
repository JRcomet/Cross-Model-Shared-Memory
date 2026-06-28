#!/usr/bin/env python3
"""
recall.py — On-demand memory retrieval (zero-dependency, pure Python).

Solves the "全倒" problem: instead of dumping ALL memory into context every
session, the auto-loaded context.md stays small (long-term + latest few), and
when Claude needs something OLDER or more specific, it runs:

    python3 recall.py "关键词 / query"

It scores every saved memory block (TF-IDF cosine, with Chinese char+bigram
tokenization so it works in 中文 and English) and prints the most relevant ones.

Sources scanned (in the Downloads / memory folder):
  - session-memory-context.md         (recent + long-term, already loaded)
  - session-memory-archive.md         (older sessions, NOT auto-loaded)
  - cowork_memory_*.md                (individual session dumps)
  - memory-longterm.md                (curated standing facts)

Usage:
    python3 recall.py "Atomi 估值 回报模型"
    python3 recall.py "陈祥 设计 假数据" --k 3 --full
    python3 recall.py "BaZi 八字" --dir ~/Downloads
"""

import argparse
import glob
import math
import os
import re
import sys
from collections import Counter


# ---------- tokenization (English words + Chinese chars & bigrams) ----------
_CJK = r'一-鿿'

def tokenize(text: str) -> list[str]:
    text = text.lower()
    toks = re.findall(r'[a-z0-9]+', text)               # ascii words / numbers
    for run in re.findall(fr'[{_CJK}]+', text):          # contiguous CJK runs
        toks.extend(list(run))                           # unigrams
        toks.extend(run[i:i + 2] for i in range(len(run) - 1))  # bigrams
    return toks


# ---------- find the memory folder ----------
def find_memory_dir(explicit: str = "") -> str:
    cands = []
    if explicit:
        cands.append(os.path.expanduser(explicit))
    cands += [
        *glob.glob("/sessions/*/mnt/Downloads"),
        os.path.expanduser("~/Downloads"),
        "/mnt/Downloads",
    ]
    for c in cands:
        if c and os.path.isdir(c):
            return c
    return ""


# ---------- load all memory blocks ----------
def split_blocks(text: str, source: str) -> list[dict]:
    """Split a markdown memory file into blocks keyed on '## ' headers."""
    blocks = []
    # split on level-2 headers, keep the header with its body
    parts = re.split(r'(?m)^(?=##\s)', text)
    for part in parts:
        part = part.strip()
        if len(part) < 20:
            continue
        header = part.splitlines()[0].lstrip('# ').strip()
        blocks.append({"source": source, "header": header, "text": part})
    return blocks


def load_blocks(mem_dir: str) -> list[dict]:
    blocks = []
    named = [
        "session-memory-context.md",
        "session-memory-archive.md",
        "memory-longterm.md",
    ]
    paths = [os.path.join(mem_dir, n) for n in named]
    paths += sorted(glob.glob(os.path.join(mem_dir, "cowork_memory_*.md")))
    seen = set()
    for p in paths:
        if not os.path.exists(p):
            continue
        try:
            txt = open(p, "r", encoding="utf-8").read()
        except Exception:
            continue
        for b in split_blocks(txt, os.path.basename(p)):
            # de-dup identical block bodies across files
            key = b["text"][:120]
            if key in seen:
                continue
            seen.add(key)
            blocks.append(b)
    return blocks


# ---------- TF-IDF scoring ----------
def score(query: str, blocks: list[dict]) -> list[tuple]:
    if not blocks:
        return []
    docs = [Counter(tokenize(b["text"])) for b in blocks]
    N = len(docs)
    df = Counter()
    for d in docs:
        for t in d:
            df[t] += 1
    idf = {t: math.log((N + 1) / (c + 1)) + 1 for t, c in df.items()}

    q = Counter(tokenize(query))
    if not q:
        return []
    qvec = {t: (1 + math.log(c)) * idf.get(t, math.log(N + 1) + 1) for t, c in q.items()}
    qnorm = math.sqrt(sum(v * v for v in qvec.values())) or 1.0

    results = []
    for b, d in zip(blocks, docs):
        dot = 0.0
        dnorm = 0.0
        for t, c in d.items():
            w = (1 + math.log(c)) * idf.get(t, 0.0)
            dnorm += w * w
            if t in qvec:
                dot += w * qvec[t]
        dnorm = math.sqrt(dnorm) or 1.0
        sim = dot / (qnorm * dnorm)
        if sim > 0:
            results.append((sim, b))
    results.sort(key=lambda x: x[0], reverse=True)
    return results


def main():
    ap = argparse.ArgumentParser(description="On-demand memory retrieval")
    ap.add_argument("query", help="What to recall (中文 or English)")
    ap.add_argument("--dir", default="", help="Memory/Downloads folder")
    ap.add_argument("--k", type=int, default=5, help="How many blocks to return")
    ap.add_argument("--full", action="store_true", help="Print full block text (else truncated)")
    args = ap.parse_args()

    mem_dir = find_memory_dir(args.dir)
    if not mem_dir:
        print("No memory folder found.", file=sys.stderr)
        sys.exit(1)

    blocks = load_blocks(mem_dir)
    if not blocks:
        print(f"No memory blocks found in {mem_dir}")
        return

    ranked = score(args.query, blocks)
    if not ranked:
        print(f"No relevant memory for: {args.query!r}")
        return

    print(f"🔎 recall: {args.query!r}  —  {len(blocks)} blocks scanned, top {min(args.k, len(ranked))}:\n")
    for sim, b in ranked[: args.k]:
        body = b["text"] if args.full else (b["text"][:600] + ("…" if len(b["text"]) > 600 else ""))
        print(f"{'='*64}\n[{b['source']}]  relevance={sim:.3f}\n{body}\n")


if __name__ == "__main__":
    main()
