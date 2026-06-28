#!/usr/bin/env python3
"""
consolidate.py — Tidy up accumulated memory (zero-dependency, pure Python).

Over time the Downloads folder fills with cowork_memory_*.md dumps and the
archive grows unbounded. This script:

  1. De-duplicates cowork_memory_*.md — keeps the NEWEST file per
     (model, session) and moves the rest into .cowork_memories_old/.
  2. Caps session-memory-archive.md to the latest N session blocks
     (older blocks stay recoverable in the moved cowork_memory files).
  3. Prints a report.

SAFE BY DEFAULT: dry-run only. Pass --apply to actually move/trim.
Nothing is ever hard-deleted — duplicates are MOVED to .cowork_memories_old/.

Usage:
    python3 consolidate.py                 # dry-run, show what would happen
    python3 consolidate.py --apply         # actually do it
    python3 consolidate.py --apply --keep-archive 40
"""

import argparse
import glob
import os
import re
import shutil
import sys
from datetime import datetime


def find_memory_dir(explicit: str = "") -> str:
    cands = [os.path.expanduser(explicit)] if explicit else []
    cands += [*glob.glob("/sessions/*/mnt/Downloads"), os.path.expanduser("~/Downloads"), "/mnt/Downloads"]
    for c in cands:
        if c and os.path.isdir(c):
            return c
    return ""


# filename: cowork_memory_<YYYYmmdd_HHMMSS>_<model>_<session8>.md
_PAT = re.compile(r'cowork_memory_(\d{8}_\d{6})_([a-z]+)_([^.]+)\.md$')


def dedup_dumps(mem_dir: str, apply: bool) -> list[str]:
    log = []
    files = sorted(glob.glob(os.path.join(mem_dir, "cowork_memory_*.md")))
    groups = {}
    for f in files:
        m = _PAT.search(os.path.basename(f))
        if not m:
            continue
        ts, model, sess = m.groups()
        groups.setdefault((model, sess), []).append((ts, f))

    old_dir = os.path.join(mem_dir, ".cowork_memories_old")
    moved = 0
    for (model, sess), items in groups.items():
        if len(items) <= 1:
            continue
        items.sort(reverse=True)              # newest first by timestamp
        keep = items[0][1]
        losers = [f for _, f in items[1:]]
        log.append(f"  {model}/{sess}: keep {os.path.basename(keep)}, archive {len(losers)} older dup(s)")
        if apply:
            os.makedirs(old_dir, exist_ok=True)
            for f in losers:
                try:
                    shutil.move(f, os.path.join(old_dir, os.path.basename(f)))
                    moved += 1
                except Exception as e:
                    log.append(f"    ! could not move {f}: {e}")
    log.insert(0, f"De-dup dumps: {len(files)} files, {len(groups)} unique sessions, "
                  f"{'moved ' + str(moved) if apply else 'would archive duplicates'}.")
    return log


def cap_archive(mem_dir: str, keep: int, apply: bool) -> list[str]:
    path = os.path.join(mem_dir, "session-memory-archive.md")
    if not os.path.exists(path):
        return ["Archive: none yet (nothing to cap)."]
    txt = open(path, "r", encoding="utf-8").read()
    blocks = [b.strip() for b in re.split(r'(?m)^(?=##\s)', txt) if b.strip().startswith("##")]
    if len(blocks) <= keep:
        return [f"Archive: {len(blocks)} blocks (≤ keep={keep}), no trim needed."]
    kept = blocks[:keep]   # blocks are stored newest-first
    out = ["# Session Memory — Archive (older sessions, not auto-loaded)",
           f"_Capped to latest {keep} on {datetime.now():%Y-%m-%d %H:%M}; use recall.py to search._", "", "---", ""]
    for b in kept:
        out += [b, "", "---", ""]
    if apply:
        open(path, "w", encoding="utf-8").write("\n".join(out))
    return [f"Archive: {len(blocks)} → {keep} blocks ({'trimmed' if apply else 'would trim'}; "
            f"{len(blocks)-keep} oldest dropped from archive, still in cowork_memory_* / .old)."]


def main():
    ap = argparse.ArgumentParser(description="Consolidate / tidy memory")
    ap.add_argument("--dir", default="")
    ap.add_argument("--apply", action="store_true", help="Actually move/trim (default: dry-run)")
    ap.add_argument("--keep-archive", type=int, default=40, help="Max session blocks to keep in archive")
    args = ap.parse_args()

    mem_dir = find_memory_dir(args.dir)
    if not mem_dir:
        print("No memory folder found.", file=sys.stderr)
        sys.exit(1)

    mode = "APPLY" if args.apply else "DRY-RUN (use --apply to act)"
    print(f"🧹 consolidate — {mem_dir}  [{mode}]\n")
    for line in dedup_dumps(mem_dir, args.apply):
        print(line)
    print()
    for line in cap_archive(mem_dir, args.keep_archive, args.apply):
        print(line)
    print("\nDone." + ("" if args.apply else "  (nothing changed — dry run)"))


if __name__ == "__main__":
    main()
