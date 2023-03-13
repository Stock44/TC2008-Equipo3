from math import floor
from typing import Optional
import networkx as nx
import numpy as np
import osmnx as ox
import osmnx.plot
import osmnx.settings
from kafka import KafkaProducer
from scipy.spatial.distance import cdist
from dataclasses import dataclass, field
from bisect import insort_left

from model.idm_vehicle_agent import IDMVehicleAgent

ox.settings.use_cache = True
ox.settings.useful_tags_way += ['layer', 'turn', 'turn:lanes']

# lane, position, agent_id
VehicleInfo = list[int, float, int]


@dataclass
class Lane:
    next_nodes: list[tuple[int, int]] = field(default_factory=list)  # pair of node_id and lane no.


def iterate_from_edges(lst: list):
    try:
        half_length: int = len(lst) // 2
        for idx in range(half_length):
            yield lst[idx]
            yield lst[len(lst) - 1 - half_length]
    except IndexError:
        raise StopIteration


class RoadNetwork:
    def __init__(self, north, south, east, west):
        # initialize and project lat and lon to coords
        self._road_graph = ox.graph_from_bbox(north, south, east, west, network_type='drive', clean_periphery=True, simplify=False)

        center_meridian = (west + east) / 2
        center_parallel = (north + south) / 2

        # project network to transverse mercator projection with
        # origin at the center meridian and parallel of bounding box
        crs_string = '+proj=tmerc +lat_0=%f +lon_0=%f +k_0=1 +x_0=0 +y_0=0 +ellps=WGS84 +datum=WGS84 +units=m +no_defs'
        self._road_graph = ox.project_graph(self._road_graph, to_crs=crs_string % (center_parallel, center_meridian))

        self._vehicles: dict[int, IDMVehicleAgent] = dict()

        # gather exit and entry nodes
        self.exit_nodes = []
        self.entry_nodes = []
        for node in self._road_graph.nodes(data=True):
            # pack coordinates into numpy array
            node_id = node[0]
            data = node[1]
            data['pos'] = np.asarray([data['x'], data['y'], 0.0])

            # add to exit and entry nodes, if applicable
            if self._road_graph.out_degree(node_id) == 0:
                self.exit_nodes.append(node_id)
                data['endpoint'] = 2
            elif self._road_graph.in_degree(node_id) == 0:
                self.entry_nodes.append(node_id)
                data['endpoint'] = 1
            else:
                data['endpoint'] = 0

        self._add_road_info()
        self._add_lane_connections()

    def send_to_kafka(self, producer: KafkaProducer):
        for road in self._road_graph.edges(data=True):
            road_id = (road[0], road[1])
            start_pos = self.node_position(road[0])
            end_pos = self.node_position(road[1])
            producer.send('roads', {
                'start_x': start_pos[0],
                'start_y': start_pos[1],
                'end_x': end_pos[0],
                'end_y': end_pos[1],
                'length': self.road_length(road_id),
                'lane_count': self.lane_count(road_id),
            })

    def _add_road_info(self):
        # add vehicle info to each edge
        for road in self._road_graph.edges(data=True):
            data = road[2]

            # get lane counts
            if 'lanes' not in data:
                lane_count = 1
            elif isinstance(data['lanes'], list):
                lane_count = len(data['lanes'])
            elif isinstance(data['lanes'], str):
                lane_count = int(data['lanes'])
            else:
                lane_count = 1

            data['lane_count'] = lane_count
            data['lanes'] = []

            origin_pos = self._road_graph.nodes(data=True)[road[0]]['pos']
            target_pos = self._road_graph.nodes(data=True)[road[1]]['pos']

            # calculate out vertex direction orderings
            rel_positions: dict[int, np.ndarray] = {}
            for neighbor in self._road_graph.neighbors(road[1]):
                rel_positions[neighbor] = self._road_graph.nodes(data=True)[neighbor]['pos'] - origin_pos
                rel_positions[neighbor] = rel_positions[neighbor][:2]

            displacement = target_pos - origin_pos
            data['length'] = np.linalg.norm(displacement)
            perpendicular_displacement = np.cross([[0, 1], [-1, 0]], displacement[:2])

            data['out_node_ordering'] = []
            # add the sorted vertex direction orderings to the road
            for neighbor in self._road_graph.neighbors(road[1]):
                insort_left(data['out_node_ordering'], neighbor,
                            key=lambda neighbor: np.dot(rel_positions[neighbor], perpendicular_displacement))

            data['direction_vector'] = displacement / np.linalg.norm(displacement)
            data['normal_vector'] = np.cross(np.asarray([[0, 1], [-1, 0]]), data['direction_vector'][:2])
            data['normal_vector'] = np.append(data['normal_vector'], data['direction_vector'][2])

    def _1_to_1_lanes(self, intersection_node: int, out_node_ordering: list[int]):
        lanes = []
        for out_node_id in out_node_ordering:
            # map each lane of this out road
            for out_lane in range(self.lane_count((intersection_node, out_node_id))):
                lanes.append(Lane([(out_node_id, out_lane)]))

        return lanes

    def _1_to_1_lanes_centered(self, intersection_node: int, out_node_ordering: list[int], centered_lane_count: int,
                               total_lanes: int) -> (list[Lane], int):
        lane_offset = (total_lanes - centered_lane_count) // 2
        lanes = []
        # prepare in lanes
        for _ in range(lane_offset):
            lanes.append(Lane())

        lanes += self._1_to_1_lanes(intersection_node, out_node_ordering)

        for _ in range(total_lanes - centered_lane_count - lane_offset):
            lanes.append(Lane())

        return lanes, lane_offset

    def _add_lane_connections(self):
        roads = self._road_graph.edges(data=True)
        for origin, target, data in roads:
            in_lanes = data['lane_count']
            out_node_ordering = data['out_node_ordering']
            total_out_lanes = sum(
                [self.lane_count((target, out_node_id)) for out_node_id in out_node_ordering])

            lanes: list[Lane] = data['lanes']

            if total_out_lanes == 0:
                continue
            elif total_out_lanes == in_lanes:
                lanes = self._1_to_1_lanes(target, out_node_ordering)
                data['lanes'] = lanes
            elif total_out_lanes > in_lanes:
                # if there are more output lanes than input lanes
                widest_out_node_id = max(out_node_ordering,
                                         key=lambda out_node_id, intr_node=target: self.lane_count(
                                             (intr_node, out_node_id)))
                max_lane_count = self.lane_count((target, widest_out_node_id))
                widest_out_nodes_ids = list([node_id for node_id in out_node_ordering if
                                             self.lane_count((target, node_id)) == max_lane_count])
                midpoint = len(widest_out_nodes_ids) // 2
                central_out_node = widest_out_nodes_ids[midpoint]
                central_out_node_idx = out_node_ordering.index(central_out_node)

                # prepare in lanes
                if in_lanes <= max_lane_count:
                    lanes: list[Lane] = []

                    offset = (max_lane_count - in_lanes) // 2

                    for lane in range(in_lanes):
                        lanes.append(Lane([(central_out_node, lane + offset)]))

                else:  # in_lanes > max_lane_count

                    offset = (in_lanes - max_lane_count) // 2
                    for lane in range(total_out_lanes - in_lanes - offset):
                        lanes.append(Lane([]))
                    lanes += self._1_to_1_lanes(target, [central_out_node])

                for out_node_idx in range(0, central_out_node_idx):
                    lanes[0].next_nodes.append((out_node_ordering[out_node_idx], 0))

                for out_node_idx in range(central_out_node_idx + 1, len(out_node_ordering)):
                    lanes[-1].next_nodes.append((out_node_ordering[out_node_idx], 0))

                data['lanes'] = lanes
            else:  # total_out_lanes < lane_count
                # if there are more input lanes than output lanes

                # start in the central input lanes
                lanes, lane_offset = self._1_to_1_lanes_centered(target, out_node_ordering, total_out_lanes, in_lanes)

                # map extreme input lanes to extreme output roads
                # first map leftmost lanes to leftmost road
                for in_lane in range(lane_offset):
                    out_node_id = out_node_ordering[0]
                    lanes[in_lane].next_nodes.append((out_node_id, 0))

                # then map rightmost lanes to rightmost road
                for in_lane in range(lane_offset + total_out_lanes, in_lanes):
                    out_node_id = out_node_ordering[-1]
                    out_road_lanes = self.lane_count((target, out_node_id))
                    lanes[in_lane].next_nodes.append((out_node_id, out_road_lanes - 1))

                data['lanes'] = lanes

    def lanes(self, road_id: tuple[int, int]) -> list[Lane]:
        return self._road_graph[road_id[0]][road_id[1]][0]['lanes']

    def lanes_to(self, road_id: tuple[int, int], out_node: int) -> list[int]:
        # TODO maybe reimplement with a dict per road ?
        lanes = self.lanes(road_id)

        target_lanes = []
        for idx, lane in enumerate(lanes):
            for node, _ in lane.next_nodes:
                if node == out_node:
                    target_lanes.append(idx)

        return target_lanes

    def lane_count(self, road_id: tuple[int, int]) -> int:
        return self._road_graph[road_id[0]][road_id[1]][0]['lane_count']

    def roads(self):
        return self._road_graph.edges(data=True)

    def node_neighbors(self, node_id: int) -> list[int]:
        return self._road_graph.neighbors(node_id)

    # def advance_vehicle(self, vehicle: VehicleAgent, delta_t: float):
    #     displacement = vehicle.velocity * delta_t
    #     self._move_vehicle(vehicle, displacement)

    # def _move_vehicle(self, vehicle: VehicleAgent, displacement: np.ndarray):
    #     vehicle.pos += displacement
    #
    #     vehicle info at 1: position along a road's lane
    # road = self._road_graph[vehicle.road_id[0]][vehicle.road_id[1]]
    # vehicle_info = road[0]['vehicles']
    # vehicle_info_idx = vehicle_info.index([vehicle.lane, vehicle.road_pos, vehicle.unique_id])
    # vehicle_info[vehicle_info_idx][1] += np.linalg.norm(displacement)
    #
    # vehicle.road_pos = vehicle_info[vehicle_info_idx][1]

    # def change_road(self, vehicle: VehicleAgent, new_road_id: tuple[int, int]):
    #     old_road = self._road_graph[vehicle.road_id[0]][vehicle.road_id[1]]
    #     old_road[0]['vehicles'].remove([vehicle.lane, vehicle.road_pos, vehicle.unique_id])
    #     vehicle.velocity = np.zeros(3)
    #
    #     self.place_vehicle(vehicle, new_road_id, 0, 0.0)

    # def next_vehicle(self, vehicle: VehicleAgent) -> Optional[VehicleAgent]:
    #     road = self._road_graph[vehicle.road_id[0]][vehicle.road_id[1]]
    #     road_vehicles: SortedList[VehicleInfo] = road[0]['vehicles']
    #
    #     vehicle_info = [vehicle.lane, vehicle.road_pos, vehicle.unique_id]
    #
    #     next_vehicle_idx = road_vehicles.bisect_right(vehicle_info)
    #
    #     if next_vehicle_idx >= len(road_vehicles):
    #         return
    #
    #     next_vehicle_id = road_vehicles[next_vehicle_idx][2]
    #
    #     return self._vehicles[next_vehicle_id]

    def road_length(self, road_id: tuple[int, int]) -> float:
        return self._road_graph[road_id[0]][road_id[1]][0]['length']

    def normal_vector(self, road_id: tuple[int, int]) -> np.ndarray:
        return self._road_graph[road_id[0]][road_id[1]][0]['normal_vector']

    def direction_vector(self, road_id: tuple[int, int]) -> np.ndarray:
        return self._road_graph[road_id[0]][road_id[1]][0]['direction_vector']

    def _astar_heuristic(self, n1_id: int, n2_id: int):
        """
        Heuristic function fo A* algorithm. Uses euclidean distance between nodes.
        :param n1_id: first node
        :param n2_id: second node
        :return:
        """
        n1_pos = self._road_graph.nodes[n1_id]['pos']
        n2_pos = self._road_graph.nodes[n2_id]['pos']
        return cdist([n1_pos], [n2_pos])

    def shortest_path(self, n1_id: int, n2_id: int) -> Optional[list[int]]:
        try:
            return nx.astar_path(self._road_graph, n1_id, n2_id,
                                 heuristic=self._astar_heuristic)
        except nx.NetworkXNoPath:
            return None

    def node_position(self, node_id: int) -> np.ndarray:
        return self._road_graph.nodes(data=True)[node_id]['pos']

    def roadwise_position(self, road_id: tuple[int, int], position: float = 0.0, lane: int = 0) -> np.ndarray:
        """
        Get a 3D coordinate from a road, a distance traveled along the road, and the lane
        :param road_id:
        :param position:
        :param lane:
        :return:
        """
        direction = self.direction_vector(road_id)
        start_pos = self.node_position(road_id[0])

        return start_pos + direction * position

    # def place_vehicle(self, vehicle: VehicleAgent, road_id: tuple[int, int], lane: int = 0, position: float = 0.0):
    #     """
    #     Adds a vehicle agent to a particular spot in a road
    #     :param vehicle: vehicle agent
    #     :param road_id: id of the road, composed of road node enpoints' ids
    #     :param lane: lane in the road to it. The road must have enough lanes
    #     :param position: position along the road to put the agent. May be longer than the road
    #     :return:
    #     """
    #     road = self._road_graph[road_id[0]][road_id[1]]
    #
    #     if lane >= int(road[0]['lanes']) or lane < 0:
    #         raise RuntimeError("lane does not exist")
    #
    #     vehicle.road_pos = position
    #     vehicle.lane = lane
    #     vehicle.road_id = road_id
    #     vehicle.pos = self._road_graph.nodes(data=True)[road_id[0]]['pos']
    #
    #     if position != 0.0:
    #         direction = road['direction_vector']
    #         self._move_vehicle(vehicle, direction * position)
    #
    #     self._road_graph[road_id[0]][road_id[1]][0]['vehicles'].add([lane, position, vehicle.unique_id])
    #
    #     self._vehicles[vehicle.unique_id] = vehicle

    def plot(self):
        nc = ox.plot.get_node_colors_by_attr(self._road_graph, "endpoint", cmap="plasma")
        ox.plot_graph(self._road_graph, node_color=nc)


if __name__ == '__main__':
    network = RoadNetwork(25.6759, 25.6682, -100.3481, -100.3582)
    n1 = network.entry_nodes[0]
    n2 = network.exit_nodes[0]
    path = network.shortest_path(n1, n2)
    network.plot()
