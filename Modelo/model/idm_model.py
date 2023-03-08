import json
import random
import time

from bisect import bisect_left, insort_left

import numpy as np
from kafka import KafkaProducer
from mesa import Model
from mesa.time import SimultaneousActivation

from model.idm import calculate_idm_accelerations, calculate_idm_free_accelerations
from model.road_network import RoadNetwork
from model.vehicle_agent import VehicleAgent


def json_serializer(input_dict: dict[str, any]):
    json_str = json.dumps(input_dict)
    return bytes(json_str, 'utf-8')


class IDMModel(Model):
    def __init__(self, max_vehicles=500):
        super().__init__()
        self.road_network = RoadNetwork(25.6759, 25.6682, -100.3481, -100.3582)
        self.schedule = SimultaneousActivation(self)
        self._kafka_producer = KafkaProducer(bootstrap_servers='localhost:9092', value_serializer=json_serializer)

        self.max_vehicles = max_vehicles

        # vehicle listing
        self._vehicles: dict[int, VehicleAgent] = {}

        # route values
        self._vehicle_routes: dict[int, list[int]] = {}
        self._vehicle_route_segment: dict[int, int] = {}

        self._road_vehicles: dict[
            tuple[int, int], list[int]] = {}  # list of roads to vehicles, sorted by VehicleAgent.pos
        self._vehicle_roads: dict[int, tuple[int, int]] = {}  # vehicle ids to road ids

        for road in self.road_network.roads():
            self._road_vehicles[(road[0], road[1])] = []

        self._next_id = 0
        self._last_spawn_time = time.time()

    def _vehicle_road_position_key(self, vehicle_id: int) -> float:
        return self._vehicles[vehicle_id].pos

    def _free_vehicle_filter(self, vehicle: VehicleAgent) -> bool:
        """
        Returns true if the vehicle is free, it does not have any other vehicle in front
        :param vehicle:
        :return:
        """
        road_vehicles = self._road_vehicles[self._vehicle_roads[vehicle.unique_id]]
        vehicle_idx = road_vehicles.index(vehicle.unique_id)
        return vehicle_idx == (len(road_vehicles) - 1)

    def _vehicle_road_index(self, vehicle: VehicleAgent) -> int:
        road_id = self._vehicle_roads[vehicle.unique_id]
        return self._road_vehicles[road_id].index(vehicle.unique_id)

    def _add_vehicle(self):
        route = None
        while route is None:
            entry_node = random.choice(self.road_network.entry_nodes)
            exit_node = random.choice(self.road_network.exit_nodes)
            route = self.road_network.shortest_path(entry_node, exit_node)

        new_vehicle = VehicleAgent(self._next_id, self, 1.0, 2.0)
        self._next_id += 1
        self._vehicles[new_vehicle.unique_id] = new_vehicle
        self._vehicle_routes[new_vehicle.unique_id] = route
        self._vehicle_route_segment[new_vehicle.unique_id] = 0
        self._place_vehicle(new_vehicle, (route[0], route[1]))

        self.schedule.add(new_vehicle)

    def _remove_vehicle(self, vehicle):
        print("removed vehicle")
        road_id = self._vehicle_roads[vehicle.unique_id]

        self._vehicle_routes.pop(vehicle.unique_id)
        self._vehicle_route_segment.pop(vehicle.unique_id)

        road_vehicles = self._road_vehicles[road_id]
        road_vehicles.remove(vehicle.unique_id)
        self._vehicle_roads.pop(vehicle.unique_id)
        self._vehicles.pop(vehicle.unique_id)

    def _place_vehicle(self, vehicle: VehicleAgent, road_id: tuple[int, int]):
        vehicle.pos = 0.0

        if vehicle.unique_id in self._vehicle_roads:
            old_road_id = self._vehicle_roads[vehicle.unique_id]
            road_vehicles = self._road_vehicles[old_road_id]
            road_vehicles.remove(vehicle.unique_id)

        self._vehicle_roads[vehicle.unique_id] = road_id
        insort_left(self._road_vehicles[road_id], vehicle.unique_id, key=self._vehicle_road_position_key)

    def _free_vehicles_step(self):
        free_vehicles = list(filter(self._free_vehicle_filter, self._vehicles.values()))
        if len(free_vehicles) > 0:
            vehicle_speeds = np.stack([vehicle.speed for vehicle in free_vehicles])

            accelerations = calculate_idm_free_accelerations(vehicle_speeds)

            for idx, vehicle in enumerate(free_vehicles):
                vehicle.acceleration = accelerations[idx]

    def _limited_vehicles_step(self):
        limited_vehicles = list(filter(lambda vehicle: not self._free_vehicle_filter(vehicle), self._vehicles.values()))
        if len(limited_vehicles) > 0:
            # forgive me lord for what im about to do
            next_vehicles_ids = [
                self._road_vehicles[self._vehicle_roads[vehicle.unique_id]][self._vehicle_road_index(vehicle) + 1] for
                vehicle
                in limited_vehicles]
            next_vehicles = [self._vehicles[vehicle_id] for vehicle_id in next_vehicles_ids]

            vehicle_positions = np.stack([vehicle.pos for vehicle in limited_vehicles])
            vehicle_speeds = np.stack([vehicle.speed for vehicle in limited_vehicles])
            next_vehicle_positions = np.stack([vehicle.pos for vehicle in next_vehicles])
            next_vehicle_speeds = np.stack([vehicle.pos for vehicle in next_vehicles])

            accelerations = calculate_idm_accelerations(vehicle_positions, vehicle_speeds, next_vehicle_positions,
                                                        next_vehicle_speeds)

            for idx, vehicle in enumerate(limited_vehicles):
                vehicle.acceleration = accelerations[idx]

    def step(self) -> None:
        current_time = time.time()
        delta_spawn_t = current_time - self._last_spawn_time

        probability = 0.5 * delta_spawn_t

        if len(self._vehicles) < self.max_vehicles and probability > random.random():
            self._last_spawn_time = current_time
            self._add_vehicle()
            print("spawned vehicle")

        self._free_vehicles_step()
        self._limited_vehicles_step()

        self.schedule.step()

        for road_id, road_vehicles in self._road_vehicles.items():
            road_length = self.road_network.road_length(road_id)

            # always ensure this list is sorted, vehicle steps might have changed that
            road_vehicles.sort(key=self._vehicle_road_position_key)

            for vehicle_id in road_vehicles:
                vehicle = self._vehicles[vehicle_id]
                if vehicle.pos > road_length:
                    print(f"switching road for vehicle #{vehicle.unique_id}")
                    route = self._vehicle_routes[vehicle.unique_id]
                    self._vehicle_route_segment[vehicle.unique_id] += 1
                    route_idx = self._vehicle_route_segment[vehicle.unique_id]
                    if route_idx == len(route) - 1:
                        self._remove_vehicle(vehicle)
                    else:
                        self._place_vehicle(vehicle, (route[route_idx], route[route_idx + 1]))

        for car in self._vehicles.values():
            road = self._vehicle_roads[car.unique_id]
            road_direction = self.road_network.direction_vector(road)
            car_pos = self.road_network.node_position(road[0]) + car.pos * road_direction
            self._kafka_producer.send('cars', {
                'id': car.unique_id,
                'x': car_pos[0],
                'y': car_pos[1],
            })


if __name__ == '__main__':
    model = IDMModel()
    while True:
        model.step()
        time.sleep(0.2)
