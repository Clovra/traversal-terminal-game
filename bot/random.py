import random

from traversal import GameState, Move, all_legal_moves

def choose_move(state: GameState) -> Move:
    """ the bot action"""
    list = all_legal_moves(state)

    return random.choice(list)

