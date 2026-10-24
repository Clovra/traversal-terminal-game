from traversal import GameState, Move, all_legal_moves,legal_moves, apply_move, pass_turn

nb_search = 0
def choose_move(state: GameState) -> Move:
    if state.move_count == 0 or state.move_count == 1 :
        global nb_search
        nb_search = 0
    best_move = None
    best_eval = None
    alpha, beta = -10000, 10000
    for m in order(all_legal_moves(state), state):
        e = minMax(apply_move(state, m.piece_id, m.to_row, m.to_col), 2, alpha, beta)
        if state.current_turn == 1:
            if best_eval is None or e > best_eval:
                best_eval, best_move = e, m
            alpha = max(alpha, e)
        else:
            if best_eval is None or e < best_eval:
                best_eval, best_move = e, m
            beta = min(beta, e)

    print(best_eval)
    print(nb_search)
    return best_move


def minMax (state: GameState, deep: int, alpha, beta  ):
    global nb_search
    nb_search += 1
    if (state.winner != None) or (deep == 0):
        return evaluation(state)
    
    if state.current_turn == 1:
        maxEval = -10000
        list_legal_move = order(all_legal_moves(state), state)
        for m in list_legal_move:
            eval = minMax(apply_move(state, m.piece_id, m.to_row, m.to_col), deep -1, alpha, beta)
            maxEval = Max(maxEval, eval)
            alpha =Max(alpha, eval)
            if beta <= alpha:
                break 
        return maxEval
    else :
        minEval = 10000
        list_legal_move = order(all_legal_moves(state), state)
        for m in list_legal_move:
            eval = minMax(apply_move(state, m.piece_id, m.to_row, m.to_col), deep -1, alpha, beta)
            minEval = Min(minEval, eval)
            beta = min(beta, eval)
            if beta <= alpha:
                break
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

def order(list_legal_move: list, state: GameState) -> list:
    if state.current_turn == 1:
        list_legal_move.sort(key=lambda m: (m.captured_id is None, m.to_row))
    else:
        list_legal_move.sort(key=lambda m: (m.captured_id is None, -m.to_row))
    return list_legal_move

def find_captur (legal_moves_rn: list) -> Move | None:
    for f in legal_moves_rn:
        if f.captured_id != None:
            return f
    return None;

def evaluation(state: GameState) -> int :
    eval = 0
    if state.winner == 1:
        return 1000
    if state.winner == 2:
        return -1000
    if state.winner == 0:
        return 0

   
    piece_value_r = piece_value(state)

    total_picec_balance = piece_value_r[0]

    total_advance = piece_value_r[1]

    #captur_bonus_r = captur_bonus(state)

    current_score_dif = state.scores[0] - state.scores[1]
    
    devlopement_malus_r = devlopement_malus(state)

    #print("total avence =" + str((total_advance * 1)) + "total peice balance =" + str((total_picec_balance * 5)) + "total picec balance = " + str((current_score_dif * 30)) + "captur bonus =" + str((captur_bonus_r * 3))

    eval = (total_advance * 1) + (total_picec_balance * 5) + (current_score_dif * 30) + devlopement_malus_r * 3

    return eval 


def piece_value(state: GameState) -> list :
    list_active_piece_1 = state.active_pieces(1)
    list_active_piece_2 = state.active_pieces(2)

    #Sentinal = 3
    #vanguard = 2
    #explorer = 1


    total_player_1 = 0
    total_player_2 = 0
    player1_advence = 0
    player2_advence = 0
    for p in list_active_piece_1:
        if p.type == "explorer":
            total_player_1 += 1
        if p.type == "vanguard":
            total_player_1 += 2
        if p.type == "sentinel":
            total_player_1 += 3
        player1_advence += (state.size - 1 ) - p.row

    for p in list_active_piece_2:
        if p.type == "explorer":
            total_player_2 += 1
        if p.type == "vanguard":
            total_player_2 += 2
        if p.type == "sentinel":
            total_player_2 += 3

        player2_advence += p.row


    total_picec_balance = total_player_1 - total_player_2

    total_advance = player1_advence - player2_advence

    return [total_picec_balance, total_advance]

def devlopement_malus (state: GameState) -> int:
    list_active_piece_1 = state.active_pieces(1)
    list_active_piece_2 = state.active_pieces(2)
    
    red_devlopement_malus = 0
    blue_devlopement_malus = 0

    for p in list_active_piece_1:
        if p.row == 9 :
            red_devlopement_malus -= 1  
    for p in list_active_piece_2:
        if p.row == 0 :
            blue_devlopement_malus += 1
    return red_devlopement_malus + blue_devlopement_malus


def captur_bonus(state: GameState) -> int:

    bonusR_captur  = 0
    bonusB_captur   = 0
    if not state.game_over:
        if state.current_turn == 1 :
            if find_captur(all_legal_moves(state)):
                bonusR_captur = 1
            state_pass = pass_turn(state)
            if find_captur(all_legal_moves(state_pass)) :
                bonusB_captur = 1
            return bonusR_captur - bonusB_captur
        if state.current_turn == 2: 
            if find_captur(all_legal_moves(state)):
                bonusB_captur = 1
            state_pass = pass_turn(state)
            if find_captur(all_legal_moves(state_pass)) :
                bonusR_captur = 1
            return bonusR_captur - bonusB_captur
    return 0
 
