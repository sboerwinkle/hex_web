from .. import wait, tasks, vector as vec
from ..game import *
#from ..actions import SingletonScheduler

layout = (31, 31, 0, 0)

path_symbols = {
        'w': ( 0, -1),
        'a': (-1,  0),
        's': ( 0,  1),
        'd': ( 1,  0)
}

teams = ("red", "green")

def decode_path_symbol(sym):
    try:
        return path_symbols[sym]
    except KeyError:
        raise PebkacException(f"symbol '{sym}' is not valid, must be one of {list(path_symbols.keys())}")

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
                player.whisper_raw(f">>> You are {team}")
                self.characters.append(PathCharacter(team, self, player))
                self.step_complete()
                return
        player.whisper_raw(f"!!! Sorry, no more than {len(teams)} players are supported, you were not added to the game")
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
            for c in self.characters:
                if c.instructions is None:
                    break
            else:
                self.launch_all_characters()
            return
        super().process_command(char, cmd)
    def launch_all_characters(self):
        for c in self.characters:
            self.task_queue.schedule(c.step, 0, tasks.NO_PATIENCE)

class PathCharacter(Character):
    def __init__(self, team, *a, **kwa):
        self.team = team
        super().__init__(*a, layout = layout, **kwa)

        self.instructions = None
        # TODO This should happen at round-start, not here
        SpriteEnt("sq_" + self.team, self.game, (0, 0))
        self.avatar = SpriteEnt("sq_face_1", self.game, (0, 0))
    # Default impl of draw_to_board is fine, literally nothing special / of interest is going on per-player
    def set_player(self, p):
        if p is None:
            if self.player is not None:
                self.abandoned_name = self.player.name
        else:
            self.abandoned_name = None
        super().set_player(p)
    def step(self):
        if len(self.instructions):
            instr = self.instructions.pop(0)
            new_pos = vec.add(self.avatar.pos, instr)
            SpriteEnt("sq_" + self.team, self.game, new_pos)
            self.avatar.move(new_pos)
            self.game.task_queue.schedule(self.step, 5, tasks.NO_PATIENCE)
        else:
            self.instructions = None
