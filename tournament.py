#!/usr/bin/env python3
"""Play bots against each other, store every game, and rate the bots with Elo.

    python3 tournament.py V5 V6 V7 random          # round-robin: every pair plays
    python3 tournament.py V8 --vs V6 V7            # gauntlet: V8 against V6 and V7 only
    python3 tournament.py                          # no games, just refit and show the ratings

Every game goes into data/games.db (game_type 'bot') with all its positions, so
the games are also training data. A bot is stored as name@hash of its file,
e.g. V7@3fa2c1, so changing a bot's file starts a fresh rating instead of mixing
the old and new versions. --depth adds /d<depth> to bots that have a DEPTH.

After the games, the ratings are refitted from every bot game in the database
(not only this run's) and saved in the bots table. The anchor bot (random by
default) is fixed at 0, so never edit bot/random.py.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
import random
import sqlite3
import sys
import time
import traceback
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from benchTest import end_reason, load_bot
from bot.dataIntegration import DB_PATH, SCHEMA, state_to_json
from traversal import all_legal_moves, apply_move, generate_board, new_game, pass_turn
from tune import bot_path

BOTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS bots (
    name   TEXT PRIMARY KEY,   -- name@hash, e.g. V7@3fa2c1
    elo    REAL,
    error  REAL,               -- 95% margin: the true Elo is within elo +- error
    games  INTEGER,            -- against other bots; self-play doesn't count
    wins   INTEGER,
    draws  INTEGER,
    losses INTEGER
);
"""


def identity(name: str, depth: int | None) -> str:
    digest = hashlib.sha1(bot_path(name).read_bytes()).hexdigest()[:6]
    forced = depth is not None and hasattr(load_bot(name), "DEPTH")
    return f"{name}@{digest}" + (f"/d{depth}" if forced else "")


# --- worker side ---

_bots: dict[str, object] = {}
_depth: int | None = None


def _init_worker(depth: int | None) -> None:
    global _depth
    sys.stdout = open(os.devnull, "w")  # hide the bots' prints
    _depth = depth


def _bot(name: str):
    if name not in _bots:
        module = load_bot(name)
        if _depth is not None and hasattr(module, "DEPTH"):
            module.DEPTH = _depth
        _bots[name] = module
    return _bots[name]


def _play(task: tuple) -> dict:
    """Play one game, recording every position and the move played from it."""
    red, blue, red_id, blue_id, board_seed, pushes, random_moves = task
    board = generate_board(pushes=pushes, seed=board_seed)
    rng = random.Random(board_seed)  # same opening for both colour orders on this board
    names = {1: red, 2: blue}
    game = {"red": red_id, "blue": blue_id, "board": board, "error": None}
    state = new_game(board)
    states, moves = [], []
    start = time.perf_counter()
    while not state.game_over:
        legal = all_legal_moves(state)
        states.append(state_to_json(state))
        if not legal:
            moves.append({"pass": True})
            state = pass_turn(state)
            continue
        if len(moves) < random_moves:
            move = rng.choice(legal)
        else:
            player = names[state.current_turn]
            try:
                move = _bot(player).choose_move(state.copy())
            except Exception:
                game["error"] = f"{player} crashed:\n{traceback.format_exc()}"
                return game
            if move not in legal:
                game["error"] = f"{player} returned an illegal move: {move!r}"
                return game
        moves.append({"piece_id": move.piece_id, "to_row": move.to_row, "to_col": move.to_col})
        state = apply_move(state, move.piece_id, move.to_row, move.to_col)
    states.append(state_to_json(state))
    moves.append(None)
    game.update(winner=state.winner, reason=end_reason(state), move_count=state.move_count,
                states=states, moves=moves, seconds=time.perf_counter() - start)
    return game


# --- main side ---

def store(con: sqlite3.Connection, game: dict) -> None:
    game_id = str(uuid.uuid4())
    with con:  # one transaction: the game and all its positions, or nothing
        con.execute("INSERT INTO games VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
            game_id, game["red"], game["blue"], None, None, game["winner"], game["reason"],
            "bot", None, game["move_count"], json.dumps(game["board"]),
        ))
        con.executemany("INSERT INTO positions VALUES (?, ?, ?, ?)", [
            (game_id, ply, state, json.dumps(move) if move else None)
            for ply, (state, move) in enumerate(zip(game["states"], game["moves"]))
        ])


def fit_elo(con: sqlite3.Connection, anchor: str) -> list[tuple]:
    """Refit every bot's Elo from all bot games and save them in the bots table.

    Bradley-Terry fit: the ratings under which all the results are most likely,
    whatever order the games were played in."""
    results = {}  # (a, b) with a < b -> [games, a's score], a draw counting 1/2
    record = {}   # name -> [wins, draws, losses]
    for p1, p2, winner in con.execute("SELECT player1, player2, winner FROM games WHERE game_type = 'bot'"):
        if p1 == p2:
            continue  # self-play says nothing about strength
        s1 = {1: 1.0, 2: 0.0, 0: 0.5}[winner]
        for name, s in ((p1, s1), (p2, 1 - s1)):
            r = record.setdefault(name, [0, 0, 0])
            r[0 if s == 1 else 1 if s == 0.5 else 2] += 1
        a, b, sa = (p1, p2, s1) if p1 < p2 else (p2, p1, 1 - s1)
        pair = results.setdefault((a, b), [0, 0.0])
        pair[0] += 1
        pair[1] += sa
    if not results:
        return []

    names = sorted(record)
    opponents = {x: set() for x in names}
    games, score = {}, {x: 0.0 for x in names}
    for (a, b), (n, sa) in results.items():
        opponents[a].add(b)
        opponents[b].add(a)
        # One extra virtual draw per pair, so a bot that won or lost every game
        # gets a finite rating instead of infinity
        games[(a, b)] = games[(b, a)] = n + 1
        score[a] += sa + 0.5
        score[b] += n - sa + 0.5

    # Minorization-maximization: gamma = 10^(elo/400), repeat until stable
    gamma = {x: 1.0 for x in names}
    for _ in range(100_000):
        new = {i: score[i] / sum(games[(i, j)] / (gamma[i] + gamma[j]) for j in opponents[i]) for i in names}
        mean = math.exp(sum(math.log(v) for v in new.values()) / len(new))
        new = {i: v / mean for i, v in new.items()}
        done = max(abs(math.log(new[i] / gamma[i])) for i in names) < 1e-12
        gamma = new
        if done:
            break
    elo = {i: 400 * math.log10(gamma[i]) for i in names}

    # Margin from how many games a bot played and how close they were
    error = {}
    for i in names:
        info = 0.0
        for j in opponents[i]:
            p = 1 / (1 + 10 ** ((elo[j] - elo[i]) / 400))
            info += results[tuple(sorted((i, j)))][0] * p * (1 - p)
        error[i] = 1.96 * 400 / math.log(10) / math.sqrt(info) if info else math.inf

    anchors = [x for x in names if x.split("@")[0] == anchor]
    if anchors:
        zero = elo[max(anchors, key=lambda x: sum(record[x]))]
    else:
        zero = 0.0
        print(f"Note: no {anchor} games yet, so the ratings are only relative to each other.")
    elo = {i: v - zero for i, v in elo.items()}

    # Bots that never met, even through other bots, can't be compared
    seen, todo = {names[0]}, [names[0]]
    while todo:
        for j in opponents[todo.pop()] - seen:
            seen.add(j)
            todo.append(j)
    if len(seen) < len(names):
        print(f"Warning: these bots are not linked by games to {names[0]}, so their ratings "
              f"can't be compared with it: {', '.join(sorted(set(names) - seen))}")

    rows = sorted(((i, elo[i], error[i], sum(record[i]), *record[i]) for i in names), key=lambda r: -r[1])
    with con:
        con.execute("DELETE FROM bots")
        con.executemany("INSERT INTO bots VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
    return rows


def print_ratings(rows: list[tuple]) -> None:
    if not rows:
        print("No bot games in the database yet.")
        return
    width = max(len(r[0]) for r in rows)
    print(f"{'':>3} {'bot':<{width}}  {'elo':>6}  {'95%':>5}  {'games':>5}  {'W-D-L':>11}  score")
    for rank, (name, elo, error, games, w, d, l) in enumerate(rows, 1):
        print(f"{rank:>3} {name:<{width}}  {elo:>6.0f}  ±{error:>4.0f}  {games:>5}  "
              f"{f'{w}-{d}-{l}':>11}  {100 * (w + d / 2) / games:4.0f}%")


def main() -> None:
    parser = argparse.ArgumentParser(description="Play bots against each other and rate them with Elo.")
    parser.add_argument("bots", nargs="*", help="bot names, e.g. V5 V6 random; none = just show the ratings")
    parser.add_argument("--vs", nargs="+", metavar="BOT", help="gauntlet: play the bots only against these")
    parser.add_argument("--games", type=int, default=20, help="games per pair, even (default 20)")
    parser.add_argument("--depth", type=int, help="force this DEPTH on every bot that has one")
    parser.add_argument("--random-moves", type=int, default=2,
                        help="random moves at the start of each game, for variety (default 2)")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1),
                        help="games played at once (default: CPUs - 1)")
    parser.add_argument("--seed", type=int, help="seed for the boards (default: random)")
    parser.add_argument("--pushes", type=int, default=400, help="how rugged the boards are (default 400)")
    parser.add_argument("--anchor", default="random", help="bot fixed at Elo 0 (default random)")
    parser.add_argument("--db", type=Path, default=DB_PATH, help=f"database (default {DB_PATH.name} in data/)")
    args = parser.parse_args()
    args.games += args.games % 2  # every board is played with both colours

    con = sqlite3.connect(args.db)
    con.executescript(SCHEMA + BOTS_SCHEMA)

    if args.bots:
        if args.vs:
            pairs = [(a, b) for a in args.bots for b in args.vs if a != b]
        else:
            pairs = list(itertools.combinations(dict.fromkeys(args.bots), 2))
        if not pairs:
            parser.error("need at least two different bots")
        ids = {name: identity(name, args.depth) for pair in pairs for name in pair}
        seed = args.seed if args.seed is not None else random.randrange(1_000_000)
        # Every pair plays on the same boards, each board twice with the colours swapped
        tasks = []
        for a, b in pairs:
            for i in range(args.games):
                red, blue = (a, b) if i % 2 == 0 else (b, a)
                tasks.append((red, blue, ids[red], ids[blue], seed + i // 2, args.pushes, args.random_moves))

        print(f"{len(pairs)} pairs x {args.games} games = {len(tasks)} games, {args.workers} at once, "
              f"boards from seed {seed}")
        print("Bots: " + ", ".join(ids.values()) + "\n")
        errors = 0
        with ProcessPoolExecutor(args.workers, initializer=_init_worker, initargs=(args.depth,)) as pool:
            futures = [pool.submit(_play, t) for t in tasks]
            try:
                for done, future in enumerate(as_completed(futures), 1):
                    g = future.result()
                    if g["error"]:
                        errors += 1
                        print(f"{done:>5}/{len(tasks)}  {g['red']} vs {g['blue']}: not stored, {g['error']}")
                        continue
                    store(con, g)
                    outcome = {1: f"{g['red']} wins", 2: f"{g['blue']} wins", 0: "draw"}[g["winner"]]
                    print(f"{done:>5}/{len(tasks)}  {g['red']} (Red) vs {g['blue']} (Blue): {outcome:<22} "
                          f"{g['reason']:<16} {g['move_count']:>3} moves  {g['seconds']:6.1f} s", flush=True)
            except KeyboardInterrupt:
                pool.shutdown(cancel_futures=True)
                print("\nStopped; the finished games are stored.")
        if errors:
            print(f"\n{errors} games not stored because a bot crashed or cheated.")
        print()

    print_ratings(fit_elo(con, args.anchor))
    con.close()


if __name__ == "__main__":
    main()
