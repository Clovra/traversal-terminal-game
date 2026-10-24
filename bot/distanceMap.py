from dataclasses import dataclass

@dataclass
class DistanceMap:
    player: int                 # 1 = Red, 2 = Blue
    movement: int               # 5 explorer, 4 vanguard, 3 sentinel
    turns: list[list[int]]      # turns[row][col] = turns needed to finish from that square
    max_turns: int              # the biggest value in turns, the slowest square to finish from

    def turns_at(self, row: int, col: int) -> int:
        return self.turns[row][col]

    def progress_at(self, row: int, col: int) -> int:
        # turns gained compared to the slowest square; never negative, so a piece
        # still on the board always counts for something
        return self.max_turns - self.turns[row][col]

def one_turn(board, r, c, movement) -> dict[tuple[int, int], int]:
    """{(row, col): movement left} for every square reachable this turn."""
    n = len(board)
    best = {(r, c): movement}
    todo = [(r, c)]
    while todo:
        cr, cc = todo.pop()
        left = best[(cr, cc)]
        for nr, nc in ((cr-1, cc), (cr+1, cc), (cr, cc-1), (cr, cc+1)):
            if 0 <= nr < n and 0 <= nc < n:
                cost = abs(board[nr][nc] - board[cr][cc]) + 1
                if cost <= left:
                    leftover = left - cost
                    if leftover > best.get((nr, nc), -1):
                        best[(nr, nc)] = leftover
                        todo.append((nr, nc))
    return best

def build_map(board, player, movement) -> DistanceMap:
    n = len(board)
    goal = 0 if player == 1 else n - 1
    reach = {}                  # (r, c) -> one_turn result, computed once
    turns = [[99] * n for _ in range(n)]
    for r in range(n):
        for c in range(n):
            reach[(r, c)] = one_turn(board, r, c, movement)

    changed = True
    while changed:
        changed = False
        for r in range(n):
            for c in range(n):
                # finishing needs a square on the goal row with at least 1 movement left
                can_finish = False
                for (tr, tc), left in reach[(r, c)].items():
                    if tr == goal and left >= 1:
                        can_finish = True
                        break
                if can_finish:
                    new = 1
                else:
                    new = 1 + min(turns[tr][tc] for (tr, tc) in reach[(r, c)])
                if new < turns[r][c]:
                    turns[r][c] = new
                    changed = True
    max_turns = max(max(row) for row in turns)
    return DistanceMap(player, movement, turns, max_turns)

# The board never changes during a game, so the maps are built once per board
_maps_board = None
_maps = {}          # (player, movement) -> DistanceMap

def get_map(board, player, movement) -> DistanceMap:
    global _maps_board, _maps
    if board is not _maps_board:          # new game → new board
        _maps_board = board
        _maps = {}
        for pl in (1, 2):
            for mv in (3, 4, 5):
                _maps[(pl, mv)] = build_map(board, pl, mv)
    return _maps[(player, movement)]
