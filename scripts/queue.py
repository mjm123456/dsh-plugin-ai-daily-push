#!/usr/bin/env python3
"""daily-push 的补写队列：在桌面端没运行时也能按时产出「待生成」条目。

背景：DSH 的定时任务由宿主进程触发，桌面端没开着就错过了。这个脚本不联网、
不写简报——它只按日期把「今天该发但还没发」的日子记进队列，等下次 Agent
启动时由技能补写，或者由 --remind 直接推一条提醒到微信。

用法：
    python3 queue.py tick          # 记下今天（以及漏掉的最近 N 天）缺失的条目
    python3 queue.py list          # 列出队列
    python3 queue.py pop --date D  # 取出一条（Agent 补写成功后调用）
    python3 queue.py prune --keep 30

退出码：0 正常；1 出错（日志写不进等）。
"""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import sys
from pathlib import Path

HOME = Path.home() / ".dsh" / "ai-daily-push"
DIGESTS = HOME / "digests"
QUEUE = HOME / "queue.jsonl"
STATE = HOME / "state.json"
LOCK = HOME / ".queue.lock"
MAX_BACKFILL = 7  # 最多记 7 天，避免长期关机后一次刷出几十条


def today() -> dt.date:
    return dt.date.today()


def load_state() -> dict:
    if STATE.is_file():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
    return {}


def save_state(state: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE)


def queue_entries() -> list:
    if not QUEUE.is_file():
        return []
    out = []
    for line in QUEUE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue  # 坏行跳过，不让一条脏数据卡住整个队列
    return out


def append_entry(entry: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    with QUEUE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def digest_path(day: dt.date) -> Path:
    return DIGESTS / f"ai-{day.isoformat()}.md"


def cmd_tick(args) -> int:
    state = load_state()
    pending = {e.get("date") for e in queue_entries() if not e.get("done")}
    added = []
    day = today()
    for back in range(MAX_BACKFILL):
        d = day - dt.timedelta(days=back)
        if back > 0 and d in state.get("skipped", []):
            continue
        if digest_path(d).exists() or d.isoformat() in pending:
            continue
        append_entry({"date": d.isoformat(), "addedAt": dt.datetime.now().isoformat(timespec="seconds")})
        added.append(d.isoformat())
    state["checkedAt"] = dt.datetime.now().isoformat(timespec="seconds")
    save_state(state)
    if args.print_only and not args.quiet:
        for a in added:
            print(f"queued {a}")
    return 0


def cmd_list(args) -> int:
    for e in queue_entries():
        if e.get("done"):
            continue
        print(e.get("date"))
    return 0


def cmd_pop(args) -> int:
    entries = queue_entries()
    target = args.date or (entries[0].get("date") if entries else None)
    if not target:
        print("队列为空", file=sys.stderr)
        return 1
    kept = []
    popped = False
    for e in entries:
        if not popped and e.get("date") == target:
            e["done"] = True
            e["doneAt"] = dt.datetime.now().isoformat(timespec="seconds")
            popped = True
        kept.append(e)
    HOME.mkdir(parents=True, exist_ok=True)
    tmp = QUEUE.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in kept), encoding="utf-8")
    tmp.replace(QUEUE)
    print(target)
    return 0


def cmd_prune(args) -> int:
    entries = queue_entries()
    keep = [e for e in entries if not e.get("done")][-args.keep:]
    tmp = QUEUE.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in keep), encoding="utf-8")
    tmp.replace(QUEUE)
    return 0


def cmd_skip(args) -> int:
    state = load_state()
    skipped = set(state.get("skipped", [])) | {args.date}
    state["skipped"] = sorted(skipped)[-90:]
    save_state(state)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="ai-daily-push 补写队列")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tick", help="记录今天及最近漏掉的条目")
    t.add_argument("--print-only", action="store_true", help="打印新增日期（默认也打印）")
    t.add_argument("--quiet", action="store_true")
    sub.add_parser("list", help="列出待生成条目")
    p = sub.add_parser("pop", help="标记某天已生成")
    p.add_argument("--date")
    pr = sub.add_parser("prune", help="清理已完成条目")
    pr.add_argument("--keep", type=int, default=100)
    sk = sub.add_parser("skip", help="把某天加入「不补发」列表，如假期")
    sk.add_argument("--date", required=True)
    args = ap.parse_args()

    HOME.mkdir(parents=True, exist_ok=True)
    with LOCK.open("w") as lock:  # 防止 cron 与手动调用撞车
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return 0  # 另一个 tick 正在跑，本次直接放过
        return {
            "tick": cmd_tick,
            "list": cmd_list,
            "pop": cmd_pop,
            "prune": cmd_prune,
            "skip": cmd_skip,
        }[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
