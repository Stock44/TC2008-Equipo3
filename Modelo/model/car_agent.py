from enum import IntEnum
from math import ceil, floor
import random

import numpy as np
from mesa import Agent

from typing import TYPE_CHECKING

from m3_model.traffic_light_agent import TrafficLightAgent, TrafficLightColor

if TYPE_CHECKING:
    from m3_model.cross_road_model import CrossRoadModel

from m3_model.direction import Direction, RoadOrientation


class CarAgent(Agent):

    def __init__(self, unique_id, model: 'CrossRoadModel', direction: Direction):
        super().__init__(unique_id, model)

        self._road_lanes = model.road_lanes
        self._grid = model.grid

        self._next_traffic_light: TrafficLightAgent = model.traffic_lights[direction]
        self._direction: Direction = direction
        self._x_speed = 0
        self._y_speed = 0

        self._wanted_direction: Direction | None = random.choice(self.get_possible_directions())

    def get_possible_directions(self):
        directions = set(Direction)
        if self._direction is Direction.UP:
            directions.discard(Direction.DOWN)
        elif self._direction is Direction.DOWN:
            directions.discard(Direction.UP)
        elif self._direction is Direction.RIGHT:
            directions.discard(Direction.LEFT)
        else:
            directions.discard(Direction.RIGHT)

        return list(directions)

    def accelerate(self):
        if self._direction in [Direction.UP, Direction.DOWN]:
            index = 1
        else:
            index = 0

        if self._direction in [Direction.RIGHT, Direction.UP]:
            multiplier = 1
            distance_to_stoplight = self._next_traffic_light.pos[index] - self._road_lanes * 2 - self.pos[index] - 1
        else:  # LEFT
            multiplier = -1
            distance_to_stoplight = self.pos[index] - self._next_traffic_light.pos[index] - self._road_lanes * 2 - 1

        if distance_to_stoplight < -self._road_lanes * 2 and self._wanted_direction is None:
            print(distance_to_stoplight)
            self.get_new_wanted_direction()

        if distance_to_stoplight < 0:
            distance_to_stoplight += self.model.width - self._road_lanes * 2

        if self._direction in [Direction.DOWN, Direction.UP]:
            self._y_speed += multiplier * self.calculate_acceleration(abs(self._y_speed), distance_to_stoplight)
        else:
            self._x_speed += multiplier * self.calculate_acceleration(abs(self._x_speed), distance_to_stoplight)

    def get_new_wanted_direction(self):
        self._wanted_direction: Direction | None = random.choice(self.get_possible_directions())
        print("new wanted direction %d" % self._wanted_direction)

    def calculate_acceleration(self, speed: int, distance_to_stoplight: int):
        if self._next_traffic_light.color is TrafficLightColor.YELLOW:
            # if 1 > speed >= distance_to_stoplight:
            #     return 1
            pass
        if self._next_traffic_light.color is TrafficLightColor.RED:
            if (0 < distance_to_stoplight <= 3) and speed > 0:
                print(distance_to_stoplight)
                return -floor(speed / distance_to_stoplight)
            if distance_to_stoplight <= 1:
                return 0

        if speed < 1:
            return 1
        elif speed > 1:
            return -1

        return 0

    @property
    def current_lane(self):
        if self._direction is Direction.UP:
            return self.pos[0] - (self.model.width / 2)
        elif self._direction is Direction.DOWN:
            return (self.model.width / 2) - self.pos[0] - 1
        elif self._direction is Direction.RIGHT:
            return (self.model.height / 2) - self.pos[1] - 1
        else:
            return self.pos[1] - (self.model.height / 2)

    def go_to_lane(self, target_lane: int):
        if self._x_speed == 0 and self._y_speed == 0:
            return

        # print("direction: %d  lane: %d  target: %d" % (self._direction, self.current_lane, self._wanted_direction))
        if self._direction in [Direction.UP, Direction.LEFT]:
            multiplier = 1
        else:
            multiplier = -1

        if self._direction in [Direction.UP, Direction.DOWN]:
            if self.current_lane != target_lane:
                self._x_speed = multiplier if self.current_lane < target_lane else -multiplier
            else:
                self._x_speed = 0
        else:
            if self.current_lane != target_lane:
                self._y_speed = multiplier if self.current_lane < target_lane else -multiplier
            else:
                self._y_speed = 0

    def change_lanes(self):
        if self._wanted_direction is self._direction:
            return
        if self._wanted_direction is self.model.turns[self._direction][0]:
            self.go_to_lane(0)
        elif self._wanted_direction is self.model.turns[self._direction][1]:
            self.go_to_lane(self._road_lanes - 1)
        elif self._wanted_direction is None:
            pass
        else:
            raise NotImplementedError("u turn not implemented")

    def try_turn(self):
        for idx, turn in enumerate(self.model.turns[self._direction]):
            if self._wanted_direction is turn and self.pos == self.model.turn_squares[self._direction][idx]:
                print("turning from %d to %d" % (self._direction, turn))
                self._direction = turn
                self._wanted_direction = None
                self._next_traffic_light = self.model.traffic_lights[turn]
                self._x_speed = 0
                self._y_speed = 0
                return

    def step(self):
        self.try_turn()
        self.change_lanes()
        self.accelerate()
        # if self._next_traffic_light.color is TrafficLightColor.RED:
        #     self.check_red_stoplight()
        # elif self._next_traffic_light.color is TrafficLightColor.YELLOW:
        #     self.check_yellow_stoplight()

        # if self._speed < 2:
        #     self._speed += 1
        #
        # if self.pos in self.model.centre and np.random.rand() < self.turning_rate:
        #     self.direction = self.model.possible_turns[self.direction][self.pos]
        #
        self.next_pos = (self.pos[0] + self._x_speed, self.pos[1] + self._y_speed)

        if self.model.grid.out_of_bounds(self.next_pos):
            self.next_pos = self.model.grid.torus_adj(self.next_pos)

        # print(self.pos, next_pos, self.direction, self.next_pos)

    def near_traffic_light(self):
        # if self.direction is Direction.UP:
        #     return self.pos[1] == self.model.traffic_light_positions[Direction.UP][1]
        # elif self.direction is Direction.DOWN:
        #     return self.pos[1] == self.model.traffic_light_positions[Direction.UP][1]
        # elif self.direction is Direction.LEFT:
        #     return self.pos[1] == self.model.traffic_light_positions[Direction.UP][1]
        # else: # RIGHT
        #     return self.pos[1] == self.model.traffic_light_positions[Direction.UP][1]
        return any([isinstance(obj, TrafficLightAgent) for obj in self.model.grid.get_neighbors(
            self.pos, moore=False, include_center=False)])

    # def is_before_crossroad(self):
    #     if self.direction == 'right':
    #         return self.pos[1] < self.model.centre_bounds[0]
    #     elif self.direction == 'left':
    #         return self.pos[1] > self.model.centre_bounds[1]
    #     elif self.direction == 'down':
    #         return self.pos[0] < self.model.centre_bounds[0]
    #     elif self.direction == 'up':
    #         return self.pos[0] > self.model.centre_bounds[1]

    def advance(self):
        # should_advance = not (self.is_before_crossroad() and self.near_traffic_light() and
        #                       self.model.traffic_lights[self.direction].colour == 'red')

        if self.model.grid.is_cell_empty(self.next_pos):
            self.model.grid.move_agent(self, self.next_pos)
