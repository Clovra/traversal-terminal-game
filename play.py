#!/usr/bin/env python3
"""Two-player Traversal in the terminal (hotseat).

    python3 play.py                 # random board
    python3 play.py --seed 7        # reproducible random board
    python3 play.py --board my.txt  # board from a file (JSON or rows of heights)

Squares are named like chess: columns A-J left to right, rows 1-10 bottom to
top. Red starts on row 1 and exits off the top; Blue starts on row 10 and
exits off the bottom.
"""

from __future__ import annotations

import argparse
import re
import sys

from traversal import (
    MOVE_LIMIT,
    GameState,
    IllegalMove,
    Move,
    all_legal_moves,
    apply_move,
    generate_board,
    legal_moves,
    load_board,
    new_game,
    pass_turn,
)

from bot.raceBot import choose_move

PLAYER_NAMES = {1: "Red", 2: "Blue"}
PIECE_LETTERS = {"explorer": "E", "vanguard": "V", "sentinel": "S"}
SPECIAL_NAMES = {"diagonal": "diagonal step", "leap": "leap"}

HELP = """\
Commands
  c1          select the piece on C1 and show where it can go
  c1 c4       move the piece on C1 to C4 (attacking if an enemy is there)
  c10 off     finish: step the piece off its goal edge ("off at d" picks the column if there's a choice)
  moves       list every legal move
  undo        take back the last move
  pass        skip your turn (only when you have no legal move)
  help        show this help
  quit        leave the game

Board
  Each square shows its piece (Red UPPERCASE, Blue lowercase, · for empty) and its height.
  E = Explorer (move 5, strength 1)   V = Vanguard (4, 2)   S = Sentinel (3, 3)
  After selecting a piece:  * reachable square   x capturable enemy   ^/v finishing column
  Cost is the Movement a path uses. Explorer diagonal steps and leaps ignore height and use the whole turn.

Rules in brief (full text in RULES.md)
  A step costs |height difference| + 1. No passing through pieces.
  Attack = strength, +1 from higher ground / -1 from lower, + base strength of your
  other pieces next to the target (+1 for a Vanguard whose cheapest path is exactly 4).
  Defense = strength + 1 per friendly piece next to the defender. Attack must be >= defense.
  Explorers may instead step 1 diagonally or leap 2 straight, ignoring height.
  Game ends when two pieces in total have finished; the higher score wins.
  A Sentinel finishing first wins instantly. 200-move limit."""


class Style:
    def __init__(self, color: bool):
        self.color = color

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.color else text

    def player(self, player: int, text: str) -> str:
        return self._wrap("1;31" if player == 1 else "1;34", text)

    def height(self, h: int, text: str) -> str:
        if h > 0:
            return self._wrap("33", text)
        if h < 0:
            return self._wrap("36", text)
        return self._wrap("2", text)

    def mark(self, kind: str, text: str) -> str:
        return self._wrap({"move": "1;32", "attack": "1;35", "select": "1;33"}[kind], text)

    def bold(self, text: str) -> str:
        return self._wrap("1", text)


def square_name(row: int, col: int, size: int) -> str:
    return f"{chr(ord('A') + col)}{size - row}"


def piece_label(state: GameState, piece_id: str) -> str:
    p = state.piece(piece_id)
    return f"{PLAYER_NAMES[p.player]} {p.type.capitalize()}"


def parse_square(text: str, size: int) -> tuple[int, int] | None:
    """Turn 'c4' into (row, col). Accepts the rows just past either edge for finishing moves."""
    m = re.fullmatch(r"([a-z])(\d{1,2})", text.lower())
    if not m:
        return None
    col = ord(m.group(1)) - ord("a")
    rank = int(m.group(2))
    if col >= size or not 0 <= rank <= size + 1:
        return None
    return size - rank, col


def render(state: GameState, style: Style, selected: tuple[int, int] | None = None,
           options: list[Move] = ()) -> str:
    size = state.size
    targets = {(m.to_row, m.to_col): m for m in options}
    exit_cols = {m.to_col for m in options if m.finishes}

    def exit_line(player: int, arrow: str) -> str:
        cells = []
        for c in range(size):
            show = c in exit_cols and options and state.current_turn == player
            cells.append(style.mark("move", f"  {arrow}   ") if show else "      ")
        return "     " + "".join(cells)

    lines = ["     " + "".join(f"  {chr(ord('A') + c)}   " for c in range(size))]
    lines.append(exit_line(1, "^") + style.player(1, "   Red exits ↑"))
    for r in range(size):
        cells = []
        for c in range(size):
            h = state.board[r][c]
            p = state.piece_at(r, c)
            if p:
                letter = PIECE_LETTERS[p.type]
                token = style.player(p.player, letter if p.player == 1 else letter.lower())
            else:
                token = "·"
            mark = " "
            if selected == (r, c):
                mark = style.mark("select", "@")
            elif (r, c) in targets:
                move = targets[(r, c)]
                mark = style.mark("attack", "x") if move.is_attack else style.mark("move", "*")
            cells.append(f" {token}{style.height(h, f'{h:>+3d}' if h else '  0')}{mark}")
        lines.append(f" {size - r:>2}  " + "".join(cells) + f"  {size - r}")
    lines.append(exit_line(2, "v") + style.player(2, "   Blue exits ↓"))
    lines.append("     " + "".join(f"  {chr(ord('A') + c)}   " for c in range(size)))
    return "\n".join(lines)


def status(state: GameState, style: Style) -> str:
    def captured(player: int) -> int:
        return sum(1 for p in state.pieces if p.player == player and p.captured)

    finished = ", ".join(piece_label(state, pid) for pid in state.finished_pieces) or "none"
    return (
        f"Move {state.move_count + (not state.game_over)}/{MOVE_LIMIT}   "
        f"Score {style.player(1, 'Red')} {state.scores[0]} : {state.scores[1]} {style.player(2, 'Blue')}   "
        f"Lost: Red {captured(1)}, Blue {captured(2)}   Finished: {finished}"
    )


def describe_option(state: GameState, move: Move) -> str:
    size = state.size
    how = SPECIAL_NAMES.get(move.special)
    if move.finishes:
        points = state.piece(move.piece_id).strength
        via = f", {how}" if how else ""
        return f"off at {chr(ord('A') + move.to_col)} (finish{via}, +{points})"
    where = square_name(move.to_row, move.to_col, size)
    if move.is_attack:
        target = state.piece(move.captured_id)
        via = f", {how}" if how else ""
        return f"{where} captures {target.type} ({move.attack_strength} vs {move.defense_strength}{via})"
    return f"{where} ({how})" if how else f"{where} (cost {move.cost})"


def describe_move(before: GameState, after: GameState, move: Move) -> str:
    size = before.size
    piece = before.piece(move.piece_id)
    text = f"{piece_label(before, move.piece_id)} {square_name(piece.row, piece.col, size)}"
    if move.finishes:
        return text + f" finishes (+{piece.strength})"
    text += f" → {square_name(move.to_row, move.to_col, size)}"
    if move.special:
        text += f" ({SPECIAL_NAMES[move.special]})"
    if move.is_attack:
        text += f", capturing the {piece_label(before, move.captured_id)}"
    return text


def end_message(state: GameState) -> str:
    if state.draw_reason == "threefold_repetition":
        return "Draw by threefold repetition."
    if state.draw_reason == "move_limit":
        return f"Draw: the {MOVE_LIMIT}-move limit was reached with nothing to separate the players."
    if state.winner == 0:
        return "Draw on equal scores."
    name = PLAYER_NAMES[state.winner]
    if state.win_reason == "move_limit_score":
        return f"{name} wins on score at the {MOVE_LIMIT}-move limit."
    if state.win_reason == "move_limit_advancement":
        return f"{name} wins at the {MOVE_LIMIT}-move limit: their piece was closest to finishing."
    first = state.piece(state.first_to_finish) if state.first_to_finish else None
    if first and first.type == "sentinel" and len(state.finished_pieces) == 1:
        return f"{name} wins instantly: their Sentinel finished first!"
    if state.victory_type == "total_domination":
        return f"{name} wins: the opponent has no pieces left."
    text = f"{name} wins after two pieces finished."
    if state.victory_type == "perfect_game":
        text += " A perfect game!"
    return text


def find_move(state: GameState, piece_id: str, target: str) -> Move | str:
    """Match the typed destination against the piece's legal moves; returns an error string on failure."""
    options = legal_moves(state, piece_id)
    words = target.split()
    if words and words[0] == "off":
        # "off", "off j" or "off at j", matching how the options list shows finishes
        column = words[-1] if len(words) > 1 else None
        finishes = [m for m in options if m.finishes]
        if column is not None:
            finishes = [m for m in finishes if chr(ord("a") + m.to_col) == column]
        if len(finishes) == 1:
            return finishes[0]
        if not finishes:
            where = f" at {column.upper()}" if column else ""
            return f"That piece can't finish{where} this turn."
        columns = " or ".join(chr(ord("A") + m.to_col) for m in finishes)
        return f"That piece can finish at {columns}; type e.g. 'off at {chr(ord('a') + finishes[0].to_col)}'."
    square = parse_square(target, state.size)
    if square is None:
        return f"'{target}' isn't a square."
    for m in options:
        if (m.to_row, m.to_col) == square:
            return m
    return f"That piece can't reach {target.upper()}."


    #def choose_move(state: GameState) -> Move:
    #""" the bot action"""
    #list = all_legal_moves(state)
    #best = list[0]
    #for i in list:
    #    if i.to_row > best.to_row:
    #        best = i

    #return best






def main() -> None:
    parser = argparse.ArgumentParser(description="Play Traversal against another person in the terminal.")
    parser.add_argument("--board", help="board file: JSON list of rows, or one row of heights per line (top row first)")
    parser.add_argument("--seed", type=int, help="seed for the random board")
    parser.add_argument("--pushes", type=int, default=400, help="how rugged the random board is (default 400)")
    parser.add_argument("--no-color", action="store_true", help="plain text output")
    args = parser.parse_args()
    BOT_PLAY = 2
    style = Style(color=not args.no_color and sys.stdout.isatty())
    try:
        board = load_board(args.board) if args.board else generate_board(pushes=args.pushes, seed=args.seed)
    except (OSError, ValueError) as e:
        sys.exit(f"Can't use that board: {e}")

    state = new_game(board)
    history: list[GameState] = []
    print(style.bold("Traversal") + " — type 'help' for commands.\n")
    show_board = True

    while not state.game_over:
        player = state.current_turn
        name = PLAYER_NAMES[player]
        if show_board:
            print(render(state, style))
            print(status(state, style))
        show_board = False

        if player == BOT_PLAY :
            move = choose_move(state)
            after = apply_move(state, move.piece_id, move.to_row, move.to_col)
            print(describe_move(state, after, move))
            history.append(state)
            state = after
            show_board = True
            continue

        try:
            words = input(style.player(player, f"{name}") + " > ").strip().lower().split()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not words:
            continue
        command = words[0]

        if command in ("q", "quit", "exit"):
            return
        if command in ("h", "help", "?"):
            print(HELP)
            continue
        if command in ("u", "undo"):
            if history:
                state = history.pop()
                print("Took back the last move.")
                show_board = True
            else:
                print("Nothing to undo.")
            continue
        if command in ("m", "moves"):
            moves = all_legal_moves(state)
            if not moves:
                print("No legal moves: type 'pass'.")
            for p in state.active_pieces(player):
                options = [m for m in moves if m.piece_id == p.id]
                if options:
                    label = f"{PIECE_LETTERS[p.type]} {square_name(p.row, p.col, state.size)}"
                    print(f"  {label}: " + ", ".join(describe_option(state, m) for m in options))
            continue
        if command == "pass":
            if all_legal_moves(state):
                print("You have legal moves, so you can't pass.")
                continue
            history.append(state)
            state = pass_turn(state)
            print(f"{name} passes.")
            show_board = True
            continue

        square = parse_square(command, state.size)
        piece = state.piece_at(*square) if square else None
        if piece is None or piece.player != player:
            print("Pick one of your own pieces by its square (e.g. c1), or type 'help'.")
            continue
        options = legal_moves(state, piece.id)
        if not options:
            print("That piece has no legal moves.")
            continue

        if len(words) >= 2:
            target = " ".join(words[1:])
        else:
            print(render(state, style, selected=square, options=options))
            print("Options: " + ", ".join(describe_option(state, m) for m in options))
            try:
                target = input("  to (blank to cancel) > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if not target:
                show_board = True
                continue

        move = find_move(state, piece.id, target)
        if isinstance(move, str):
            print(move)
            continue
        try:
            after = apply_move(state, move.piece_id, move.to_row, move.to_col)
        except IllegalMove as e:
            print(e)
            continue
        print(describe_move(state, after, move))
        history.append(state)
        state = after
        show_board = True

    print(render(state, style))
    print(status(state, style))
    print(style.bold(end_message(state)))


if __name__ == "__main__":
    main()
