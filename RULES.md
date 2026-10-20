# Traversal Rules

Source: https://www.traversalgame.com/rules (the English rules text), plus the
site's own rules engine (`assets/localGameEngine-*.js`), which settles details
the text leaves open. Those details are listed under
[Engine details](#engine-details) at the end.

## Overview

Traversal is a two player strategy game played on a 10×10 grid of varying
terrain heights. Each player commands six pieces and must move them across the
board and off the opposite edge to score. Each piece that crosses scores points
equal to its Strength. After any two pieces have finished, regardless of which
player they belong to, the highest score wins.

Traversing will not be easy. The board is a three-dimensional landscape of
mountains and valleys, and every change in elevation costs extra Movement. Your
opponent is racing the other direction, and you'll fight for position,
capturing enemy pieces and defending your own. Faster pieces are weaker,
stronger pieces are slower. Choosing which pieces to push, which to sacrifice,
and which routes to take are strategic decisions at the heart of every game.

| At a glance | |
| --- | --- |
| Players | 2 |
| Pieces each | 6 |
| Grid | 10×10 |
| Piece types | 3 |

## Board

The board is a 10×10 grid where each square has a height value, creating a
three-dimensional landscape of mountains and valleys. Adjacent squares can
differ by at most 2 height units, ensuring terrain is always traversable and
there are no impassable cliffs.

Every game is played on a different board, you'll never play the same map
twice. Terrains are generated to be fair; neither side gets a significant
advantage. Players can choose a terrain mode before the game, each producing a
different style of landscape:

| Mode | Style |
| --- | --- |
| Random | Balanced variety of terrain |
| Mountains | Dramatic central peaks |
| Valleys | Deep basins with ridges |
| Highlands | Mountains and valleys combined |
| Woodlands | Mostly flat, gentle hills |
| Desert | Flat expanses, rare spikes |

## Pieces

Each player begins with six pieces: two of each type. Pieces are placed
symmetrically across the center columns of their starting row. Each piece's
Movement corresponds to the number of sides of its base. Each piece's Strength
corresponds to the number of points around its top. Movement and Strength
always sum to 6, the faster a piece moves, the weaker it is in combat and vice
versa.

| Piece | Shape | Movement | Strength | Special |
| --- | --- | --- | --- | --- |
| Explorer | Pentagon cone | 5 | 1 | Instead of its normal movement, can move 1 square diagonally or leap 2 squares in a single direction (forward, backward, left, or right) from its starting position, ignoring height cost. The most mobile piece on the board. |
| Vanguard | Diamond wedge | 4 | 2 | Gains +1 attack strength when it uses all 4 of its Movement to reach a target. The 4 Movement must be the shortest path to the target. Rewards aggressive positioning. |
| Sentinel | Triangular prism | 3 | 3 | If a Sentinel is the first piece of either side to finish off the board, that player wins immediately. The most valuable and dangerous piece. |

### Starting Setup

Player 1 (Red) starts on row 1 (bottom), Player 2 (Blue) on row 10 (top), in
columns C–H (columns 2–7 counting from 0), arranged symmetrically:

```
Row 10:  . . S V E E V S . .   (Blue)
          ...10 x 10 terrain grid...
Row 1:   . . S V E E V S . .   (Red)
```

## Movement

On your turn, select one of your pieces and move it. Pieces move orthogonally
(forward, backward, left, right) across the grid, spending Movement based on
the terrain.

1. A piece can move to any square within its Movement and can change direction.
2. You cannot move through any piece, friend or foe. You must find paths around them.
3. You cannot return to the square you started from in the same turn.
4. After moving (or choosing to attack), your turn ends and play passes to your opponent.

### Movement Costs

- **Flat:** moving to a square at the same height costs **1** Movement.
- **Up & down:** moving to a higher or lower square costs the **height
  difference + 1**. Going from height 2 to height 4 costs 3; dropping from
  height 4 to height 2 also costs 3.

### Explorer Movement Special

Explorers have two special movement options from their starting position each
turn. These are standalone moves that cannot be combined with normal movement.

- **Diagonal step:** move 1 square diagonally, regardless of height difference.
- **Orthogonal leap:** jump 2 squares in a cardinal direction, regardless of height.

## Combat

When one of your pieces is adjacent to an enemy piece, you may choose to attack
instead of moving to an empty square. Combat is resolved instantly by comparing
effective strengths. If the attacker's strength is greater than or equal to the
defender's, the defender is captured and removed from the game.

Attacking ends your turn. You cannot move further after an attack. If an attack
would fail (attacker strength < defender strength), the move is not allowed.
Captured pieces are permanently removed from the game.

### Strength Modifiers

- **Downhill:** attacking from higher ground gives **+1** Strength. Attacking
  downhill means your piece started the turn on a higher elevation than the target.
- **Uphill:** attacking uphill gives **−1** Strength. Attacking uphill means
  your piece started the turn on a lower elevation than the target.
- **Allies:** when attacking, each of your pieces adjacent to the target adds
  its **base Strength** to the attack.
- **Reinforcements:** when defending, each friendly piece adjacent to the
  defender adds **+1** to defense.

### Strength Formulas

- **Attacker** = Strength + Height Advantage + Allies (+Strength)
- **Defender** = Strength + Reinforcements (+1 each)

### Vanguard Attack Special

A Vanguard gains **+1** attack strength when it **must use all 4** of its
Movement to reach the target.

### Examples

- **Hill advantage:** a Red Vanguard (base 2) attacks downhill (+1) for 3. The
  Blue Vanguard defends with base 2 + 1 adjacent reinforcement = 3. Attacker
  wins (3 ≥ 3) and the Blue Vanguard is captured.
- **Allied assault:** a Red Explorer (base 1) attacks with an ally Vanguard
  adjacent to the target (+2) for 3. The Blue Sentinel defends with base 3.
  Attacker wins (3 ≥ 3) and the Blue Sentinel is captured.

## Scoring

The ultimate goal of the game is to move your pieces across the board to
finish by crossing the opposite edge. To finish, a piece must be on the final
row and have at least 1 Movement remaining to step off the board. Once
finished, the piece is removed and its Strength is added to your score. The
game ends when any combination of **two pieces total** have finished. They can
belong to the same player or different players.

- **Player 1 (Red):** starts on row 1 (bottom). Finishes by exiting off **row 10** (top edge).
- **Player 2 (Blue):** starts on row 10 (top). Finishes by exiting off **row 1** (bottom edge).

Points: Explorer 1, Vanguard 2, Sentinel 3.

### Standard Victory

When the second piece finishes, each player's **score** is the sum of the
Strength of their finished pieces. The higher score wins. Equal scores result
in a draw.

### Sentinel Victory Special

If a **Sentinel** is the *very first piece* (of either player) to finish, that
player **wins instantly**. This makes the Sentinel a high-risk high-reward
piece, slow, but game-ending if it crosses first.

### Move Limit

A game that reaches **200 moves** ends there, and the higher score wins. If
neither player has scored, the player whose piece is closest to finishing wins,
counting the rows it still has to cross. If both players' closest pieces are
equally close, the stronger piece wins. If they are also equally strong, the
game is a draw.

## Strategy Tips

- **Control the high ground.** Pieces on elevated terrain are cheaper to move
  downhill from and gain +1 strength when attacking below. Position your pieces
  on ridgelines to dominate the board.
- **The Sentinel gambit.** Pushing a Sentinel across first wins the game
  outright, but Sentinels have the lowest movement. Use Explorers and Vanguards
  to clear a path or create diversions. Your opponent must respect the Sentinel
  threat at all times.
- **Formation defense.** Adjacent reinforcements bolster a defender's strength.
  Keeping pieces close creates a defensive wall that's difficult to break
  through. But beware, bunching up slows your advance.
- **The Vanguard charge.** Position your Vanguards exactly 4 Movement away from
  a target to unlock their +1 attack bonus. On varied terrain this range
  shifts, both climbs and descents cost extra, so elevation changes in any
  direction can bring a distant enemy into charging range.
- **Explorer flanking.** Explorers can move diagonally and leap over terrain,
  making them ideal for flanking maneuvers and reaching unexpected positions.
  Their low strength means they should avoid direct confrontation with
  stronger pieces.
- **Race vs. fight.** Sometimes the fastest path to victory is avoiding combat
  entirely and racing pieces to the finish. Other times, capturing a key enemy
  piece changes the score calculus entirely. Read the board and adapt.

## Engine details

These come from the site's engine code, which `traversal/engine.py` ports.

- **Attacks happen at the end of a path.** A piece can spend Movement moving
  next to an enemy and then step into its square. The step into the target
  must be affordable with the Movement left. The attacker then occupies the
  captured square. The height modifier still compares the attacker's
  *starting* square with the target.
- **Vanguard bonus:** applies when the cheapest path into the target costs
  exactly 4.
- **Allies** are counted at their current positions and exclude the attacker
  itself.
- **Explorer specials** are only offered for squares the Explorer cannot reach
  by normal movement. A leap needs the square it jumps over to be on the board
  and empty, so it cannot jump over pieces. Diagonal steps and leaps can
  capture (with no Vanguard-style bonus) and can carry the Explorer off its
  goal edge to finish.
- **Finishing** uses the whole turn. A piece already on its goal row at the
  start of the turn can step off immediately.
- **Wipeout:** if a player has no pieces left on the board, the game ends at
  once and each player adds the Strength of their strongest remaining piece to
  their score.
- **Move limit:** 200 moves counts both players' moves.
- **Repetition:** if the same sequence of positions repeats three times in a
  row, the game is a draw.
- **No legal moves:** the site's engine doesn't handle this. The local
  two-player program lets the stuck player pass, and a pass counts as a move.
