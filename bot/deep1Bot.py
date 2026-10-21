from traversal import GameState, Move, all_legal_moves, apply_move, pass_turn


def choose_move(state: GameState) -> Move:
    """ the bot action"""
    list = all_legal_moves(state)
    top_list = find_all_best(list, state.current_turn)
    if len(top_list) > 1:
        best_curent_move = top_list[0]
        best_next_move = list[0]
        best_value = 0
        for f in top_list:
            new_state = apply_move(state, f.piece_id, f.to_row, f.to_col)
            if new_state.game_over:
                continue
            pass_oponent_turn = pass_turn(new_state)
            new_list_legal_move = all_legal_moves(pass_oponent_turn)
            new_top_list = find_all_best(new_list_legal_move, state.current_turn)
            if not new_top_list:
                continue
            if state.current_turn == 1 :
                if new_top_list[0].to_row < best_value:
                    best_value = new_top_list[0].to_row
                    best_next_move = new_top_list[0]
                    best_curent_move = f
            else:
                if new_top_list[0].to_row > best_value:
                    best_value = new_top_list[0].to_row
                    best_next_move = new_top_list[0]
                    best_curent_move = f
 
    else : 
        best_curent_move = top_list[0]

    return best_curent_move

# make a fonction that take a list and send back a list of all the best moove 
def find_all_best(leagal_moves: list, current_turn: list) -> list:
    list_of_best = []
    if not leagal_moves:
        return list_of_best
    best_value = leagal_moves[0].to_row
    if current_turn == 1:
        for i in leagal_moves:
            if i.to_row < best_value:
                best_value = i.to_row
        for f in leagal_moves:
            if f.to_row == best_value:
                list_of_best.append(f)
    else:
        for i in leagal_moves:
            if i.to_row > best_value:
                best_value = i.to_row
        for f in leagal_moves:
            if f.to_row == best_value:
                list_of_best.append(f)
    return list_of_best

