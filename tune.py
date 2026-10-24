#!/usr/bin/env python3
"""Tune a bot's WHEIGHTS by hill climbing: change one weight, play the
changed bot against the current best, keep the change only if it wins clearly.

    python3 tune.py V5                      # tune bot/V5Bot.py
    python3 tune.py V5 --games 400 --workers 3
    python3 tune.py V5 --resume             # continue from tune_V5Bot.json

The bot needs a WHEIGHTS dict and a DEPTH global at the top of its file.
Each challenger plays --games games against the best weights, on fresh boards,
each board twice with the colours swapped. It wins clearly when
(its wins - best's wins) > 2 * sqrt(decisive games). After a full pass with
no change the step gets smaller (--shrink); tuning stops when the step is below --min-step.
The best weights are saved to tune_<bot>.json after every change, so it's safe
to stop with Ctrl-C at any time.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from benchTest import BOT_DIR, play_game
from play import Style
from traversal import all_legal_moves, apply_move, generate_board, new_game

PLAIN = Style(color=False)


def bot_path(name: str) -> Path:
    for path in (BOT_DIR / f"{name}Bot.py", BOT_DIR / f"{name}.py"):
        if path.exists():
            return path
    sys.exit(f"No bot file bot/{name}Bot.py or bot/{name}.py")


def load_copy(path: Path, label: str):
    """Load a separate copy of the bot module, with its own globals."""
    spec = importlib.util.spec_from_file_location(f"tune_{label}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- worker side: each process keeps its own two copies of the bot ---

_copies: dict[str, object] = {}


def _init_worker(path: str) -> None:
    sys.stdout = open(os.devnull, "w")  # hide the bot's prints
    for label in ("best", "challenger"):
        _copies[label] = load_copy(Path(path), label)


def _play_one(task: tuple) -> tuple[str | None, str | None]:
    """Play one game; return (winner label or None for a draw, error)."""
    board_seed, pushes, challenger_is_red, weights, depth = task
    for label in ("best", "challenger"):
        _copies[label].WHEIGHTS = dict(weights[label])
        _copies[label].DEPTH = depth
    red, blue = ("challenger", "best") if challenger_is_red else ("best", "challenger")
    board = generate_board(pushes=pushes, seed=board_seed)
    r = play_game(red, blue, _copies, board, watch=False, style=PLAIN)
    return r.winner_name(), r.error


# --- main side ---

def weights_matter(path: Path, weights: dict, depth: int) -> bool:
    """True if very different weights make the bot choose different moves."""
    copy = load_copy(path, "check")
    copy.DEPTH = depth
    rng = random.Random(0)
    # Scaling every weight by the same factor never changes a move, so make
    # some weights much bigger and the others much smaller
    other = {k: (v * 10 if i % 2 == 0 else v / 10) if v else 10 for i, (k, v) in enumerate(weights.items())}
    stdout, sys.stdout = sys.stdout, open(os.devnull, "w")
    try:
        for i in range(30):
            state = new_game(generate_board(seed=10_000 + i))
            for _ in range(rng.randrange(4, 20)):  # a random position mid-game
                moves = all_legal_moves(state)
                if state.game_over or not moves:
                    break
                m = rng.choice(moves)
                state = apply_move(state, m.piece_id, m.to_row, m.to_col)
            if state.game_over or not all_legal_moves(state):
                continue
            copy.WHEIGHTS = dict(weights)
            a = copy.choose_move(state.copy())
            copy.WHEIGHTS = dict(other)
            if copy.choose_move(state.copy()) != a:
                return True
        return False
    finally:
        sys.stdout = stdout


def match(pool, best: dict, challenger: dict, args, first_seed: int) -> tuple[int, int, int]:
    """Challenger vs best; return (challenger wins, best wins, draws)."""
    weights = {"best": best, "challenger": challenger}
    tasks = [(first_seed + i // 2, args.pushes, i % 2 == 0, weights, args.depth) for i in range(args.games)]
    counts = {"challenger": 0, "best": 0, None: 0}
    for winner, error in pool.map(_play_one, tasks):
        if error:
            sys.exit(f"A game was forfeited by a bot error:\n{error}")
        counts[winner] += 1
    return counts["challenger"], counts["best"], counts[None]


def nudge(value: float, step: float, up: bool) -> float:
    if value == 0:
        return 1 if up else -1
    return round(value * step if up else value / step, 3)


def main() -> None:
    parser = argparse.ArgumentParser(description="Tune a bot's WHEIGHTS by hill climbing.")
    parser.add_argument("bot", help="bot name, e.g. 'V5' for bot/V5Bot.py")
    parser.add_argument("--games", type=int, default=200, help="games per challenger, even (default 200)")
    parser.add_argument("--depth", type=int, default=1, help="DEPTH to tune at (default 1, fast)")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1),
                        help="games played at once (default: CPUs - 1)")
    parser.add_argument("--step", type=float, default=1.5, help="first multiplier for a weight (default 1.5)")
    parser.add_argument("--min-step", type=float, default=1.1, help="stop below this step (default 1.1)")
    parser.add_argument("--shrink", type=float, default=0.5,
                        help="after a pass with no change, keep this fraction of the step's change, "
                             "e.g. 0.5 turns x1.5 into x1.25 (default 0.5)")
    parser.add_argument("--only", nargs="+", metavar="KEY", help="tune only these weights")
    parser.add_argument("--seed", type=int, default=1, help="seed for the boards (default 1)")
    parser.add_argument("--pushes", type=int, default=400, help="how rugged the boards are (default 400)")
    parser.add_argument("--resume", action="store_true", help="start from the saved tune_<bot>.json")
    args = parser.parse_args()
    args.games += args.games % 2  # every board is played with both colours
    if not 0 < args.shrink < 1:
        parser.error("--shrink must be between 0 and 1")

    path = bot_path(args.bot)
    module = load_copy(path, "main")
    if not isinstance(getattr(module, "WHEIGHTS", None), dict) or not hasattr(module, "DEPTH"):
        sys.exit(f"{path.name} needs a WHEIGHTS dict and a DEPTH global at the top.")
    out = Path(__file__).parent / f"tune_{path.stem}.json"

    best = dict(module.WHEIGHTS)
    step, next_seed = args.step, args.seed
    if args.resume and out.exists():
        saved = json.loads(out.read_text())
        best, step, next_seed = saved["weights"], saved["step"], saved["next_seed"]
        print(f"Resuming from {out.name}")
    keys = args.only or list(best)
    unknown = [k for k in keys if k not in best]
    if unknown:
        sys.exit(f"Not in WHEIGHTS: {', '.join(unknown)}. Keys: {', '.join(best)}")

    if not weights_matter(path, best, args.depth):
        print("Warning: changing WHEIGHTS doesn't change the bot's moves. Check that the "
              "search really calls the function that uses WHEIGHTS.\n")

    def save() -> None:
        out.write_text(json.dumps({"weights": best, "step": step, "next_seed": next_seed}, indent=2) + "\n")

    print(f"Tuning {path.name} at depth {args.depth}, {args.games} games per challenger, "
          f"{args.workers} at once")
    print(f"Start: WHEIGHTS = {best}\n")
    start = time.time()
    with ProcessPoolExecutor(args.workers, initializer=_init_worker, initargs=(str(path),)) as pool:
        try:
            while step >= args.min_step:
                changed = False
                for key in keys:
                    for up in (True, False):
                        improved = False
                        # Keep pushing in this direction while it keeps winning
                        while True:
                            challenger = dict(best, **{key: nudge(best[key], step, up)})
                            c, b, d = match(pool, best, challenger, args, next_seed)
                            next_seed += args.games // 2  # fresh boards for every match
                            decisive = c + b
                            limit = 2 * math.sqrt(decisive) if decisive else 0
                            better = decisive > 0 and c - b > limit
                            print(f"{key:>10} {best[key]:>7} -> {challenger[key]:<7} "
                                  f"challenger {c:>4}  best {b:>4}  draws {d:>4}   "
                                  f"gap {c - b:>+4} vs {limit:5.1f}  {'KEEP' if better else 'no'}",
                                  flush=True)
                            if not better:
                                break
                            best, improved, changed = challenger, True, True
                            save()
                        if improved:
                            break  # no need to try the other direction
                if not changed:
                    step = 1 + (step - 1) * args.shrink
                    print(f"\nNo change this pass; smaller step: x{step:.3f}\n")
                save()
        except KeyboardInterrupt:
            pool.shutdown(cancel_futures=True)
            print("\nStopped.")

    minutes = (time.time() - start) / 60
    print(f"\nBest after {minutes:.1f} min (saved in {out.name}):")
    print(f"WHEIGHTS = {best}")


if __name__ == "__main__":
    main()
