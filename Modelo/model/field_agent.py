import numpy as np
from mesa import Agent

from model.state_producer_agent import StateProducerAgent


class FieldAgent(StateProducerAgent):
    FIELD_COLOURS = ('olive', 'dark_green', 'brown')

    def __init__(self, unique_id, model):
        super().__init__(unique_id, model)
        self.colour = self.random.choice(self.FIELD_COLOURS)

    def dump_state(self) -> dict[str, any]:
        return {
            'id': self.unique_id,
            'x': self.pos[0],
            'y': self.pos[1],
        }

    def step(self):
        if np.random.rand() < 0.1:
            self.colour = self.random.choice(self.FIELD_COLOURS)
