from typing import Optional

import networkx as nx
import numpy as np
import osmnx as ox
import osmnx.plot
import osmnx.settings
from scipy.spatial.distance import cdist
from dataclasses import dataclass
from bisect import insort_left

from model.vehicle_agent import VehicleAgent

ox.settings.use_cache = True
ox.settings.useful_tags_way += ['layer', 'turn', 'turn:lanes']

# lane, position, agent_id
VehicleInfo = list[int, float, int]


@dataclass
class Lane:
    end_node: int


class RoadNetwork:
    def __init__(self, north, south, east, west):
        # initialize and project lat and lon to coords
        self._road_graph = ox.graph_from_bbox(north, south, east, west, network_type='drive', clean_periphery=True)

        center_meridian = (west + east) / 2
        center_parallel = (north + south) / 2

        # project network to transverse mercator projection with
        # origin at the center meridian and parallel of bounding box
        crs_string = '+proj=tmerc +lat_0=%f +lon_0=%f +k_0=1 +x_0=0 +y_0=0 +ellps=WGS84 +datum=WGS84 +units=m +no_defs'
        self._road_graph = ox.project_graph(self._road_graph, to_crs=crs_string % (center_parallel, center_meridian))

        self._vehicles: dict[int, VehicleAgent] = dict()

        # gather exit and entry nodes
        self.exit_nodes = []
        self.entry_nodes = []
        for node in self._road_graph.nodes(data=True):
            # pack coordinates into numpy array
            node_id = node[0]
            data = node[1]
            data['pos'] = np.asarray([data['x'], data['y'], 0.0])

            if 'turn:lanes' in data:
                pass

            # add to exit and entry nodes, if applicable
            if self._road_graph.out_degree(node_id) == 0:
                self.exit_nodes.append(node_id)
                data['endpoint'] = 2
            elif self._road_graph.in_degree(node_id) == 0:
                self.entry_nodes.append(node_id)
                data['endpoint'] = 1
            else:
                data['endpoint'] = 0

        # add vehicle info to each edge
        for road in self._road_graph.edges(data=True):
            data = road[2]

            # get lane counts
            if 'lanes' not in data:
                data['lanes'] = 0
            elif isinstance(data['lanes'], list):
                data['lanes'] = len(data['lanes'])
            elif isinstance(data['lanes'], str):
                data['lanes'] = int(data['lanes'])

            origin_pos = self._road_graph.nodes(data=True)[road[0]]['pos']
            target_pos = self._road_graph.nodes(data=True)[road[1]]['pos']

            # calculate out vertex direction orderings
            endpoint_neighbors = self._road_graph.neighbors(road[1])
            rel_positions: dict[int, np.ndarray] = {}
            for neighbor in endpoint_neighbors:
                rel_positions[neighbor] = self._road_graph.nodes(data=True)[neighbor]['pos'] - origin_pos

            displacement = target_pos - origin_pos
            perpendicular_displacement = np.cross([[0, 1], [-1, 0]], displacement)

            data['out_vertex_ordering'] = []
            # add the sorted vertex direction orderings to the road
            for neighbor in endpoint_neighbors:
                insort_left(data['out_vertex_ordering'], neighbor,
                            key=lambda neighbor: np.dot(rel_positions[neighbor], perpendicular_displacement))

            data['direction_vector'] = displacement / np.linalg.norm(displacement)

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
