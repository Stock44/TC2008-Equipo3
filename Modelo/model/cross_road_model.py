import numpy as np
import random

from mesa import Model
from mesa.time import SimultaneousActivation
from mesa.space import SingleGrid
from mesa.datacollection import DataCollector

from m3_model.direction import Direction, RoadOrientation
from m3_model.field_agent import FieldAgent
from m3_model.traffic_light_agent import TrafficLightAgent, TrafficLightColor
from m3_model.car_agent import CarAgent


class CrossRoadModel(Model):
    """A model with some number of agents."""

    def __init__(self, num_agents=10, half_length=10, traffic_time=10, road_lanes=3):
        super().__init__()

        self._next_id = 0

        self.num_agents = num_agents
        self.running = True

        self.road_lanes: int = road_lanes

        # Dimensions are double of given values
        self.centre_bounds = (half_length - 1, half_length + 1)
        self.width = half_length * 2
        self.height = half_length * 2

        self.grid = SingleGrid(self.width, self.height, True)
        self.schedule = SimultaneousActivation(self)
        self.traffic_time = traffic_time
        self.traffic_lights: dict[Direction, TrafficLightAgent] = {}

        # limits of each road (first cell in road, last cell in road)
        self.h_road_boundary = (half_length - road_lanes, half_length + road_lanes - 1)
        self.v_road_boundary = (half_length - road_lanes, half_length + road_lanes - 1)

        # position of each traffic light
        self.traffic_light_positions: dict[Direction, tuple[int, int]] = {
            Direction.UP: (half_length + road_lanes, half_length + road_lanes),
            Direction.RIGHT: (half_length + road_lanes, half_length - road_lanes - 1),
            Direction.DOWN: (half_length - road_lanes - 1, half_length - road_lanes - 1),
            Direction.LEFT: (half_length - road_lanes - 1, half_length + road_lanes),
        }

        self.turn_squares: dict[Direction, tuple[tuple[int, int], tuple[int, int]]] = {
            Direction.UP: (
                (half_length, half_length),
                (half_length + road_lanes - 1, half_length - road_lanes),
            ),
            Direction.DOWN: (
                (half_length - 1, half_length - 1),
                (half_length - road_lanes, half_length + road_lanes - 1),
            ),
            Direction.RIGHT: (
                (half_length, half_length - 1),
                (half_length - road_lanes, half_length - road_lanes),
            ),
            Direction.LEFT: (
                (half_length - 1, half_length),
                (half_length + road_lanes - 1, half_length + road_lanes - 1),
            ),
        }

        self.turns: dict[Direction, tuple[Direction, Direction]] = {
            Direction.UP: (Direction.LEFT, Direction.RIGHT),
            Direction.DOWN: (Direction.RIGHT, Direction.LEFT),
            Direction.LEFT: (Direction.DOWN, Direction.UP),
            Direction.RIGHT: (Direction.UP, Direction.DOWN),
        }

        # Create traffic light agents
        for direction, position in self.traffic_light_positions.items():
            traffic_light = TrafficLightAgent(self._next_id, self, red_duration=45, step_offset=direction * 15)
            if direction == 0:
                traffic_light.color = TrafficLightColor.GREEN

            self._next_id += 1
            self.schedule.add(traffic_light)
            self.traffic_lights[direction] = traffic_light
            self.grid.place_agent(traffic_light, position)

        # Create field agents
        for cell in self.grid.coord_iter():
            _, x, y = cell

            # only place a Field agent if not within the road boundaries
            in_horizontal_lane = self.h_road_boundary[0] <= y <= self.h_road_boundary[1]
            in_vertical_lane = self.v_road_boundary[0] <= x <= self.v_road_boundary[1]
            if not in_horizontal_lane and not in_vertical_lane and self.grid.is_cell_empty((x, y)):
                field = FieldAgent(self._next_id, self)
                self._next_id += 1
                self.schedule.add(field)
                self.grid.place_agent(field, (x, y))

        sections = [
            ((half_length - road_lanes, 0), (half_length + road_lanes, half_length - road_lanes)),
            ((half_length - road_lanes, half_length + road_lanes), (half_length + road_lanes, half_length * 2)),
            ((0, half_length - road_lanes), (half_length - road_lanes, half_length + road_lanes)),
            ((half_length + road_lanes, half_length - road_lanes), (half_length * 2, half_length + road_lanes)),
        ]

        orientations = [
            RoadOrientation.VERTICAL,
            RoadOrientation.VERTICAL,
            RoadOrientation.HORIZONTAL,
            RoadOrientation.HORIZONTAL,
        ]

        # two halves of vertical road
        for (corner1, corner2), direction in zip(sections, orientations):
            self._add_random_car_agents(corner1, corner2, direction)

        self.datacollector = DataCollector(
            model_reporters={"Grid": lambda _: self.get_grid_as_array(),
                             "Waiting": lambda _: self.count_waiting_agents(),
                             "Running": lambda _: self.count_running_agents()}
        )

    def _add_random_car_agents(self, corner1: tuple[int, int], corner2: tuple[int, int], orientation: RoadOrientation,
                               probability: float = 0.95):
        rng = np.random.default_rng(4812821)
        x1, y1 = corner1
        x2, y2 = corner2

        tile_probabilities = rng.random(size=(x2 - x1, y2 - y1))
        h_it = np.nditer(tile_probabilities, flags=['multi_index'])
        for tile_probability in h_it:
            if tile_probability < probability:
                continue
            x, y = h_it.multi_index
            pos = (x1 + x, y1 + y)
            if not self.grid.is_cell_empty(pos):
                continue
            if orientation is RoadOrientation.VERTICAL:
                direction = Direction.DOWN if x < self.road_lanes else Direction.UP
            else:
                direction = Direction.RIGHT if y < self.road_lanes else Direction.LEFT
            car = CarAgent(self._next_id, self, direction)
            self._next_id += 1

            self.schedule.add(car)

            self.grid.place_agent(car, pos)

    def step(self):
        self.datacollector.collect(self)
        self.schedule.step()

    def count_waiting_agents(self):
        total_waiting_time = 0

        # Por todas las celdas del grid
        for cell in self.grid.coord_iter():
            agent, x, y = cell
            if isinstance(agent, CarAgent):
                pass
                # total_waiting_time += agent.waiting

        return total_waiting_time

    def count_running_agents(self):
        return self.num_agents - self.count_waiting_agents()

    def get_grid_as_array(self):
        grid = np.zeros((self.grid.width, self.grid.height))

        # Por todas las celdas del grid
        for cell in self.grid.coord_iter():
            agent, x, y = cell

            if isinstance(agent, CarAgent):
                # if agent.colour == 'orange':
                #     grid[x][y] = 6
                # elif agent.colour == 'blue':
                #     grid[x][y] = 7
                # elif agent.colour == 'purple':
                #     grid[x][y] = 8
                # else:  # black
                grid[x][y] = 9

            elif isinstance(agent, FieldAgent):
                if agent.colour == 'brown':
                    grid[x][y] = 3
                elif agent.colour == 'olive':
                    grid[x][y] = 4
                else:  # dark green
                    grid[x][y] = 5

            elif isinstance(agent, TrafficLightAgent):
                grid[x][y] = agent.color
            else:  # Street
                grid[x][y] = 0

        return grid
