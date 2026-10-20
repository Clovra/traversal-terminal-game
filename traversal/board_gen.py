"""Terrain boards: random generation, loading and validation."""

from __future__ import annotations

import json
import random
from pathlib import Path

MAX_STEP = 2  # adjacent squares may differ by at most this much


def generate_board(size: int = 10, pushes: int = 400, max_height: int = 5, seed: int | None = None) -> list[list[int]]:
    """Random terrain made by nudging squares up or down one unit at a time.

    Every nudge is mirrored on the square rotated 180 degrees, so both players
    see the same terrain from their own side.
    """
    rng = random.Random(seed)
    board = [[0] * size for _ in range(size)]
    done = attempts = 0
    while done < pushes and attempts < pushes * 100:
        attempts += 1
        r, c = rng.randrange(size), rng.randrange(size)
        step = rng.choice((-1, 1))
        cells = {(r, c), (size - 1 - r, size - 1 - c)}
        for i, j in cells:
            board[i][j] += step
        if all(abs(board[i][j]) <= max_height and _square_ok(board, i, j) for i, j in cells):
            done += 1
        else:
            for i, j in cells:
                board[i][j] -= step
    return board


def _square_ok(board: list[list[int]], r: int, c: int) -> bool:
    n = len(board)
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        i, j = r + dr, c + dc
        if 0 <= i < n and 0 <= j < len(board[i]) and abs(board[r][c] - board[i][j]) > MAX_STEP:
            return False
    return True


def validate_board(board: list[list[int]]) -> None:
    """Raise ValueError if the board isn't a square grid of legal terrain."""
    n = len(board)
    if n < 4 or any(len(row) != n for row in board):
        raise ValueError("board must be a square grid at least 4x4")
    for r in range(n):
        for c in range(n):
            if not isinstance(board[r][c], int):
                raise ValueError(f"height at row {r}, col {c} is not an integer")
            if not _square_ok(board, r, c):
                raise ValueError(f"square at row {r}, col {c} differs from a neighbour by more than {MAX_STEP}")


def load_board(path: str | Path) -> list[list[int]]:
    """Load a board from JSON (a list of rows) or plain text (one row of heights per line).

    Rows are listed top to bottom, so the first row is the one Blue starts on.
    """
    text = Path(path).read_text()
    try:
        board = json.loads(text)
    except json.JSONDecodeError:
        board = [[int(float(h)) for h in line.replace(",", " ").strip("[] \t").split()]
                 for line in text.splitlines() if line.strip("[] \t")]
    validate_board(board)
    return board
