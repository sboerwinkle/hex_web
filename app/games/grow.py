from .. import wait, tasks
from ..game import *

# Basic hex layout (x step, y step, row shift, y offset, clear image)
# (y_offset being because the tip top of the sprite is above the clickable area)
layout = (50, 43, 25, 7, 'hex_empty')

class GrowGame(Game):
    def __init__(self, *a, **kwa):
        super().__init__(*a, **kwa)
        self.task_queue = tasks.MillisTaskQueue(self.step_complete)
    async def cleanup(self):
        await self.task_queue.cancel()
    def seat_player(self, player):
        self.characters.append(GrowCharacter(self, player))
    def process_command(self, char, cmd):
        bits = cmd.split()
        if bits[0] == "/mag_pl":
            pos = (int(bits[1]), int(bits[2]))
            tile = self.board.get_tile(pos)
            has_grass = False
            for e in tile.contents:
                if isinstance(e, SpriteEnt) and e.sprite == "grass":
                    has_grass = True
                elif isinstance(e, MagentaPlant):
                    raise PebkacException("Something is already growing there")
            if not has_grass:
                raise PebkacException("Nothing plantable there!")
            delay = int(bits[3]) if len(bits) > 3 else 2000
            Move(MagentaPlant(delay, self), pos).sched(self.task_queue)
            return
        if bits[0] == "/click":
            pos = (int(bits[1]), int(bits[2]))
            tile = self.board.get_tile(pos)
            has_grass = False
            plant = None
            for e in tile.contents:
                if not has_grass and isinstance(e, SpriteEnt) and e.sprite == "grass":
                    has_grass = True
                elif isinstance(e, MagentaPlant):
                    plant = e
                    break
            if plant != None:
                if plant.stage != 3:
                    raise PebkacException("Not ready for harvest!")
                Destroy(plant).sched(self.task_queue)
                char.coins += 2
            elif has_grass:
                if char.coins < 1:
                    raise PebkacException("Planting costs a coin!")
                char.coins -= 1
                Move(MagentaPlant(2000, self), pos).sched(self.task_queue)
            else:
                if char.coins < 5:
                    raise PebkacException("Creating land costs 5 coins!")
                char.coins -= 5
                Move(SpriteEnt("grass", self), pos).sched(self.task_queue)
            return
        if bits[0] == "/coins":
            char.coins = int(bits[1])
            self.step_complete() # TODO This method is more aptly named `write_state` or something...
            return
        super().process_command(char, cmd)

class GrowCharacter(Character):
    def __init__(self, *a, **kwa):
        self.coins = 6
        super().__init__(*a, layout = layout, **kwa)
        if self.player != None:
            self.player.whisper_raw(">>> Click on the board to get started!")
    def draw_to_board(self, out_board):
        # Coin emoji
        self.player.set_status(f"\U0001FA99{self.coins}")
        return super().draw_to_board(out_board)

class MagentaPlant(Ent):
    def __init__(self, delay, *a, **kwa):
        super().__init__(*a, **kwa)
        self.delay = delay
        self.stage = 1
        self.game.task_queue.schedule(self.grow, self.delay, tasks.NO_PATIENCE)
    def draw(self, out_board):
        out_board.require_tile(self.pos).add("mag_pl_" + str(self.stage))
    def grow(self):
        if self.game == None:
            return
        self.stage += 1
        if self.stage < 3:
            self.game.task_queue.schedule(self.grow, self.delay, tasks.NO_PATIENCE)
