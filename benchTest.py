#!/usr/bin/env python3
"""Play many Traversal games between bots and report the results.

    python3 benchTest.py race 100              # race bot against itself, 100 games
    python3 benchTest.py race 100 --vs random  # race against bot/randomBot.py
    python3 benchTest.py race 5 --watch        # print every move and board

A bot named NAME lives in bot/NAMEBot.py (or bot/NAME.py) and has a
choose_move(state) function returning one of all_legal_moves(state).
Each game uses a fresh random board; with two different bots the colours swap
every game so neither always moves first.
"""

from __future__ import annotations

import argparse
import importlib
import random
import sys
import time
import traceback
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from play import PLAYER_NAMES, Style, describe_move, end_message, render, status
from traversal import (
    GameState,
    all_legal_moves,
    apply_move,
    generate_board,
    load_board,
    new_game,
    pass_turn,
)

BOT_DIR = Path(__file__).parent / "bot"


@dataclass
class GameResult:
    red: str
    blue: str
    winner: int  # 1 or 2, or 0 for a draw
    reason: str
    moves: int
    scores: list[int]
    think_time: dict[int, float]
    bot_moves: dict[int, int]
    error: str | None = None

    def winner_name(self) -> str | None:
        return {1: self.red, 2: self.blue}.get(self.winner)


def load_bot(name: str):
    for module_name in (f"bot.{name}Bot", f"bot.{name}"):
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as e:
            if e.name in (module_name, "bot"):
                continue
            raise  # the bot file exists but imports something missing
        if not callable(getattr(module, "choose_move", None)):
            sys.exit(f"{module.__file__} has no choose_move(state) function.")
        return module
    available = sorted(p.stem.removesuffix("Bot") for p in BOT_DIR.glob("*.py") if p.stem != "__init__")
    sys.exit(f"No bot named '{name}'. Available: {', '.join(available) or 'none'}")


def end_reason(state: GameState) -> str:
    if state.draw_reason:
        return state.draw_reason
    if state.win_reason:
        return state.win_reason
    first = state.piece(state.first_to_finish) if state.first_to_finish else None
    if first and first.type == "sentinel" and len(state.finished_pieces) == 1:
        return "sentinel_first"
    if state.victory_type == "total_domination":
        return "wipeout"
    if state.winner == 0:
        return "equal_score"
    return "two_finished"


def play_game(red_name: str, blue_name: str, bots: dict, board: list[list[int]],
              watch: bool, style: Style) -> GameResult:
    names = {1: red_name, 2: blue_name}
    state = new_game(board)
    think_time = {1: 0.0, 2: 0.0}
    bot_moves = {1: 0, 2: 0}

    def result(winner: int, reason: str, error: str | None = None) -> GameResult:
        return GameResult(red_name, blue_name, winner, reason, state.move_count, state.scores,
                          think_time, bot_moves, error)

    if watch:
        print(render(state, style))
    while not state.game_over:
        player = state.current_turn
        legal = all_legal_moves(state)
        if not legal:
            state = pass_turn(state)
            if watch:
                print(f"{PLAYER_NAMES[player]} has no legal move and passes.")
            continue

        start = time.perf_counter()
        try:
            # A copy, so a bot that experiments on the state can't change the real game
            move = bots[names[player]].choose_move(state.copy())
        except Exception:
            return result(3 - player, "forfeit_error", traceback.format_exc())
        think_time[player] += time.perf_counter() - start
        bot_moves[player] += 1

        if move not in legal:
            return result(3 - player, "forfeit_illegal_move",
                          f"{names[player]} ({PLAYER_NAMES[player]}) returned an illegal move: {move!r}")

        after = apply_move(state, move.piece_id, move.to_row, move.to_col)
        if watch:
            print(f"{names[player]}: {describe_move(state, after, move)}")
            print(render(after, style))
            print(status(after, style))
        state = after

    if watch:
        print(style.bold(end_message(state)) + "\n")
    return result(state.winner, end_reason(state))


def summarize(results: list[GameResult], bot_names: list[str], seed: int) -> None:
    n = len(results)
    games = "game" if n == 1 else "games"
    print()
    if len(bot_names) == 1:
        name = bot_names[0]
        outcomes = Counter(r.winner for r in results)
        print(f"{name} vs itself — {n} {games}")
        print(f"  Red wins   {outcomes[1]:>5}  ({100 * outcomes[1] / n:.0f}%)")
        print(f"  Blue wins  {outcomes[2]:>5}  ({100 * outcomes[2] / n:.0f}%)")
        print(f"  Draws      {outcomes[0]:>5}  ({100 * outcomes[0] / n:.0f}%)")
    else:
        print(f"{bot_names[0]} vs {bot_names[1]} — {n} {games}, colours alternating")
        width = max(len(b) for b in bot_names)
        for name in bot_names:
            wins = [r for r in results if r.winner_name() == name]
            as_red = sum(1 for r in wins if r.winner == 1)
            print(f"  {name:<{width}}  wins {len(wins):>5}  ({100 * len(wins) / n:.0f}%)"
                  f"   as Red {as_red}, as Blue {len(wins) - as_red}")
        draws = sum(1 for r in results if r.winner == 0)
        print(f"  {'draws':<{width}}       {draws:>5}  ({100 * draws / n:.0f}%)")

    reasons = Counter(r.reason for r in results)
    print("Endings: " + ", ".join(f"{reason} {count}" for reason, count in reasons.most_common()))
    print(f"Average game length: {sum(r.moves for r in results) / n:.1f} moves")

    for name in bot_names:
        total_time = sum(r.think_time[p] for r in results for p in (1, 2) if (r.red, r.blue)[p - 1] == name)
        total_moves = sum(r.bot_moves[p] for r in results for p in (1, 2) if (r.red, r.blue)[p - 1] == name)
        if total_moves:
            print(f"Think time {name}: {1000 * total_time / total_moves:.2f} ms per move")

    errors = [r for r in results if r.error]
    if errors:
        print(f"\n{len(errors)} {'game' if len(errors) == 1 else 'games'} forfeited by a bot error. First one:")
        print(errors[0].error)
    print(f"\nBoards from seed {seed}; add --seed {seed} to replay the same games.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Play Traversal bots against each other and report the results.")
    parser.add_argument("bot", help="bot name, e.g. 'race' for bot/raceBot.py")
    parser.add_argument("games", type=int, nargs="?", default=10, help="number of games (default 10)")
    parser.add_argument("--vs", metavar="BOT", help="opponent bot (default: the same bot)")
    parser.add_argument("--seed", type=int, help="seed for the boards, to replay the same games")
    parser.add_argument("--board", help="use this board file for every game instead of random boards")
    parser.add_argument("--pushes", type=int, default=400, help="how rugged the random boards are (default 400)")
    parser.add_argument("--watch", action="store_true", help="print every move and board")
    parser.add_argument("--quiet", action="store_true", help="only print the summary")
    parser.add_argument("--no-color", action="store_true", help="plain text output")
    args = parser.parse_args()
    if args.games < 1:
        parser.error("games must be at least 1")

    bot_names = [args.bot] if not args.vs or args.vs == args.bot else [args.bot, args.vs]
    bots = {name: load_bot(name) for name in bot_names}
    style = Style(color=not args.no_color and sys.stdout.isatty())
    seed = args.seed if args.seed is not None else random.randrange(1_000_000)
    try:
        fixed_board = load_board(args.board) if args.board else None
    except (OSError, ValueError) as e:
        sys.exit(f"Can't use that board: {e}")

    results = []
    for i in range(args.games):
        board = fixed_board or generate_board(pushes=args.pushes, seed=seed + i)
        # With two bots, swap colours every game
        red, blue = (bot_names[i % 2], bot_names[1 - i % 2]) if len(bot_names) == 2 else (bot_names[0],) * 2
        r = play_game(red, blue, bots, board, args.watch, style)
        results.append(r)
        if not args.quiet:
            outcome = "draw" if r.winner == 0 else f"{r.winner_name()} ({PLAYER_NAMES[r.winner]}) wins"
            print(f"game {i + 1:>4}  {red} (Red) vs {blue} (Blue): {outcome:<24} "
                  f"{r.reason:<24} {r.scores[0]}:{r.scores[1]}  {r.moves} moves")

    summarize(results, bot_names, seed)


if __name__ == "__main__":
    main()
