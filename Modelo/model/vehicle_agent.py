import time
import numpy as np
from mesa import Agent, Model


class VehicleAgent(Agent):
    def __init__(self, unique_id: int, model: Model, width: float, length: float):
        # agent init
        super().__init__(unique_id, model)

        # values along road
        self.pos: float = 0.0
        self.acceleration: float = 0.0
        self.speed: float = 0.0

        self.last_tick: float = time.time()

        # agent characteristics
        self.length = length
        self.width = width

    def step(self) -> None:
        pass

    def advance(self) -> None:
        current_time = time.time()
        delta_t = current_time - self.last_tick
        self.speed += self.acceleration * delta_t
        self.pos += self.speed * delta_t
        self.last_tick = current_time
