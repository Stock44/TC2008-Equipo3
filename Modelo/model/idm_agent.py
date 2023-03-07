import time
from math import sqrt

import numpy as np
from mesa import Model

from model.road_network import RoadNetwork
from model.vehicle_agent import VehicleAgent



class IDMVehicleAgent(VehicleAgent):
    def __init__(self, unique_id: int, model: Model, road_network: RoadNetwork, target_node: int, width: float,
                 length: float,
                 desired_speed: float = 80, acceleration_reduction_factor: float = 4, minimum_safety_gap: float = 1,
                 time_safety_gap: float = 1, comfortable_deceleration: float = 1.5):
        super().__init__(unique_id, model, road_network, target_node, width, length)
        self._road_network = road_network

        self.desired_speed = desired_speed
        self.acceleration_reduction_factor = acceleration_reduction_factor
        self.minimum_safety_gap = minimum_safety_gap
        self.time_safety_gap = time_safety_gap
        self.comfortable_deceleration = comfortable_deceleration

        self._route: list[int] | None = None

        self._next_acceleration: float = 0.0

    def step(self) -> None:
        if self._route is None:
            self._route = self.road_network.shortest_path(self.road_id[0], self.target_node)


        speed_factor = (self.velocity / self.desired_speed) ** self.acceleration_reduction_factor

        next_vehicle = self._road_network.next_vehicle(self)
        if next_vehicle is not None:
            delta_velocity = self.velocity - next_vehicle.velocity

            dynamic_gap_factor = (self.velocity * delta_velocity) / (
                    2 * np.sqrt(self.acceleration * self.comfortable_deceleration))

            desired_gap = self.minimum_safety_gap + max(0.0, np.linalg.norm(
                self.velocity * self.time_safety_gap + dynamic_gap_factor))

            current_gap = next_vehicle.road_pos - self.road_pos

            gap_factor = (desired_gap / current_gap) ** 2
        else:
            gap_factor = 0.0

        self._next_acceleration = self.acceleration * (1 - speed_factor - gap_factor)

    def advance(self) -> None:
        current_time = time.time()
        delta_t = current_time - self.last_execution

        self.road_network.advance_vehicle(self, delta_t)

        self.velocity += self.acceleration * delta_t
        self.acceleration = self._next_acceleration

        # if we are at the end of the road
        if self.road_network.road_length(self.road_id) < self.road_pos:
            end_node_id = self.road_id[1]
            end_node_idx = self._route.index(end_node_id)
            # the old end is the new beginning
            self.road_network.change_node(self, (end_node_id, self._route[end_node_idx + 1]))

        self.last_execution = current_time
