#!/usr/bin/env python3
"""Tune a bot's WHEIGHTS so its evaluation predicts who wins the stored games.

    python3 texelTune.py V7                        # games from data/games.db
    python3 texelTune.py V7 --min-elo 1300 --max-gap 200
    python3 texelTune.py V7 --only val_vanguard adv_vanguard

Texel tuning: every stored position gets a predicted chance that Red wins,
sigmoid(eval), and the error is how far that is from the real result of its
game (1 Red won, 0 Blue won, 0.5 draw). The weights are changed one at a time
while the average error goes down. No games are played, so a test takes
seconds instead of hundreds of games.

Only quiet positions are used: a position where the side to move can capture
or finish is in the middle of something and its eval means little. One game in
ten is kept aside as a test set; if the test error stops falling while the
training error still falls, the weights are learning those games by heart.

Always confirm the result with a match against the old weights: predicting
results better usually means winning more, but not always.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
import time
import zlib
from pathlib import Path

from bot.dataIntegration import DB_PATH, state_from_json
from bot.distanceMap import build_map
from traversal import all_legal_moves
from tune import bot_path, load_copy, nudge


def select_games(con: sqlite3.Connection, args) -> list[tuple[str, str, int]]:
    """(game_id, board, winner) of the games to learn from."""
    exclude = set(args.exclude)
    rows = con.execute("""
        SELECT g.game_id, g.board, g.winner, g.game_type, g.player1, g.player2, b1.elo, b2.elo
        FROM games g
        LEFT JOIN bots b1 ON b1.name = g.player1
        LEFT JOIN bots b2 ON b2.name = g.player2
        ORDER BY g.game_id""").fetchall()
    games = []
    for game_id, board, winner, game_type, p1, p2, elo1, elo2 in rows:
        if game_type != "bot":
            if args.with_live:
                games.append((game_id, board, winner))
            continue
        if p1.split("@")[0] in exclude or p2.split("@")[0] in exclude:
            continue
        if elo1 is None or elo2 is None:
            continue  # not rated yet: run python3 tournament.py to refit
        if min(elo1, elo2) >= args.min_elo and abs(elo1 - elo2) <= args.max_gap:
            games.append((game_id, board, winner))
    return games


def is_quiet(state) -> bool:
    return not any(m.captured_id is not None or m.finishes for m in all_legal_moves(state))


def load_data(con: sqlite3.Connection, games: list, args) -> tuple[list, list]:
    """([(state, result)] for training, the same for testing)."""
    train, test = [], []
    start = time.time()
    for n, (game_id, board_text, winner) in enumerate(games, 1):
        board = json.loads(board_text)  # one board object per game
        result = {1: 1.0, 2: 0.0, 0: 0.5}[winner]
        # The same game always lands in the same set
        target = test if zlib.crc32(game_id.encode()) % 10 == 0 else train
        for ply, text in con.execute("SELECT ply, state FROM positions WHERE game_id = ? ORDER BY ply",
                                     (game_id,)):
            if ply < args.skip_opening:
                continue
            state = state_from_json(text, board)
            if state.game_over or (not args.keep_noisy and not is_quiet(state)):
                continue
            target.append((state, result))
        if n % 200 == 0 or n == len(games):
            print(f"\r  loading positions: game {n}/{len(games)}, {len(train) + len(test)} positions "
                  f"({time.time() - start:.0f} s)", end="", flush=True)
    print()
    return train, test


def predicted(value: float, k: float) -> float:
    """Chance that Red wins, from an eval."""
    x = max(-50.0, min(50.0, -k * value / 400))
    return 1 / (1 + 10 ** x)


def error_of(values: list[float], data: list, k: float) -> float:
    return sum((result - predicted(v, k)) ** 2 for v, (_, result) in zip(values, data)) / len(data)


def fit_k(values: list[float], data: list) -> float:
    """The sigmoid scale that best turns these evals into win chances."""
    lo, hi = math.log(1e-4), math.log(1e3)
    for _ in range(100):  # ternary search on log k
        a, b = lo + (hi - lo) / 3, hi - (hi - lo) / 3
        if error_of(values, data, math.exp(a)) < error_of(values, data, math.exp(b)):
            hi = b
        else:
            lo = a
    return math.exp((lo + hi) / 2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Tune a bot's WHEIGHTS on the stored games (Texel tuning).")
    parser.add_argument("bot", help="bot name, e.g. 'V7' for bot/V7Bot.py")
    parser.add_argument("--func", default="evaluation", help="evaluation function name (default evaluation)")
    parser.add_argument("--only", nargs="+", metavar="KEY", help="tune only these weights")
    parser.add_argument("--min-elo", type=float, default=0, help="both bots rated at least this (default 0)")
    parser.add_argument("--max-gap", type=float, default=200, help="at most this Elo apart (default 200)")
    parser.add_argument("--exclude", nargs="*", default=["random"], metavar="BOT",
                        help="leave out games of these bots (default random)")
    parser.add_argument("--with-live", action="store_true", help="also use the real games from the site")
    parser.add_argument("--skip-opening", type=int, default=4, help="skip the first N positions of a game (default 4)")
    parser.add_argument("--keep-noisy", action="store_true", help="also use positions with a capture or finish available")
    parser.add_argument("--step", type=float, default=1.5, help="first multiplier for a weight (default 1.5)")
    parser.add_argument("--min-step", type=float, default=1.01, help="stop below this step (default 1.01)")
    parser.add_argument("--shrink", type=float, default=0.5, help="keep this fraction of the step after a pass with no change (default 0.5)")
    parser.add_argument("--min-gain", type=float, default=1e-5,
                        help="smallest error drop that counts as better (default 0.00001)")
    parser.add_argument("--db", type=Path, default=DB_PATH, help=f"database (default {DB_PATH.name} in data/)")
    args = parser.parse_args()
    if not 0 < args.shrink < 1:
        parser.error("--shrink must be between 0 and 1")

    path = bot_path(args.bot)
    bot = load_copy(path, "texel")
    evaluate = getattr(bot, args.func, None)
    if not isinstance(getattr(bot, "WHEIGHTS", None), dict) or not callable(evaluate):
        sys.exit(f"{path.name} needs a WHEIGHTS dict and a {args.func}(state) function.")
    if hasattr(bot, "get_map"):
        # distanceMap keeps the maps of one board only; here the boards change all
        # the time, so keep every board's maps (the board objects stay alive in data)
        maps = {}

        def get_map(board, player, movement):
            key = (id(board), player, movement)
            if key not in maps:
                maps[key] = build_map(board, player, movement)
            return maps[key]
        bot.get_map = get_map

    best = dict(bot.WHEIGHTS)
    keys = args.only or list(best)
    unknown = [k for k in keys if k not in best]
    if unknown:
        sys.exit(f"Not in WHEIGHTS: {', '.join(unknown)}. Keys: {', '.join(best)}")

    con = sqlite3.connect(args.db)
    games = select_games(con, args)
    if not games:
        sys.exit("No games match. Lower --min-elo or raise --max-gap, or play games with tournament.py.")
    print(f"{len(games)} games selected")
    train, test = load_data(con, games, args)
    con.close()
    if not train or not test:
        sys.exit("Not enough positions to tune on.")
    print(f"{len(train)} training positions, {len(test)} test positions\n")

    def evals(weights: dict, data: list) -> list[float]:
        bot.WHEIGHTS = weights
        return [evaluate(state) for state, _ in data]

    print("Building the distance maps...", flush=True)
    values = evals(best, train)  # the first pass builds every board's maps
    start = time.time()
    values = evals(best, train)
    print(f"One error computation takes {time.time() - start:.2f} s")
    # The scale is fitted once, for the starting weights, then kept: otherwise
    # making every weight bigger and the scale smaller would change nothing
    k = fit_k(values, train)
    best_error = error_of(values, train, k)
    test_error = error_of(evals(best, test), test, k)
    print(f"Sigmoid scale k = {k:.4f}: an eval of {400 / k:.0f} means Red wins about 91% of the time")
    print(f"Start: training error {best_error:.6f}, test error {test_error:.6f}")
    print(f"WHEIGHTS = {best}\n")

    out = Path(__file__).parent / f"texel_{path.stem}.json"
    step = args.step
    try:
        while step >= args.min_step:
            changed = False
            for key in keys:
                for up in (True, False):
                    improved = False
                    # Keep going in this direction while the error keeps falling
                    while True:
                        challenger = dict(best, **{key: nudge(best[key], step, up)})
                        if challenger[key] == best[key]:
                            break  # too small to change after rounding
                        e = error_of(evals(challenger, train), train, k)
                        # Ignore gains too tiny to matter, or a weight drifts forever on noise
                        if e > best_error - args.min_gain:
                            break
                        print(f"{key:>14} {best[key]:>8} -> {challenger[key]:<8} error {best_error:.6f} -> {e:.6f}",
                              flush=True)
                        best, best_error, improved, changed = challenger, e, True, True
                    if improved:
                        break  # no need to try the other direction
            test_error = error_of(evals(best, test), test, k)
            print(f"  pass at step x{step:.3f} done: training error {best_error:.6f}, test error {test_error:.6f}\n")
            out.write_text(json.dumps({"weights": best, "k": k, "train_error": best_error,
                                       "test_error": test_error}, indent=2) + "\n")
            if not changed:
                step = 1 + (step - 1) * args.shrink
    except KeyboardInterrupt:
        print("\nStopped.")

    print(f"Best after {(time.time() - start) / 60:.1f} min (saved in {out.name}):")
    print(f"WHEIGHTS = {best}")


if __name__ == "__main__":
    main()
