import json
import math
import random
import time

from bisect import bisect_left, insort_left
from scipy.stats import norm

import numpy as np
from kafka import KafkaProducer
from mesa import Model
from mesa.time import SimultaneousActivation

from model.idm import calculate_idm_accelerations, calculate_idm_free_accelerations
from model.road_network import RoadNetwork
from model.idm_vehicle_agent import IDMVehicleAgent


def json_serializer(input_dict: dict[str, any]):
    json_str = json.dumps(input_dict)
    return bytes(json_str, 'utf-8')


class IDMModel(Model):
    def __init__(self, max_vehicles=2000, lane_safety_critical_accel=-1.5, lane_switch_accel_threshold=0.5,
                 critical_obligatory_lane_change_dist=100):
        super().__init__()
        self.road_network = RoadNetwork(25.6759, 25.6682, -100.3481, -100.3582)
        self.schedule = SimultaneousActivation(self)
        self._kafka_producer = KafkaProducer(bootstrap_servers='localhost:9092', value_serializer=json_serializer)

        self.max_vehicles = max_vehicles

        self.lane_safety_critical_accel = lane_safety_critical_accel
        self.lane_switch_accel_threshold = lane_switch_accel_threshold
        self.critical_obligatory_lane_change_dist = critical_obligatory_lane_change_dist

        # vehicle listing
        self._vehicles: dict[int, IDMVehicleAgent] = {}

        # route values
        self._vehicle_routes: dict[int, list[int]] = {}
        self._vehicle_route_segment: dict[int, int] = {}

        # lane values
        self._vehicle_lanes: dict[int, int] = {}
        self._vehicle_target_lanes: dict[int, int | None] = {}

        self._road_lanes_vehicles: dict[
            tuple[int, int], list[
                list[int]]] = {}  # map of roads to lanes to vehicles in that lane, sorted by VehicleAgent.pos
        self._vehicle_roads: dict[int, tuple[int, int]] = {}  # vehicle ids to road ids

        for road in self.road_network.roads():
            road_id = (road[0], road[1])
            self._road_lanes_vehicles[road_id] = []
            lane_vehicles = self._road_lanes_vehicles[road_id]
            for _ in range(self.road_network.lane_count(road_id)):
                lane_vehicles.append([])

        self._next_id = 0
        self._last_spawn_time = time.time()
        self._last_lane_switch_step = time.time()

    def _vehicle_road_position_key(self, vehicle_id: int) -> float:
        return self._vehicles[vehicle_id].pos

    def _free_vehicle_filter(self, vehicle: IDMVehicleAgent) -> bool:
        """
        Returns true if the vehicle is free, it does not have any other vehicle in front
        :param vehicle:
        :return:
        """
        road_id = self._vehicle_roads[vehicle.unique_id]
        road_lane_vehicles = self._road_lanes_vehicles[road_id]
        vehicle_lane = self._vehicle_lanes[vehicle.unique_id]
        lane_vehicles = road_lane_vehicles[vehicle_lane]
        return lane_vehicles.index(vehicle.unique_id) == (len(lane_vehicles) - 1)

    def _vehicle_lane_index(self, vehicle: IDMVehicleAgent) -> int:
        road_id = self._vehicle_roads[vehicle.unique_id]
        road_lane_vehicles = self._road_lanes_vehicles[road_id]
        vehicle_lane = self._vehicle_lanes[vehicle.unique_id]
        lane_vehicles = road_lane_vehicles[vehicle_lane]
        return lane_vehicles.index(vehicle.unique_id)

    def _add_vehicle(self):
        route = None
        while route is None:
            entry_node = random.choice(self.road_network.entry_nodes)
            exit_node = random.choice(self.road_network.exit_nodes)
            route = self.road_network.shortest_path(entry_node, exit_node)

        initial_road = (route[0], route[1])

        # all values in base metric, e.g. 80 km/h to 22.22 m/s
        # using a normal distribution
        desired_speed = norm.rvs(loc=22.22, scale=5.0)
        minimum_safety_gap = norm.rvs(loc=1.5, scale=0.75)
        time_safety_gap = norm.rvs(loc=1.0, scale=0.25)
        maximum_acceleration = norm.rvs(loc=2.0, scale=0.8)
        comfortable_deceleration = norm.rvs(loc=1.5, scale=0.5)
        politeness = norm.rvs(loc=0.5, scale=0.5)

        new_vehicle = IDMVehicleAgent(self._next_id, self, 1.0, 2.0, desired_speed, minimum_safety_gap, time_safety_gap,
                                      maximum_acceleration, comfortable_deceleration, politeness)
        self._next_id += 1
        self._vehicles[new_vehicle.unique_id] = new_vehicle

        self._vehicle_routes[new_vehicle.unique_id] = route
        self._vehicle_route_segment[new_vehicle.unique_id] = 0

        if len(route) > 2:
            self._vehicle_target_lanes[new_vehicle.unique_id] = self.road_network.lanes_to(initial_road, route[2])[0]
        else:
            self._vehicle_target_lanes[new_vehicle.unique_id] = None

        self._place_vehicle(new_vehicle, initial_road, 0)

        self.schedule.add(new_vehicle)

    def _remove_vehicle(self, vehicle_id: int):
        print("removed vehicle")
        road_id = self._vehicle_roads[vehicle_id]
        road_lane_vehicles = self._road_lanes_vehicles[road_id]
        vehicle_lane = self._vehicle_lanes[vehicle_id]
        lane_vehicles = road_lane_vehicles[vehicle_lane]

        self._vehicle_routes.pop(vehicle_id)
        self._vehicle_route_segment.pop(vehicle_id)
        self._vehicle_target_lanes.pop(vehicle_id)
        self._vehicle_lanes.pop(vehicle_id)
        lane_vehicles.remove(vehicle_id)
        self._vehicle_roads.pop(vehicle_id)
        self._vehicles.pop(vehicle_id)

    def _change_vehicle_lane(self, vehicle: IDMVehicleAgent, new_lane: int, new_idx: int):
        if new_lane < 0:
            raise ValueError
        vehicle_id = vehicle.unique_id
        current_lane = self._vehicle_lanes[vehicle_id]
        road_id = self._vehicle_roads[vehicle_id]

        print(f'vehicle #{vehicle_id} changing from lane {current_lane} to {new_lane}')

        lane_vehicles = self._road_lanes_vehicles[road_id][current_lane]
        lane_vehicles.remove(vehicle.unique_id)

        new_lane_vehicles = self._road_lanes_vehicles[road_id][new_lane]
        new_lane_vehicles.insert(new_idx, vehicle_id)
        self._vehicle_lanes[vehicle_id] = new_lane

    def _place_vehicle(self, vehicle: IDMVehicleAgent, road_id: tuple[int, int], lane: int):
        vehicle.pos = 0.0

        if vehicle.unique_id in self._vehicle_roads:
            old_road_id = self._vehicle_roads[vehicle.unique_id]
            road_lanes_vehicles = self._road_lanes_vehicles[old_road_id]
            old_lane = self._vehicle_lanes[vehicle.unique_id]
            lane_vehicles = road_lanes_vehicles[old_lane]

            lane_vehicles.remove(vehicle.unique_id)

        self._vehicle_lanes[vehicle.unique_id] = lane
        self._vehicle_roads[vehicle.unique_id] = road_id
        road_lane_vehicles = self._road_lanes_vehicles[road_id]
        lane_vehicles = road_lane_vehicles[lane]

        insort_left(lane_vehicles, vehicle.unique_id, key=self._vehicle_road_position_key)

    def _free_vehicles_step(self):
        free_vehicles = list(filter(self._free_vehicle_filter, self._vehicles.values()))
        if len(free_vehicles) > 0:
            vehicle_speeds = np.stack(vehicle.speed for vehicle in free_vehicles)
            desired_speeds = np.stack(vehicle.desired_speed for vehicle in free_vehicles)
            maximum_accelerations = np.stack(vehicle.maximum_acceleration for vehicle in free_vehicles)

            accelerations = calculate_idm_free_accelerations(vehicle_speeds, desired_speeds, maximum_accelerations)

            for idx, vehicle in enumerate(free_vehicles):
                vehicle.acceleration = accelerations[idx]

    def _limited_vehicles_step(self):
        vehicles = list(filter(lambda vehicle: not self._free_vehicle_filter(vehicle), self._vehicles.values()))
        if len(vehicles) > 0:
            # forgive me lord for what im about to do
            next_vehicles_ids = [
                self._road_lanes_vehicles[self._vehicle_roads[vehicle.unique_id]][
                    self._vehicle_lanes[vehicle.unique_id]][self._vehicle_lane_index(vehicle) + 1]
                for
                vehicle
                in vehicles]
            next_vehicles = [self._vehicles[vehicle_id] for vehicle_id in next_vehicles_ids]

            # ugh
            vehicle_positions = np.stack(vehicle.pos for vehicle in vehicles)
            vehicle_speeds = np.stack(vehicle.speed for vehicle in vehicles)
            next_vehicle_positions = np.stack(vehicle.pos for vehicle in next_vehicles)
            next_vehicle_speeds = np.stack(vehicle.pos for vehicle in next_vehicles)
            desired_speeds = np.stack(vehicle.desired_speed for vehicle in vehicles)
            minimum_safety_gaps = np.stack(vehicle.minimum_safety_gap for vehicle in vehicles)
            time_safety_gaps = np.stack(vehicle.time_safety_gap for vehicle in vehicles)
            maximum_accelerations = np.stack(vehicle.maximum_acceleration for vehicle in vehicles)
            comfortable_decelerations = np.stack(vehicle.comfortable_deceleration for vehicle in vehicles)

            accelerations = calculate_idm_accelerations(vehicle_positions, vehicle_speeds, next_vehicle_positions,
                                                        next_vehicle_speeds, desired_speeds, minimum_safety_gaps,
                                                        time_safety_gaps, maximum_accelerations,
                                                        comfortable_decelerations)

            for idx, vehicle in enumerate(vehicles):
                vehicle.acceleration = accelerations[idx]

    def _evalate_vehicle_accel_delta(self, vehicle: IDMVehicleAgent, lane_vehicles: list[int], lane_idx: int):
        if lane_idx + 2 < len(lane_vehicles):
            next_vehicle_idx = lane_idx + 2
            next_vehicle = self._vehicles[lane_vehicles[next_vehicle_idx]]
            old_follower_new_accel = calculate_idm_accelerations([vehicle.pos], [vehicle.speed],
                                                                 [next_vehicle.pos], [next_vehicle.speed],
                                                                 [vehicle.desired_speed],
                                                                 [vehicle.minimum_safety_gap],
                                                                 [vehicle.time_safety_gap],
                                                                 [vehicle.maximum_acceleration],
                                                                 [vehicle.comfortable_deceleration])
        else:
            old_follower_new_accel = calculate_idm_free_accelerations([vehicle.speed],
                                                                      [vehicle.desired_speed],
                                                                      [vehicle.maximum_acceleration])
        return old_follower_new_accel[0] - vehicle.acceleration

    def _is_lane_switch_safe(self, vehicle: IDMVehicleAgent, new_lane_vehicles: list[int], new_idx: int) -> bool:
        if len(new_lane_vehicles) != 0:
            # check if there would be a new follower
            if 0 < new_idx:
                new_follower_id = new_lane_vehicles[new_idx - 1]
                new_follower = self._vehicles[new_follower_id]
                new_follower_accel = calculate_idm_accelerations([new_follower.pos], [new_follower.speed],
                                                                 [vehicle.pos],
                                                                 [vehicle.speed], [new_follower.desired_speed],
                                                                 [new_follower.minimum_safety_gap],
                                                                 [new_follower.time_safety_gap],
                                                                 [new_follower.maximum_acceleration],
                                                                 [new_follower.comfortable_deceleration])
                # do the safety check
                return new_follower_accel[0] > self.lane_safety_critical_accel
        return True

    def _evaluate_lane_switch(self, vehicle: IDMVehicleAgent, direction=1):
        vehicle_id = vehicle.unique_id
        road_id = self._vehicle_roads[vehicle_id]
        road_lanes = self.road_network.lane_count(road_id)
        lane = self._vehicle_lanes[vehicle_id]
        new_lane = lane + direction

        if not (0 < new_lane < road_lanes):
            # no lane in this direction
            return

        road_lane_vehicles = self._road_lanes_vehicles[road_id]
        old_lane_vehicles = road_lane_vehicles[lane]
        new_lane_vehicles = road_lane_vehicles[new_lane]

        old_idx = self._vehicle_lane_index(vehicle)
        new_idx = bisect_left(new_lane_vehicles, vehicle_id, key=self._vehicle_road_position_key)

        old_follower: IDMVehicleAgent | None = None
        new_follower: IDMVehicleAgent | None = None

        # if there are vehicles in the new lane
        if not self._is_lane_switch_safe(vehicle, new_lane_vehicles, new_idx):
            print("is unsafe")
            # print("can't switch lane, new follower accel too big")
            return

        # passed safety check, execute MOBIL
        # get old follower
        if len(old_lane_vehicles) != 0 and 0 < old_idx:
            old_follower_id = old_lane_vehicles[old_idx - 1]
            old_follower = self._vehicles[old_follower_id]

        # values for current vehicle
        old_accel = vehicle.acceleration
        if old_idx < len(old_lane_vehicles) - 1:
            next_vehicle_id = old_lane_vehicles[old_idx]
            next_vehicle = self._vehicles[next_vehicle_id]
            new_accel = calculate_idm_accelerations([vehicle.pos], [vehicle.speed], [next_vehicle.pos],
                                                    [next_vehicle.speed], [vehicle.desired_speed],
                                                    [vehicle.minimum_safety_gap], [vehicle.time_safety_gap],
                                                    [vehicle.maximum_acceleration],
                                                    [vehicle.comfortable_deceleration])
        else:
            new_accel = calculate_idm_free_accelerations([vehicle.speed], [vehicle.desired_speed],
                                                         [vehicle.maximum_acceleration])

        selfish_factor = new_accel - old_accel

        cooperative_factor = 0.0

        if old_follower is not None:
            cooperative_factor += self._evalate_vehicle_accel_delta(old_follower, old_lane_vehicles, old_idx - 1)
        if new_follower is not None:
            cooperative_factor += self._evalate_vehicle_accel_delta(new_follower, new_lane_vehicles, new_idx - 1)

        accels_factor = selfish_factor[0] + vehicle.politeness * cooperative_factor

        target_lane = self._vehicle_target_lanes[vehicle_id]
        road_length = self.road_network.road_length(road_id)
        distance = road_length - vehicle.pos
        if target_lane is not None and distance < self.critical_obligatory_lane_change_dist:
            current_lane = self._vehicle_lanes[vehicle_id]
            delta_lanes = target_lane - current_lane
            if delta_lanes > 0:
                multiplier = 1
            elif delta_lanes < 0:
                multiplier = -1
            else:
                multiplier = 0

            exp_threshold = math.exp(self.lane_switch_accel_threshold)
            inner = (distance * (1 - exp_threshold)) / self.critical_obligatory_lane_change_dist + exp_threshold
            target_lane_factor = multiplier * math.log(inner)
        else:
            target_lane_factor = 0.0

        switch_criterion = accels_factor + target_lane_factor * direction

        if switch_criterion > self.lane_switch_accel_threshold:
            self._change_vehicle_lane(vehicle, lane + direction, new_idx)

    def _lane_switch_step(self):
        current_time = time.time()
        if current_time - self._last_lane_switch_step < 2.0:
            return
        self._last_lane_switch_step = current_time
        for vehicle in self._vehicles.values():
            # right lane
            self._evaluate_lane_switch(vehicle)
            # left lane
            self._evaluate_lane_switch(vehicle, -1)

    def _road_end_step(self):
        vehicles_to_remove: list[int] = []
        for vehicle_id, vehicle in self._vehicles.items():
            road_id = self._vehicle_roads[vehicle_id]
            road_length = self.road_network.road_length(road_id)
            if vehicle.pos > road_length:
                route = self._vehicle_routes[vehicle.unique_id]
                self._vehicle_route_segment[vehicle.unique_id] += 1
                route_idx = self._vehicle_route_segment[vehicle.unique_id]
                # if we're at the end of the road
                if route_idx > len(route) - 3:
                    vehicles_to_remove.append(vehicle_id)
                else:  # we have at least one segment to go
                    current_lane_idx = self._vehicle_lanes[vehicle_id]
                    current_lane = self.road_network.lanes(self._vehicle_roads[vehicle_id])[current_lane_idx]
                    # find the output lane for the output node
                    current_road_end_node = route[route_idx]
                    next_end_node = route[route_idx + 1]
                    next_road = (current_road_end_node, next_end_node)
                    if current_lane_idx == self._vehicle_target_lanes[vehicle_id]:
                        next_lane = next(
                            lane for out_node, lane in current_lane.next_nodes if out_node == next_end_node)
                    else:
                        next_lane = 0
                        print(
                            f"vehicle #{vehicle.unique_id} missed its exit! on lane {current_lane_idx} but should be in {self._vehicle_target_lanes[vehicle_id]}")
                    self._place_vehicle(vehicle, next_road, next_lane)

                    possible_lanes = self.road_network.lanes_to(next_road, route[route_idx + 2])
                    target_lane = min(possible_lanes, key=lambda lane, cur_lane=current_lane_idx: abs(lane - cur_lane))
                    self._vehicle_target_lanes[vehicle_id] = target_lane

        for vehicle_id in vehicles_to_remove:
            self._remove_vehicle(vehicle_id)

    def step(self) -> None:
        current_time = time.time()
        delta_spawn_t = current_time - self._last_spawn_time

        probability = 2 * delta_spawn_t

        if len(self._vehicles) < self.max_vehicles and probability > random.random():
            self._last_spawn_time = current_time
            self._add_vehicle()
            # print("spawned vehicle")

        self._lane_switch_step()

        self._free_vehicles_step()
        self._limited_vehicles_step()

        self.schedule.step()

        for road_id, road_lanes_vehicles in self._road_lanes_vehicles.items():
            for lane_vehicles in road_lanes_vehicles:
                # always ensure this list is sorted, vehicle steps might have changed that
                lane_vehicles.sort(key=self._vehicle_road_position_key)

        self._road_end_step()

        for vehicle in self._vehicles.values():
            lane_width = 1.5
            road_id = self._vehicle_roads[vehicle.unique_id]
            road_lanes = self.road_network.lane_count(road_id)

            offset = (road_lanes // 2)
            if road_lanes % 2 != 0:
                offset += 0.5

            offset -= road_lanes
            offset *= lane_width

            current_lane = self._vehicle_lanes[vehicle.unique_id]
            offset += current_lane * lane_width

            road_direction = self.road_network.direction_vector(road_id)
            road_normal = self.road_network.normal_vector(road_id)
            car_pos = self.road_network.node_position(road_id[0]) + vehicle.pos * road_direction + offset * road_normal
            self._kafka_producer.send('cars', {
                'id': vehicle.unique_id,
                'x': car_pos[0],
                'y': car_pos[1],
            })
