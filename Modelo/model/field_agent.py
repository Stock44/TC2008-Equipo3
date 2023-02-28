import numpy as np
from mesa import Agent


class FieldAgent(Agent):
    FIELD_COLOURS = ('olive', 'dark_green', 'brown')

    def __init__(self, unique_id, model):
        super().__init__(unique_id, model)
        self.colour = self.random.choice(self.FIELD_COLOURS)

    def step(self):
        if np.random.rand() < 0.1:
            self.colour = self.random.choice(self.FIELD_COLOURS)
