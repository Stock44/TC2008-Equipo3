import time

import numpy as np
from mesa import Agent, Model



class VehicleAgent(Agent):
    def __init__(self, unique_id: int, model: Model, road_network: "RoadNetwork", target_node: int, width: float, length: float):
        # agent init
        super().__init__(unique_id, model)
        self.road_network = road_network

        # agent global centroid position
        self.pos: np.ndarray = np.zeros(3)

        # road specific data
        self.road_id: tuple[int, int] = (0, 0)
        self.velocity: np.ndarray = np.zeros(3)
        self.acceleration: np.ndarray = np.zeros(3)
        self.road_pos: float = 0.0
        self.lane: int = 0

        self.target_node = target_node

        self.last_execution: float = time.time()

        # agent characteristics
        self.length = length
        self.width = width
