from traversal import GameState, Move, all_legal_moves,legal_moves, apply_move, pass_turn


def choose_move(state: GameState) -> Move:
    best_move = None
    best_eval = None
    for m in all_legal_moves(state):
        e = minMax(apply_move(state, m.piece_id, m.to_row, m.to_col), 2)
        if best_eval is None \
           or (state.current_turn == 1 and e > best_eval) \
           or (state.current_turn == 2 and e < best_eval):
            best_eval = e
            best_move = m
    return best_move


def minMax (state: GameState, deep: int ):
    if (state.winner != None) or (deep == 0):
        return evaluation(state)
    
    if state.current_turn == 1:
        maxEval = -10000
        list_legal_move = all_legal_moves(state)
        for m in list_legal_move:
            eval = minMax(apply_move(state, m.piece_id, m.to_row, m.to_col), deep -1)
            maxEval = Max(maxEval, eval)
        return maxEval
    else :
        minEval = 10000
        list_legal_move = all_legal_moves(state)
        for m in list_legal_move:
            eval = minMax(apply_move(state, m.piece_id, m.to_row, m.to_col), deep -1)
            minEval = Min(minEval, eval)
        return minEval


def Max(int1: int, int2: int) -> int :
    if int1 > int2:
        return int1
    else :
        return int2

def Min(int1: int, int2: int) -> int :
    if int1 > int2:
        return int2
    else :
        return int1


def find_faster (legal_moves_rn: list, current_turn: list) -> list:
    list_of_best = []
    if not legal_moves_rn:
        return list_of_best
    best_value = legal_moves_rn[0].to_row
    if current_turn == 1:
        for i in legal_moves_rn:
            if i.to_row < best_value:
                best_value = i.to_row
        for f in legal_moves_rn:
            if f.to_row == best_value:
                list_of_best.append(f)
    else:
        for i in legal_moves_rn:
            if i.to_row > best_value:
                best_value = i.to_row
        for f in legal_moves_rn:
            if f.to_row == best_value:
                list_of_best.append(f)
    return list_of_best

def find_captur (legal_moves_rn: list) -> Move | None:
    for f in legal_moves_rn:
        if f.captured_id != None:
            return f
    return None;

def evaluation(state: GameState) -> int :
    eval = 0
    list_active_piece_1 = state.active_pieces(1)
    list_active_piece_2 = state.active_pieces(2)
    
    total_player_1 = 0
    total_player_2 = 0
    player1_advence = 0
    player2_advence = 0
    for p in list_active_piece_1:
        total_player_1 += 1
        player1_advence += (state.size - 1 ) - p.row
    for p in list_active_piece_2:
        total_player_2 += 1
        player2_advence += p.row

    total_picec_balance = total_player_1 - total_player_2

    total_advance = player1_advence - player2_advence

    current_score_dif = state.scores[0] - state.scores[1]

    eval = (total_advance * 1) + (total_picec_balance * 5) + (current_score_dif * 30)

    return eval 
