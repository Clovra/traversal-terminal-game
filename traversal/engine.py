"""Traversal rules engine.

A Python port of the engine behind traversalgame.com
(assets/localGameEngine-*.js); see RULES.md for the rules it implements.

Coordinates are (row, col) with row 0 at the top edge. Player 1 (Red) starts on
the bottom row and exits off the top edge; player 2 (Blue) does the reverse.
A finishing move targets the row just past the goal edge: -1 for player 1,
len(board) for player 2.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, replace

MOVE_LIMIT = 200

# type -> (movement, strength)
PIECE_STATS = {
    "explorer": (5, 1),
    "vanguard": (4, 2),
    "sentinel": (3, 3),
}

# (type, column) for each player's starting row, identical for both sides
START_LAYOUT = (
    ("sentinel", 2),
    ("vanguard", 3),
    ("explorer", 4),
    ("explorer", 5),
    ("vanguard", 6),
    ("sentinel", 7),
)

ORTHOGONAL = ((-1, 0), (1, 0), (0, -1), (0, 1))
EXPLORER_JUMPS = ((-1, -1), (-1, 1), (1, -1), (1, 1), (-2, 0), (0, -2), (2, 0), (0, 2))


class IllegalMove(ValueError):
    pass


@dataclass
class Piece:
    id: str
    type: str
    player: int
    row: int
    col: int
    captured: bool = False
    finished: bool = False

    @property
    def movement(self) -> int:
        return PIECE_STATS[self.type][0]

    @property
    def strength(self) -> int:
        return PIECE_STATS[self.type][1]

    @property
    def active(self) -> bool:
        return not self.captured and not self.finished


@dataclass(frozen=True)
class Move:
    piece_id: str
    to_row: int
    to_col: int
    cost: int
    is_attack: bool = False
    captured_id: str | None = None
    finishes: bool = False
    # Explorer diagonal step or leap: ignores height and uses the whole turn
    special: str | None = None  # "diagonal" or "leap"
    # Effective strengths, filled in for attacks only
    attack_strength: int | None = None
    defense_strength: int | None = None


@dataclass
class GameState:
    board: list[list[int]]
    pieces: list[Piece]
    current_turn: int = 1
    move_count: int = 0
    finished_pieces: list[str] = field(default_factory=list)
    first_to_finish: str | None = None
    game_over: bool = False
    winner: int | None = None  # 1 or 2, or 0 for a draw
    scores: list[int] = field(default_factory=lambda: [0, 0])
    position_history: list[str] = field(default_factory=list)
    draw_reason: str | None = None
    win_reason: str | None = None
    victory_type: str | None = None

    @property
    def size(self) -> int:
        return len(self.board)

    def copy(self) -> GameState:
        # The board never changes during a game, so it is shared
        return replace(
            self,
            pieces=[replace(p) for p in self.pieces],
            finished_pieces=list(self.finished_pieces),
            scores=list(self.scores),
            position_history=list(self.position_history),
        )

    def piece(self, piece_id: str) -> Piece | None:
        return next((p for p in self.pieces if p.id == piece_id), None)

    def piece_at(self, row: int, col: int) -> Piece | None:
        return next((p for p in self.pieces if p.active and p.row == row and p.col == col), None)

    def active_pieces(self, player: int) -> list[Piece]:
        return [p for p in self.pieces if p.player == player and p.active]


def new_game(board: list[list[int]]) -> GameState:
    size = len(board)
    pieces = [
        Piece(id=f"p{player}_{col}", type=kind, player=player, row=row, col=col)
        for player, row in ((1, size - 1), (2, 0))
        for kind, col in START_LAYOUT
    ]
    return GameState(board=board, pieces=pieces)


def step_cost(board: list[list[int]], r1: int, c1: int, r2: int, c2: int) -> int:
    return abs(board[r2][c2] - board[r1][c1]) + 1


def is_goal_row(piece: Piece, row: int, size: int) -> bool:
    return row == 0 if piece.player == 1 else row == size - 1


def _neighbours(state: GameState, row: int, col: int):
    n = state.size
    for dr, dc in ORTHOGONAL:
        r, c = row + dr, col + dc
        if 0 <= r < n and 0 <= c < n:
            p = state.piece_at(r, c)
            if p:
                yield p


def combat_strengths(state: GameState, attacker: Piece, defender: Piece) -> tuple[int, int]:
    """Effective (attack, defense), without the Vanguard charge bonus."""
    diff = state.board[attacker.row][attacker.col] - state.board[defender.row][defender.col]
    attack = attacker.strength + (diff > 0) - (diff < 0)
    attack += sum(
        p.strength
        for p in _neighbours(state, defender.row, defender.col)
        if p.player == attacker.player and p.id != attacker.id
    )
    defense = defender.strength + sum(
        1 for p in _neighbours(state, defender.row, defender.col) if p.player == defender.player
    )
    return attack, defense


def legal_moves(state: GameState, piece_id: str) -> list[Move]:
    piece = state.piece(piece_id)
    if piece is None or not piece.active or piece.player != state.current_turn:
        return []

    board = state.board
    rows, cols = len(board), len(board[0]) if board else 0
    start = (piece.row, piece.col)
    movement = piece.movement

    best_remaining = {start: movement}
    moves: dict[tuple[int, int], Move] = {}
    exits: list[tuple[int, int, int]] = []
    attack_targets: dict[tuple[int, int], tuple[int, Piece]] = {}

    if is_goal_row(piece, piece.row, rows) and movement >= 1:
        exits.append((piece.row, piece.col, movement))

    queue = deque([(piece.row, piece.col, movement)])
    while queue:
        r, c, remaining = queue.popleft()
        if remaining < best_remaining.get((r, c), -1):
            continue
        if remaining >= 1 and (r, c) != start and is_goal_row(piece, r, rows):
            exits.append((r, c, remaining))

        for dr, dc in ORTHOGONAL:
            nr, nc = r + dr, c + dc
            if not (0 <= nr < rows and 0 <= nc < cols):
                continue
            cost = step_cost(board, r, c, nr, nc)
            if cost > remaining:
                continue
            occupant = state.piece_at(nr, nc)
            if occupant:
                if occupant.player != piece.player:
                    spent = movement - remaining + cost
                    known = attack_targets.get((nr, nc))
                    if known is None or spent < known[0]:
                        attack_targets[(nr, nc)] = (spent, occupant)
                continue
            left = remaining - cost
            if left > best_remaining.get((nr, nc), -1):
                best_remaining[(nr, nc)] = left
                if (nr, nc) != start:
                    moves[(nr, nc)] = Move(piece.id, nr, nc, cost=movement - left)
                if left > 0:
                    queue.append((nr, nc, left))

    result = list(moves.values())

    for (tr, tc), (min_cost, target) in attack_targets.items():
        attack, defense = combat_strengths(state, piece, target)
        if piece.type == "vanguard" and min_cost == 4:
            attack += 1
        if attack >= defense:
            result.append(
                Move(
                    piece.id, tr, tc, cost=min_cost, is_attack=True, captured_id=target.id,
                    attack_strength=attack, defense_strength=defense,
                )
            )

    exit_row = -1 if piece.player == 1 else rows
    exit_cols: set[int] = set()
    for _, c, _ in exits:
        if c not in exit_cols:
            exit_cols.add(c)
            result.append(Move(piece.id, exit_row, c, cost=movement, finishes=True))

    if piece.type == "explorer":
        for dr, dc in EXPLORER_JUMPS:
            tr, tc = piece.row + dr, piece.col + dc
            special = "leap" if abs(dr) == 2 or abs(dc) == 2 else "diagonal"
            if abs(dr) == 2 or abs(dc) == 2:
                mr, mc = piece.row + dr // 2, piece.col + dc // 2
                if not (0 <= mr < rows and 0 <= mc < cols) or state.piece_at(mr, mc):
                    continue
            if (tr < 0 or tr >= rows) and 0 <= tc < cols:
                forward = dr < 0 if piece.player == 1 else dr > 0
                if forward and tc not in exit_cols:
                    exit_cols.add(tc)
                    result.append(Move(piece.id, exit_row, tc, cost=movement, finishes=True, special=special))
                continue
            if not (0 <= tr < rows and 0 <= tc < cols):
                continue
            if (tr, tc) in best_remaining or (tr, tc) in attack_targets:
                continue
            occupant = state.piece_at(tr, tc)
            if occupant is None:
                result.append(Move(piece.id, tr, tc, cost=movement, special=special))
            elif occupant.player != piece.player:
                attack, defense = combat_strengths(state, piece, occupant)
                if attack >= defense:
                    result.append(
                        Move(
                            piece.id, tr, tc, cost=movement, is_attack=True, captured_id=occupant.id,
                            attack_strength=attack, defense_strength=defense, special=special,
                        )
                    )

    return result


def all_legal_moves(state: GameState) -> list[Move]:
    """Every legal move for the player whose turn it is."""
    if state.game_over:
        return []
    return [m for p in state.active_pieces(state.current_turn) for m in legal_moves(state, p.id)]


def apply_move(state: GameState, piece_id: str, to_row: int, to_col: int) -> GameState:
    """Return the state after the move; the input state is left unchanged."""
    if state.game_over:
        raise IllegalMove("the game is over")
    move = next(
        (m for m in legal_moves(state, piece_id) if m.to_row == to_row and m.to_col == to_col),
        None,
    )
    if move is None:
        raise IllegalMove(f"{piece_id} cannot move to ({to_row}, {to_col})")

    s = state.copy()
    size = s.size
    piece = s.piece(piece_id)

    if move.is_attack and move.captured_id:
        s.piece(move.captured_id).captured = True

    if to_row < 0 or to_row >= size:
        piece.row = 0 if piece.player == 1 else size - 1
        piece.col = to_col
        piece.finished = True
        s.finished_pieces.append(piece_id)
        s.scores = _finished_scores(s)
        if s.first_to_finish is None:
            s.first_to_finish = piece_id
            if piece.type == "sentinel":
                s.game_over = True
                s.winner = piece.player
    else:
        piece.row, piece.col = to_row, to_col

    if len(s.finished_pieces) >= 2 and not s.game_over:
        s.game_over = True
        s.winner = _higher_score(s.scores)

    if not s.game_over:
        red, blue = s.active_pieces(1), s.active_pieces(2)
        if not red or not blue:
            s.game_over = True
            s.scores = [
                s.scores[0] + max((p.strength for p in red), default=0),
                s.scores[1] + max((p.strength for p in blue), default=0),
            ]
            s.winner = _higher_score(s.scores)

    _end_turn(s)
    return s


def pass_turn(state: GameState) -> GameState:
    """Skip a turn. Not part of the official engine; for a player with no legal moves."""
    if state.game_over:
        raise IllegalMove("the game is over")
    s = state.copy()
    _end_turn(s)
    return s


def _end_turn(s: GameState) -> None:
    if s.game_over and s.victory_type is None:
        s.victory_type = _victory_type(s)
    s.current_turn = 2 if s.current_turn == 1 else 1
    s.move_count += 1
    if not s.game_over and s.move_count >= MOVE_LIMIT:
        _resolve_move_limit(s)
    if not s.game_over:
        s.position_history.append(_position_key(s))
        history = s.position_history
        for span in range(2, len(history) // 3 + 1, 2):
            last = history[-span:]
            if last == history[-2 * span:-span] and last == history[-3 * span:-2 * span]:
                s.game_over = True
                s.winner = 0
                s.draw_reason = "threefold_repetition"
                s.scores = _finished_scores(s)
                break


def _higher_score(scores: list[int]) -> int:
    if scores[0] > scores[1]:
        return 1
    if scores[1] > scores[0]:
        return 2
    return 0


def _resolve_move_limit(s: GameState) -> None:
    size = s.size
    s.game_over = True
    s.scores = _finished_scores(s)
    if s.scores[0] != s.scores[1]:
        s.winner = _higher_score(s.scores)
        s.win_reason = "move_limit_score"
        return

    def closest(player: int) -> tuple[int, int] | None:
        found = None
        for p in s.active_pieces(player):
            rows_left = p.row if player == 1 else size - 1 - p.row
            if found is None or rows_left < found[0] or (rows_left == found[0] and p.strength > found[1]):
                found = (rows_left, p.strength)
        return found

    def ahead(a, b) -> bool:
        return a is not None and (b is None or a[0] < b[0] or (a[0] == b[0] and a[1] > b[1]))

    red, blue = closest(1), closest(2)
    s.winner = 1 if ahead(red, blue) else 2 if ahead(blue, red) else 0
    if s.winner:
        s.win_reason = "move_limit_advancement"
    else:
        s.draw_reason = "move_limit"


def _victory_type(s: GameState) -> str | None:
    if s.winner not in (1, 2):
        return None
    loser = 2 if s.winner == 1 else 1
    if not s.active_pieces(loser):
        return "total_domination"
    winner_types = set()
    loser_finished = 0
    for piece_id in s.finished_pieces:
        p = s.piece(piece_id)
        if p.player == s.winner:
            winner_types.add(p.type)
        else:
            loser_finished += 1
    if loser_finished == 0 and {"vanguard", "sentinel"} <= winner_types:
        return "perfect_game"
    return None


def _position_key(s: GameState) -> str:
    on_board = sorted(f"{p.player},{p.type},{p.row},{p.col}" for p in s.pieces if p.active)
    return f"{s.current_turn}|{';'.join(on_board)}|{','.join(sorted(s.finished_pieces))}"


def _finished_scores(s: GameState) -> list[int]:
    scores = [0, 0]
    for piece_id in s.finished_pieces:
        p = s.piece(piece_id)
        scores[p.player - 1] += p.strength
    return scores
