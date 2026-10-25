"""Import real games exported from traversalgame.com into a SQLite database.

    python3 -m bot.dataIntegration          # run from integration/, imports data/*.json

Each game is replayed with the engine, so every position it went through can be
stored and loaded back as a GameState. Two tables in data/games.db:

    games      one row per game: players, ratings, winner, board
    positions  one row per position: the state before move `ply`, the move played

A game already in the database is skipped, so it's safe to run again after
adding new files to data/.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from traversal import GameState, IllegalMove, Piece, apply_move, new_game

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "games.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    game_id       TEXT PRIMARY KEY,
    player1       TEXT,
    player2       TEXT,
    rating1       INTEGER,
    rating2       INTEGER,
    winner        INTEGER,      -- 1 Red, 2 Blue, 0 draw
    result_reason TEXT,
    game_type     TEXT,
    time_control  TEXT,
    move_count    INTEGER,
    board         TEXT          -- JSON list of rows
);
CREATE TABLE IF NOT EXISTS positions (
    game_id   TEXT REFERENCES games(game_id),
    ply       INTEGER,          -- 0 = starting position
    state     TEXT,             -- JSON, see state_to_json
    next_move TEXT,             -- JSON {piece_id, to_row, to_col}, NULL after the last move
    PRIMARY KEY (game_id, ply)
);
"""


def state_to_json(state: GameState) -> str:
    """Everything except the board, which is stored once in games."""
    return json.dumps({
        "pieces": [[p.id, p.type, p.player, p.row, p.col, p.captured, p.finished] for p in state.pieces],
        "current_turn": state.current_turn,
        "move_count": state.move_count,
        "finished_pieces": state.finished_pieces,
        "first_to_finish": state.first_to_finish,
        "game_over": state.game_over,
        "winner": state.winner,
        "scores": state.scores,
    })


def state_from_json(text: str, board: list[list[int]]) -> GameState:
    d = json.loads(text)
    pieces = [Piece(id=i, type=t, player=pl, row=r, col=c, captured=cap, finished=fin)
              for i, t, pl, r, c, cap, fin in d.pop("pieces")]
    return GameState(board=board, pieces=pieces, **d)


def replay(data: dict) -> list[tuple[GameState, dict | None]]:
    """[(state, move played from it)] for every position, the last with move None.

    Raises ValueError if the engine disagrees with the site."""
    state = new_game(data["board"])
    positions = []
    for m in data["move_history"]:
        move = {"piece_id": m["pieceId"], "to_row": m["toRow"], "to_col": m["toCol"]}
        positions.append((state, move))
        try:
            state = apply_move(state, m["pieceId"], m["toRow"], m["toCol"])
        except IllegalMove as e:
            raise ValueError(f"move {m['moveNumber']} ({m['notation']}): {e}") from None
    positions.append((state, None))

    # The final position must match the site's, or the engine's rules differ somewhere
    site = {p["id"]: p for p in data["pieces"]}
    for p in state.pieces:
        s = site[p.id]
        if (p.captured, p.finished) != (s["is_captured"], s["is_finished"]) or \
                (p.active and (p.row, p.col) != (s["row"], s["col"])):
            raise ValueError(f"final position differs from the site's for {p.id}")
    if state.scores != data["scores"] or state.winner != data["winner"]:
        raise ValueError(f"engine ends with scores {state.scores} winner {state.winner}, "
                         f"site has {data['scores']} winner {data['winner']}")
    return positions


def import_game(con: sqlite3.Connection, path: Path) -> str:
    """Import one exported game; return what happened, for printing."""
    data = json.loads(path.read_text())
    game_id = data["game_id"]
    if con.execute("SELECT 1 FROM games WHERE game_id = ?", (game_id,)).fetchone():
        return "already imported"
    if not data["game_over"] or data["game_aborted"] or data["winner"] is None:
        return "skipped, game not finished"
    try:
        positions = replay(data)
    except ValueError as e:
        return f"skipped, {e}"

    with con:  # one transaction: the game and all its positions, or nothing
        con.execute("INSERT INTO games VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
            game_id, data["player1_username"], data["player2_username"],
            data["player1_rating"], data["player2_rating"], data["winner"],
            data["result_reason"], data["game_type"], data["time_control"],
            data["move_count"], json.dumps(data["board"]),
        ))
        con.executemany("INSERT INTO positions VALUES (?, ?, ?, ?)", [
            (game_id, ply, state_to_json(state), json.dumps(move) if move else None)
            for ply, (state, move) in enumerate(positions)
        ])
    return f"imported, {len(positions)} positions"


def load_positions(db_path: Path = DB_PATH, include_finished: bool = False) -> list[tuple[GameState, int]]:
    """[(state, winner of its game)] for every stored position, e.g. for tuning."""
    con = sqlite3.connect(db_path)
    boards = {}
    result = []
    rows = con.execute("SELECT p.game_id, p.state, g.winner, g.board FROM positions p "
                       "JOIN games g ON g.game_id = p.game_id ORDER BY p.game_id, p.ply")
    for game_id, state_text, winner, board_text in rows:
        if game_id not in boards:
            # One board object per game, so distanceMap's cache works
            boards[game_id] = json.loads(board_text)
        state = state_from_json(state_text, boards[game_id])
        if include_finished or not state.game_over:
            result.append((state, winner))
    con.close()
    return result


def main() -> None:
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    for path in sorted(DATA_DIR.glob("*.json")):
        print(f"{path.name}: {import_game(con, path)}")
    games, positions = con.execute(
        "SELECT (SELECT COUNT(*) FROM games), (SELECT COUNT(*) FROM positions)").fetchone()
    print(f"\n{DB_PATH.name}: {games} games, {positions} positions")
    con.close()


if __name__ == "__main__":
    main()
