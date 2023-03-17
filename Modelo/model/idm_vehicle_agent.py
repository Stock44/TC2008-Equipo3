import time
import numpy as np
from mesa import Agent, Model


class IDMVehicleAgent(Agent):
    def __init__(self, unique_id: int, model: Model, length: float, desired_speed: float,
                 minimum_safety_gap: float, time_safety_gap: float, maximum_acceleration: float,
                 comfortable_deceleration: float, politeness: float, occupancy: int, max_occupancy: int):
        # agent init
        super().__init__(unique_id, model)

        self.pos: float = 0.0
        self.speed: float = 0.0
        self.acceleration: float = 0.0

        self.occupancy = occupancy
        self.max_occupancy = max_occupancy

        self.desired_speed: float = desired_speed
        self.minimum_safety_gap: float = minimum_safety_gap
        self.time_safety_gap: float = time_safety_gap
        self.maximum_acceleration: float = maximum_acceleration
        self.comfortable_deceleration: float = comfortable_deceleration

        self.politeness: float = politeness

        self.last_tick: float = time.time()

        # agent characteristics
        self.length = length

    def step(self) -> None:
        pass

    def advance(self) -> None:
        current_time = time.time()
        delta_t = current_time - self.last_tick
        self.speed += self.acceleration * delta_t
        self.pos += self.speed * delta_t
        self.last_tick = current_time
