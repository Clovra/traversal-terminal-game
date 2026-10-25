#!/usr/bin/env python3
"""Copy the games from another PC's database into data/games.db.

    python3 mergeDb.py other_games.db
    python3 mergeDb.py other_games.db --into some.db

Games are matched by game_id (a random UUID for bot games, the site's id for
real games), so a game already here is skipped and merging the same file twice
adds nothing. The Elo ratings are refitted afterwards.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from bot.dataIntegration import DB_PATH, SCHEMA
from tournament import BOTS_SCHEMA, fit_elo, print_ratings


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge another games database into this one.")
    parser.add_argument("other", type=Path, help="the database to copy games from")
    parser.add_argument("--into", type=Path, default=DB_PATH, help=f"database to merge into (default {DB_PATH.name} in data/)")
    parser.add_argument("--anchor", default="random", help="bot fixed at Elo 0 (default random)")
    args = parser.parse_args()
    if not args.other.exists():
        sys.exit(f"No file {args.other}")
    if args.into.exists() and args.other.resolve() == args.into.resolve():
        sys.exit("That's the same database.")

    con = sqlite3.connect(args.into)
    con.executescript(SCHEMA + BOTS_SCHEMA)
    con.execute("ATTACH DATABASE ? AS other", (str(args.other),))
    tables = {name for (name,) in con.execute("SELECT name FROM other.sqlite_master WHERE type = 'table'")}
    if not {"games", "positions"} <= tables:
        sys.exit(f"{args.other} has no games and positions tables.")

    before = con.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    with con:  # all or nothing
        new_ids = "SELECT game_id FROM other.games WHERE game_id NOT IN (SELECT game_id FROM main.games)"
        con.execute(f"INSERT INTO main.positions SELECT * FROM other.positions WHERE game_id IN ({new_ids})")
        con.execute(f"INSERT INTO main.games SELECT * FROM other.games WHERE game_id IN ({new_ids})")
    after = con.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    con.execute("DETACH DATABASE other")

    print(f"Added {after - before} games; {args.into.name} now has {after} games.\n")
    print_ratings(fit_elo(con, args.anchor))
    con.close()


if __name__ == "__main__":
    main()
