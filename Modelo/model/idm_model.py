import json
import math
import random
import time

from bisect import bisect_left, insort_left

import matplotlib.pyplot
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
    def __init__(self, max_vehicles=10000, lane_safety_critical_accel=-2.0, lane_switch_accel_threshold=1.0,
                 critical_obligatory_lane_change_dist=200.0, lane_width=4, vehicle_lookahead_distance=300.0):
        super().__init__()
        self.road_network = RoadNetwork(25.6759, 25.6682, -100.3481, -100.3582, lane_width=lane_width)
        self.schedule = SimultaneousActivation(self)
        self._kafka_producer = KafkaProducer(bootstrap_servers='localhost:9092', value_serializer=json_serializer)

        self.road_network.send_to_kafka(self._kafka_producer)

        self.max_vehicles = max_vehicles

        self.lane_safety_critical_accel = lane_safety_critical_accel
        self.lane_switch_accel_threshold = lane_switch_accel_threshold
        self.critical_obligatory_lane_change_dist = critical_obligatory_lane_change_dist
        self.vehicle_lookahead_distance = vehicle_lookahead_distance

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

        initial_lane = random.randint(0, self.road_network.lane_count(initial_road) - 1)

        # all values in base metric, e.g. 80 km/h to 22.22 m/s
        # using a normal distribution
        desired_speed = norm.rvs(loc=22.22, scale=5.0)
        minimum_safety_gap = norm.rvs(loc=1.5, scale=0.75)
        time_safety_gap = norm.rvs(loc=1.5, scale=0.25)
        maximum_acceleration = norm.rvs(loc=4.0, scale=1.5)
        comfortable_deceleration = norm.rvs(loc=3.0, scale=1.0)
        politeness = norm.rvs(loc=0.5, scale=0.3)

        new_vehicle = IDMVehicleAgent(self._next_id, self, 2.0, desired_speed, minimum_safety_gap, time_safety_gap,
                                      maximum_acceleration, comfortable_deceleration, politeness)
        self._next_id += 1
        self._vehicles[new_vehicle.unique_id] = new_vehicle

        self._vehicle_routes[new_vehicle.unique_id] = route
        self._vehicle_route_segment[new_vehicle.unique_id] = 0

        if len(route) > 2:
            self._vehicle_target_lanes[new_vehicle.unique_id] = self.road_network.lanes_to(initial_road, route[2])[0]
        else:
            self._vehicle_target_lanes[new_vehicle.unique_id] = None

        self._place_vehicle(new_vehicle, initial_road, initial_lane)

        self.schedule.add(new_vehicle)
        self._kafka_producer.send('vehicle_creations', value={
            'id': new_vehicle.unique_id,
        })

    def _remove_vehicle(self, vehicle_id: int):
        # print("removed vehicle")
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

        self._kafka_producer.send('vehicle_deletions', value={
            'id': vehicle_id,
        })

    def _change_vehicle_lane(self, vehicle: IDMVehicleAgent, new_lane: int, new_idx: int):
        vehicle_id = vehicle.unique_id
        road_id = self._vehicle_roads[vehicle_id]
        if new_lane < 0 or new_lane >= self.road_network.lane_count(road_id):
            raise ValueError
        current_lane = self._vehicle_lanes[vehicle_id]

        # print(f'vehicle #{vehicle_id} changing from lane {current_lane} to {new_lane}')

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
            vehicle_distances = np.stack(self.distance_to_next_vehicle(self._vehicle_roads[vehicle.unique_id],
                                                                       self._vehicle_lanes[vehicle.unique_id],
                                                                       vehicle.pos, vehicle.length) for vehicle in
                                         vehicles)
            vehicle_speeds = np.stack(vehicle.speed for vehicle in vehicles)
            next_vehicle_speeds = np.stack(vehicle.pos for vehicle in next_vehicles)
            desired_speeds = np.stack(vehicle.desired_speed for vehicle in vehicles)
            minimum_safety_gaps = np.stack(vehicle.minimum_safety_gap for vehicle in vehicles)
            time_safety_gaps = np.stack(vehicle.time_safety_gap for vehicle in vehicles)
            maximum_accelerations = np.stack(vehicle.maximum_acceleration for vehicle in vehicles)
            comfortable_decelerations = np.stack(vehicle.comfortable_deceleration for vehicle in vehicles)

            accelerations = calculate_idm_accelerations(vehicle_distances, vehicle_speeds,
                                                        next_vehicle_speeds, desired_speeds,
                                                        minimum_safety_gaps,
                                                        time_safety_gaps, maximum_accelerations,
                                                        comfortable_decelerations)

            for idx, vehicle in enumerate(vehicles):
                vehicle.acceleration = accelerations[idx]

    def _evalate_vehicle_accel_delta(self, vehicle: IDMVehicleAgent, lane_vehicles: list[int], lane_idx: int):
        if lane_idx + 2 < len(lane_vehicles):
            next_vehicle_idx = lane_idx + 2
            next_vehicle = self._vehicles[lane_vehicles[next_vehicle_idx]]
            old_follower_new_accel = calculate_idm_accelerations(
                [next_vehicle.pos - next_vehicle.length / 2 - (vehicle.pos + vehicle.length / 2)], [vehicle.speed],
                [next_vehicle.speed], [vehicle.desired_speed], [vehicle.minimum_safety_gap],
                [vehicle.time_safety_gap], [vehicle.maximum_acceleration], [vehicle.comfortable_deceleration])
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
                new_follower_accel = calculate_idm_accelerations(
                    [vehicle.pos - vehicle.length / 2 - (new_follower.pos + new_follower.length / 2)],
                    [new_follower.speed],
                    [vehicle.speed], [new_follower.desired_speed], [new_follower.minimum_safety_gap],
                    [new_follower.time_safety_gap], [new_follower.maximum_acceleration],
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

        if not (0 <= new_lane < road_lanes):
            # no lane in this direction
            return 0.0, 0

        road_lane_vehicles = self._road_lanes_vehicles[road_id]
        old_lane_vehicles = road_lane_vehicles[lane]
        new_lane_vehicles = road_lane_vehicles[new_lane]

        old_idx = self._vehicle_lane_index(vehicle)
        new_idx = bisect_left(new_lane_vehicles, vehicle_id, key=self._vehicle_road_position_key)

        old_follower: IDMVehicleAgent | None = None
        new_follower: IDMVehicleAgent | None = None

        # if there are vehicles in the new lane
        # if not self._is_lane_switch_safe(vehicle, new_lane_vehicles, new_idx):
        #     print("is unsafe")
        #     print("can't switch lane, new follower accel too big")
        #     return 0.0, 0

        # passed safety check, execute MOBIL
        # get old follower
        if 0 < old_idx <= (len(old_lane_vehicles) - 1):
            old_follower_id = old_lane_vehicles[old_idx - 1]
            old_follower = self._vehicles[old_follower_id]

        if 0 < new_idx < (len(new_lane_vehicles) - 1):
            new_follower_id = new_lane_vehicles[new_idx]
            new_follower = self._vehicles[new_follower_id]

        # values for current vehicle
        old_accel = vehicle.acceleration
        if old_idx < len(old_lane_vehicles) - 1:
            next_vehicle_id = old_lane_vehicles[old_idx + 1]
            next_vehicle = self._vehicles[next_vehicle_id]
            new_accel = calculate_idm_accelerations(
                [next_vehicle.pos - next_vehicle.length / 2 - (vehicle.pos + vehicle.length / 2)], [vehicle.speed],
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

            # exp_threshold = math.exp(self.lane_switch_accel_threshold)
            # inner = (distance * (1 - exp_threshold)) / self.critical_obligatory_lane_change_dist + exp_threshold
            target_lane_factor = 4 * self.lane_switch_accel_threshold * (
                1 - (distance / self.critical_obligatory_lane_change_dist) ** 2)
            if delta_lanes == 0:
                target_lane_factor *= -1
            else:
                target_lane_factor *= delta_lanes * direction
            print("vehicle: %d target: %d  current: %d  direction: %d factor: %f" % (
            vehicle_id, target_lane, current_lane, direction, target_lane_factor))
        else:
            target_lane_factor = 0.0

        switch_criterion = accels_factor + target_lane_factor
        print("vehicle %d criterion %f" % (vehicle_id, switch_criterion))

        return switch_criterion, new_idx

    def _lane_switch_step(self):
        current_time = time.time()
        if current_time - self._last_lane_switch_step < 1.0:
            return
        self._last_lane_switch_step = current_time
        for vehicle in self._vehicles.values():
            current_lane = self._vehicle_lanes[vehicle.unique_id]
            # right lane
            to_right_criterion, right_idx = self._evaluate_lane_switch(vehicle)
            # left lane
            to_left_criterion, left_idx = self._evaluate_lane_switch(vehicle, -1)

            if to_right_criterion > to_left_criterion and to_right_criterion > self.lane_switch_accel_threshold:
                print("vehicle: %d switching lane from %d to %d" % (vehicle.unique_id, current_lane, current_lane + 1))
                self._change_vehicle_lane(vehicle, current_lane + 1, right_idx)
            elif to_left_criterion > to_right_criterion and to_left_criterion > self.lane_switch_accel_threshold:
                print("vehicle: %d switching lane from %d to %d" % (vehicle.unique_id, current_lane, current_lane - 1))
                self._change_vehicle_lane(vehicle, current_lane - 1, right_idx)

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

    def distance_to_next_vehicle(self, road_id: tuple[int, int], lane_idx: int, pos: float, length: float):
        """
        Calculates the distance from a given position in a road's lane to the next vehicle, if any
        :param road_id:
        :param lane_idx:
        :param pos:
        :param length:
        :return:
        """
        current_lane_vehicles = self._road_lanes_vehicles[road_id][lane_idx]

        # try to find the first vehicle in the current lane that is ahead of us
        for vehicle_id in current_lane_vehicles:
            vehicle = self._vehicles[vehicle_id]
            if vehicle.pos > pos:
                return (vehicle.pos - vehicle.length / 2) - (pos + length / 2)

        # if we didn't find any we then start searching through the next vehicles, up to a maaximum lookahead
        distance = self.road_network.road_length(road_id) - (pos + length / 2)
        current_lane = self.road_network.lanes(road_id)[lane_idx]
        current_road_id = road_id
        while distance < self.vehicle_lookahead_distance:
            # switch over to the next road
            next_node, next_lane = current_lane.next_nodes[0]
            current_road_id = (current_road_id[1], next_node)
            current_lane_idx = next_lane
            current_lane_vehicles = self._road_lanes_vehicles[current_road_id][current_lane_idx]
            current_lane = self.road_network.lanes(current_road_id)[current_lane_idx]

            if len(current_lane_vehicles) == 0:
                if len(current_lane.next_nodes) == 0:
                    # there is nothing next, abort the search
                    break
                distance += self.road_network.road_length(current_road_id)
                # add the distance, continue searching
                continue

            # if there are vehicles in this lane, we have found a next vehicle
            next_vehicle_id = current_lane_vehicles[0]
            next_vehicle = self._vehicles[next_vehicle_id]
            distance += next_vehicle.pos - next_vehicle.length / 2
            if distance < 0:
                distance = 0.0
            return distance

        # no vehicle was found, returns maximum lookahead distance (in theory)
        return distance

    def step(self) -> None:
        current_time = time.time()
        delta_spawn_t = current_time - self._last_spawn_time

        probability = 50 * delta_spawn_t

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
            road_id = self._vehicle_roads[vehicle.unique_id]
            current_lane = self._vehicle_lanes[vehicle.unique_id]

            car_pos = self.road_network.roadwise_position(road_id, vehicle.pos, current_lane)
            direction = self.road_network.direction_vector(road_id)

            self._kafka_producer.send('vehicle_positions', value={
                'id': vehicle.unique_id,
                'x': car_pos[0],
                'y': car_pos[1],
                'z': car_pos[2],
                'x_direction': direction[0],
                'y_direction': direction[1],
                'z_direction': direction[2],
                'acceleration': vehicle.acceleration,
                'speed': vehicle.speed,
            })
