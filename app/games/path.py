from .. import wait, tasks, vector as vec
from ..game import *
import math
from random import Random

TILES_PER_CHAR = 12
DENSITY = 0.3

layout = (31, 31, 0, 0)

path_symbols = {
        'w': ( 0, -1),
        'a': (-1,  0),
        's': ( 0,  1),
        'd': ( 1,  0)
}

teams = (
    ("red", "\U0001F7E5"),
    ("green", "\U0001F7E9"),
    ("blue", "\U0001F7E6"),
    ("yellow", "\U0001F7E8"),
    ("black", "\U00002B1B"),
    ("purple", "\U0001F7EA"),
)

def decode_path_symbol(sym):
    try:
        return path_symbols[sym]
    except KeyError:
        raise PebkacException(f"symbol '{sym}' is not valid, must be one of {list(path_symbols.keys())}")

def tile_empty(t):
    for c in t.contents:
        if isinstance(c, SpriteEnt):
            return False
    return True

class PathGame(Game):
    def __init__(self):
        super().__init__()
        self.task_queue = tasks.MillisTaskQueue(self.step_complete, sec_per_turn = 0.1)
    async def cleanup(self):
        await self.task_queue.cancel()
    def seat_player(self, player):
        for c in self.characters:
            if c.abandoned_name == player.name:
                c.set_player(player)
                return
        for team in teams:
            for c in self.characters:
                if c.team == team:
                    break
            else:
                player.whisper_raw(f">>> You are {team[0]} {team[1]}")
                self.characters.append(PathCharacter(team, self, player))
                return
        player.whisper_raw(f"!!! Sorry, no more than {len(teams)} players are supported, you were not added to the game")
    def begin(self):        
        self.mk_board()
    def process_command(self, char, cmd):
        bits = cmd.split()
        # TODO /kick (For now this will only work for orphaned characters)
        if bits[0] == "/g":
            if not self.task_queue.async_task.done():
                raise PebkacException("/g not allowed while running! Wait!")
            if len(bits) == 1:
                bits.append("")
            if len(bits) != 2:
                raise PebkacException("/g requires only one arg: [wasd]*")
            input_path = bits[1]
            parsed_path = [decode_path_symbol(x) for x in input_path]
            char.instructions = parsed_path
            char.player.whisper_raw("... confirmed")
            for c in self.characters:
                if c.instructions is None:
                    break
            else:
                self.launch_all_characters()
        elif bits[0] == "/n":
            # TODO Also check for round completion, like actually
            if not self.task_queue.async_task.done():
                raise PebkacException("/n not allowed while running! Wait!")
            self.mk_board()
        elif bits[0] == "/help" or bits[0] == "/h":
            f = char.player.whisper_raw
            f('... Available commands are:')
            f('... /g [wasd]* - set your path (e.g. /g wdsdd)')
            f('... /n         - start a new round')
            f('... /help      - this help')
        else:
            super().process_command(char, cmd)
    def launch_all_characters(self):
        for c in self.characters:
            self.task_queue.schedule(c.step, 0, tasks.NO_PATIENCE)

    def legal_wall(self, pos):
        """
        This used to be a lot more complex,
        but it didn't work so well.
        Leaving it for now tho
        """
        return True

        t = self.board.get_tile
        moves = path_symbols.values()
        if not tile_empty(t(pos)):
            raise Exception(f"Shouldn't be asking about the legality of a wall in a filled space: {pos}")
        for a in moves:
            neighbor = vec.add(pos, a)
            if not tile_empty(t(neighbor)):
                continue
            openings = 0
            for b in moves:
                if tile_empty(t(vec.add(neighbor, b))):
                    openings += 1
                    # Walls are legal if they do not create "dead ends" in any of their neighbors
                    if openings == 3:
                        break
            else:
                return False
        return True
    def mk_board(self):
        rng = Random()
        tile_estimate = len(self.characters) * TILES_PER_CHAR
        height = int(math.sqrt(tile_estimate))
        width = height
        leftover = tile_estimate - width * height
        if leftover > height / 2:
            width = height + 1
            if leftover > height * 1.5 + 0.5:
                height = height + 1
        # +2 so we have space to draw the walls
        self.board.reset(width = width + 2, height = height + 2)

        # This is done outside the game loop,
        # so we can just call _run on our WriteOps directly
        # (Even if that's usually frowned upon)
        for i in range(width+2):
            Move(SpriteEnt("wall", self), (i, 0))._run()
            Move(SpriteEnt("wall", self), (i, height + 1))._run()
        for i in range(height):
            Move(SpriteEnt("wall", self), (0, i + 1))._run()
            Move(SpriteEnt("wall", self), (width + 1, i + 1))._run()
        l = []
        for i in range(width):
            for j in range(height):
                l.append((i + 1, j + 1))
        for _ in range(int(width*height*DENSITY)):
            ix = rng.randint(0, len(l) - 1)
            pos = l[ix]
            if not self.legal_wall(pos):
                break
            l.pop(ix)
            Move(SpriteEnt("wall", self), pos)._run()
        for c in self.characters:
            c.avatar_spawn_writeop(l.pop(rng.randint(0, len(l)-1)))._run()
        self.step_complete()

    def check_round_over(self):
        for c in self.characters:
            if c.instructions is not None:
                return
        self.task_queue.schedule(self.finish_round, 0, tasks.ACT_PATIENCE)
    def finish_round(self):
        round_scores = [c.score - c.prev_score for c in self.characters]
        max_score = max(round_scores)
        for c in self.characters:
            c.pity_points += max_score + c.prev_score - c.score

class PathCharacter(Character):
    def __init__(self, team, *a, **kwa):
        self.team = team
        self.score = 0
        self.pity_points = 0
        super().__init__(*a, layout = layout, **kwa)

        self.avatar = None
        self.instructions = None
    def avatar_spawn_writeop(self, pos):
        self.instructions = None
        self.score += 1 # For initial space, makes the math more obvious when looking at it
        self.prev_score = self.score
        self.avatar = SpriteEnt("sq_face_1", self.game)
        return WriteAll(
            Move(SpriteEnt("sq_" + self.team[0], self.game), pos),
            Move(self.avatar, pos),
        )
    def draw_to_board(self, out_board):
        self.player.set_status(' '.join([f"{c.team[1]}{c.score}({c.pity_points})\xA0\xA0\xA0\xA0" for c in self.game.characters]))
        return super().draw_to_board(out_board)
    def set_player(self, p):
        if p is None:
            if self.player is not None:
                self.abandoned_name = self.player.name
        else:
            self.abandoned_name = None
        super().set_player(p)
    def step(self):
        if 0 == len(self.instructions):
            self.instructions = None
            self.game.check_round_over()
            self.score += 1
            return
        instr = self.instructions.pop(0)
        new_pos = vec.add(self.avatar.pos, instr)
        if not tile_empty(self.game.board.get_tile(new_pos)):
            self.destroy_avatar()
            return

        new_square = SpriteEnt("sq_" + self.team[0], self.game)
        self.movement = WithClaim(
            self.game,
            new_pos,
            WriteAll(Move(new_square, new_pos), Move(self.avatar, new_pos))
        )
        self.movement.sched(self.game.task_queue)
        self.game.task_queue.schedule(self.verify_move, 0, tasks.ACT_PATIENCE)

    def verify_move(self):
        if self.movement.success:
            self.score += 1
            self.game.task_queue.schedule(self.step, 5, tasks.NO_PATIENCE)
        else:
            self.destroy_avatar()

    def destroy_avatar(self):
        self.instructions = None
        self.game.check_round_over()
        Destroy(self.avatar).sched(self.game.task_queue)
