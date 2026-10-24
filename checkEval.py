#!/usr/bin/env python3
"""Check that a bot's evaluation treats Red and Blue the same way.

    python3 checkEval.py V5                  # checks evaluation() in bot/V5Bot.py
    python3 checkEval.py V5 --func test_eval
    python3 checkEval.py V5 --positions 2000

Boards are symmetric under a 180-degree turn, so every position has a mirror
image: turn the board around and swap the colours. A fair evaluation gives the
mirror exactly the negative value. Also checks that the starting position is 0
and that the evaluation doesn't change the state it is given.
"""

from __future__ import annotations

import argparse
import random
import statistics
import sys
from dataclasses import replace

from benchTest import load_bot
from play import Style, render
from traversal import GameState, all_legal_moves, apply_move, generate_board, new_game


def mirror(state: GameState) -> GameState:
    """The same position turned 180 degrees with Red and Blue swapped."""
    n = state.size

    def rename(piece_id: str | None) -> str | None:
        if piece_id is None:
            return None
        player, col = piece_id[1:].split("_")
        return f"p{3 - int(player)}_{n - 1 - int(col)}"

    # Keep each side's pieces in the same order, with the other side's pieces first
    ordered = [p for p in state.pieces if p.player == 2] + [p for p in state.pieces if p.player == 1]
    pieces = [replace(p, id=rename(p.id), player=3 - p.player, row=n - 1 - p.row, col=n - 1 - p.col)
              for p in ordered]
    return replace(
        state,
        board=[row[::-1] for row in state.board[::-1]],
        pieces=pieces,
        current_turn=3 - state.current_turn,
        finished_pieces=[rename(i) for i in state.finished_pieces],
        first_to_finish=rename(state.first_to_finish),
        winner={1: 2, 2: 1}.get(state.winner, state.winner),
        scores=[state.scores[1], state.scores[0]],
        position_history=[],
    )


def random_positions(count: int, seed: int):
    """Positions from random games, from the opening to game over."""
    rng = random.Random(seed)
    for i in range(count):
        state = new_game(generate_board(seed=seed + i))
        for _ in range(rng.randrange(0, 60)):
            moves = all_legal_moves(state)
            if state.game_over or not moves:
                break
            m = rng.choice(moves)
            state = apply_move(state, m.piece_id, m.to_row, m.to_col)
        yield state


def main() -> None:
    parser = argparse.ArgumentParser(description="Check that a bot's evaluation is fair to both colours.")
    parser.add_argument("bot", help="bot name, e.g. 'V5' for bot/V5Bot.py")
    parser.add_argument("--func", default="evaluation", help="evaluation function name (default evaluation)")
    parser.add_argument("--positions", type=int, default=500, help="random positions to test (default 500)")
    parser.add_argument("--seed", type=int, default=1, help="seed for the positions (default 1)")
    parser.add_argument("--show", type=int, default=2, help="failing positions to print (default 2)")
    args = parser.parse_args()

    bot = load_bot(args.bot)
    evaluate = getattr(bot, args.func, None)
    if not callable(evaluate):
        sys.exit(f"{bot.__file__} has no function {args.func}(state)")
    style = Style(color=sys.stdout.isatty())
    problems = 0

    starts = [evaluate(new_game(generate_board(seed=args.seed + i))) for i in range(10)]
    if any(v != 0 for v in starts):
        problems += 1
        print(f"✗ Starting position isn't 0 on every board: {starts}")
    else:
        print("✓ Starting position is 0")

    values, unfair, changed = [], [], 0
    for state in random_positions(args.positions, args.seed):
        before = state.copy()
        value = evaluate(state)
        if state != before:
            changed += 1
        mirrored = evaluate(mirror(before))
        if not before.game_over:
            values.append(value)
        if abs(value + mirrored) > 1e-9:
            unfair.append((before, value, mirrored))

    if changed:
        problems += 1
        print(f"✗ {args.func} changed the state it was given in {changed} positions; "
              "use state.copy() or apply_move instead of changing pieces directly")
    else:
        print("✓ The state is left unchanged")

    if unfair:
        problems += 1
        print(f"✗ {len(unfair)} of {args.positions} positions aren't the negative of their mirror image")
        for state, value, mirrored in unfair[:args.show]:
            print(f"\n  eval {value}, mirror {mirrored} (should be {-value}):")
            print(render(state, style))
    else:
        print(f"✓ All {args.positions} positions are the negative of their mirror image")

    if values:
        print(f"\nValues in unfinished positions: min {min(values)}, median {statistics.median(values)}, "
              f"max {max(values)}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
