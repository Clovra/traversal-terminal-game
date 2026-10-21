
from traversal import GameState, Move, all_legal_moves

def choose_move(state: GameState) -> Move:
    """ the bot action"""
    list = all_legal_moves(state)
    best = list[0]
    if state.current_turn == 1 :
        for i in list:
            if i.to_row < best.to_row:
                best = i
    else :
        for i in list:
            if i.to_row > best.to_row:
                best = i
    
    return best

