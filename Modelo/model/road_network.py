from typing import Optional
import networkx as nx
import numpy as np
import osmnx as ox
import osmnx.settings
from kafka import KafkaProducer
from scipy.spatial.distance import cdist
from dataclasses import dataclass, field

ox.settings.use_cache = True
ox.settings.useful_tags_way += ['layer', 'turn', 'turn:lanes']

NodeId = int
RoadSegmentId = int
RoadId = int


@dataclass
class Node:
    node_id: NodeId
    pos: np.ndarray


@dataclass
class RoadSegment:
    road_segment_id: RoadSegmentId
    start_node_id: NodeId
    end_node_id: NodeId
    road_id: RoadId
    direction: np.ndarray
    normal: np.ndarray
    length: float
    cumulative_length: float = 0.0


@dataclass
class Road:
    road_id: RoadId
    lanes: int
    length: float = 0.0
    segments: list[RoadSegmentId] = field(default_factory=list)
    intersecting_segment_lanes: dict[RoadSegmentId, list[tuple[int, int]]] = field(
        default_factory=dict)  # per target road_segment, list of pairs of this road lane and target road lane


class RoadNetwork:
    def __init__(self, north, south, east, west):
        # initialize and project lat and lon to coords
        self._road_graph = ox.graph_from_bbox(north, south, east, west, network_type='drive', clean_periphery=True,
                                              simplify=False)
        self._buildings = ox.geometries_from_bbox(north, south, east, west, {
            'building': True,
        })

        self.roads: dict[RoadId, Road] = {}
        self.road_segments: dict[RoadSegmentId, RoadSegment] = {}
        self.nodes: dict[NodeId, Node] = {}

        center_meridian = (west + east) / 2
        center_parallel = (north + south) / 2

        # project network to transverse mercator projection with
        # origin at the center meridian and parallel of bounding box
        crs_string = '+proj=tmerc +lat_0=%f +lon_0=%f +k_0=1 +x_0=0 +y_0=0 +ellps=WGS84 +datum=WGS84 +units=m +no_defs'
        self._road_graph = ox.project_graph(self._road_graph, to_crs=crs_string % (center_parallel, center_meridian))
        self._buildings.to_crs(crs_string % (center_parallel, center_meridian), inplace=True)

        # gather exit and entry nodes
        self.exit_nodes: list[NodeId] = []
        self.entry_nodes: list[NodeId] = []

        self._add_node_info()
        self._add_road_segment_info()
        self._organize_all_roads()
        self._connect_road_segments()

    def _add_node_info(self):
        for node_id, data in self._road_graph.nodes(data=True):
            neighbors = self._road_graph.neighbors(node_id)

            # given road layers, set the y position of this node
            layer: int = 0
            for neighbor_id in neighbors:
                road_data = self._road_graph[node_id][neighbor_id][0]
                if 'layer' in road_data:
                    road_layer = int(road_data['layer'])
                    layer = road_layer if road_layer > layer else layer

            node_pos = np.asarray([data['x'], layer * 4.0, data['y']])

            data['node'] = Node(node_id, node_pos)
            self.nodes[node_id] = data['node']

            # add to exit and entry nodes, if applicable
            if self._road_graph.out_degree(node_id) == 0:
                self.exit_nodes.append(node_id)
            elif self._road_graph.in_degree(node_id) == 0:
                self.entry_nodes.append(node_id)

    def _add_road_segment_info(self):
        next_road_segment_id = 0
        # add vehicle info to each edge
        for start_node_id, end_node_id, data in self._road_graph.edges(data=True):
            road_id = data['osmid']

            if 'lanes' not in data:
                data['lanes'] = 1
            elif isinstance(data['lanes'], list):
                data['lanes'] = len(data['lanes'])
            elif isinstance(data['lanes'], str):
                data['lanes'] = int(data['lanes'])
            else:
                data['lanes'] = 1

            if road_id not in self.roads:

                road = Road(road_id, data['lanes'])
                self.roads[road_id] = road
            else:
                road = self.roads[road_id]

            start_pos = self.nodes[start_node_id].pos
            target_pos = self.nodes[end_node_id].pos

            displacement = target_pos - start_pos
            length = np.linalg.norm(displacement)
            direction = displacement / length
            normal = np.cross(direction, [0.0, 1.0, 0.0])

            road_segment_id = next_road_segment_id
            road_segment = RoadSegment(road_segment_id, start_node_id, end_node_id, road_id, direction, normal,
                                       length)
            self.road_segments[road_segment_id] = road_segment
            data['road_segment'] = road_segment
            road.segments.append(road_segment_id)
            next_road_segment_id += 1

    def _organize_all_roads(self):
        """
        Organizes all roads via the _organize_road_structure method, while also adding any new reversed roads
        :return:
        """
        reverse_roads = {}
        for road_id in self.roads.keys():
            reversed_road = self._organize_road_structure(road_id)
            if reversed_road is not None:
                for road_segment in reversed_road.segments:
                    self.road_segments[road_segment].road_id = reversed_road.road_id
                reverse_roads[reversed_road.road_id] = reversed_road

        if len(reverse_roads) > 0:
            self.roads.update(reverse_roads)
            self._organize_all_roads()

    def _organize_road_structure(self, road_id) -> Road | None:
        """
        This method first tries to organize a road's road segments, in the order in which they are connected.
        As OSM uses the same ID for roads that have incoming and outgoing lanes, this function also creates a reverse
        road object for the lanes that go in the opposite direction, and returns it
        :return The reverse road object, if any
        """
        road = self.roads[road_id]
        road_segments = road.segments
        reverse_road = Road(road_id * 2, 0)
        first_road_segment = self.road_segments[road_segments[0]]
        ordered_road_segments = [road_segments[0]]
        added_roads: set[tuple[int, int]] = set()
        last_end_node = first_road_segment.end_node_id
        last_start_node = first_road_segment.start_node_id
        added_roads.add((last_start_node, last_end_node))

        while len(road_segments) != len(ordered_road_segments):
            for road_segment_id in road_segments:
                if road_segment_id in ordered_road_segments:
                    continue

                road_segment = self.road_segments[road_segment_id]

                if (road_segment.end_node_id, road_segment.start_node_id) in added_roads:
                    road_segments.remove(road_segment_id)
                    reverse_road.lanes = self._road_graph[road_segment.start_node_id][road_segment.end_node_id][0][
                        'lanes']
                    reverse_road.segments.append(road_segment_id)
                elif road_segment.start_node_id == last_end_node:
                    last_end_node = road_segment.end_node_id
                    ordered_road_segments.append(road_segment_id)
                    added_roads.add((road_segment.start_node_id, road_segment.end_node_id))
                elif road_segment.end_node_id == last_start_node:
                    last_start_node = road_segment.start_node_id
                    ordered_road_segments.insert(0, road_segment_id)
                    added_roads.add((road_segment.start_node_id, road_segment.end_node_id))

        road.segments = ordered_road_segments
        cumulative_length = 0.0
        for road_segment_id in road.segments:
            road_segment = self.road_segments[road_segment_id]
            road_segment.cumulative_length = cumulative_length
            cumulative_length += road_segment.length
        road.length = cumulative_length

        if len(reverse_road.segments) > 0:
            return reverse_road

    def _connect_road_segments(self):
        for road_segment_id, road_segment in self.road_segments.items():
            road = self.roads[road_segment.road_id]

            last_road_segment = self.road_segments[road.segments[-1]]
            last_rs_node = last_road_segment.end_node_id

            start_node = self.nodes[road_segment.start_node_id]
            end_node = self.nodes[road_segment.end_node_id]

            next_nodes_ids = self.get_node_neighbors(end_node)

            next_road_segments: list[RoadSegment] = []
            rightness: dict[int, float] = {}

            # get the list of neighboring segments (excluding the one that would go along the current road)
            # also calculate the relative node position to the current segment's start position
            for next_node_id in next_nodes_ids:
                next_road_segment = self._road_graph[end_node.node_id][next_node_id][0]['road_segment']

                if next_road_segment.road_segment_id not in road.segments:
                    next_road_segments.append(next_road_segment)
                    rel_position = self.nodes[next_node_id].pos - start_node.pos
                    # degree of rightness (how far along to the right an exit road segment is) using only x and z axes
                    # negative values indicates it's to the left
                    # noinspection PyTypeChecker
                    rightness[next_node_id] = np.dot(-1 * road_segment.direction[::2],
                                                     rel_position[::2])  # this is totally a float

            # join the exiting roads to a given lane, except if we're at the end of a road.
            # accumulate the exceptions in a list
            last_segments: list[RoadSegment] = []
            for next_road_segment in next_road_segments:
                if next_road_segment.road_segment_id == 92:
                    pass
                # if this road segment is connected to the last node of the road
                if last_rs_node == next_road_segment.start_node_id:
                    last_segments.append(next_road_segment)
                else:
                    # the road segment intersects the road at some other point
                    next_road = self.roads[next_road_segment.road_id]
                    if rightness[next_road_segment.end_node_id] > 0:
                        road.intersecting_segment_lanes[next_road_segment.road_segment_id] = [
                            (road.lanes - 1, next_road.lanes - 1)]
                        if road.road_id == 158071149:
                            pass
                    else:
                        road.intersecting_segment_lanes[next_road_segment.road_segment_id] = [(0, 0)]
                        if road.road_id == 158071149:
                            pass
            if len(last_segments) > 0:
                total_out_lanes = sum([self.roads[road_segment.road_id].lanes for road_segment in last_segments])
                total_out_roads = len(last_segments)
                in_lanes = road.lanes

                # output lane mapping for the last segments
                lane_connections: dict[int, list[tuple[int, int]]] = {}

                # sort the exiting nodes by their rightness (from left to right)
                last_segments.sort(key=lambda segment: rightness[segment.end_node_id])

                raw_segment_data = self._road_graph[start_node.node_id][end_node.node_id][0]
                # if there is a turn:lanes relationship defined, then use it to map the lanes

                if 'turn:lanes' in raw_segment_data:
                    raw_per_lane_turns: list[str] = raw_segment_data['turn:lanes'].split('|')
                    per_lane_turns: list[list[str]] = []
                    for raw_lane_turns in raw_per_lane_turns:
                        per_lane_turns.append(raw_lane_turns.split(';'))

                    out_current_lane = 0
                    last_segments_idx = 0
                    for lane_idx, lane_turns in enumerate(per_lane_turns):
                        for _ in lane_turns:
                            segment = last_segments[last_segments_idx]
                            if segment.road_segment_id not in lane_connections:
                                lane_connections[segment.road_segment_id] = []
                            lane_connections[segment.road_segment_id].append((lane_idx, out_current_lane))
                            out_current_lane += 1
                            if out_current_lane >= self.roads[last_segments[last_segments_idx].road_id].lanes:
                                out_current_lane = 0
                                last_segments_idx += 1
                elif total_out_roads >= in_lanes:
                    lane_to_roads_ratio = total_out_roads // in_lanes

                    last_segments_idx = 0
                    for lane_idx in range(0, road.lanes):
                        for out_segment_idx in range(0, lane_to_roads_ratio):
                            segment = last_segments[last_segments_idx]
                            if segment.road_segment_id not in lane_connections:
                                lane_connections[segment.road_segment_id] = []
                            for out_lane_idx in range(0, self.roads[segment.road_id].lanes):
                                lane_connections[segment.road_segment_id].append((lane_idx, out_lane_idx))
                            last_segments_idx += 1
                    if last_segments_idx < len(last_segments):
                        for out_segment_idx in range(last_segments_idx - 1, len(last_segments)):
                            segment = last_segments[out_segment_idx]
                            if segment.road_segment_id not in lane_connections:
                                lane_connections[segment.road_segment_id] = []
                            lane_connections[segment.road_segment_id].append((road.lanes - 1, 0))
                else:
                    lane_to_lanes_ratio = (total_out_lanes // total_out_roads) // in_lanes
                    lane_to_lanes_ratio = 1 if lane_to_lanes_ratio == 0 else lane_to_lanes_ratio

                    out_current_lane = 0
                    last_segments_idx = 0
                    for lane_idx in range(0, road.lanes):
                        for out_lane_idx in range(0, lane_to_lanes_ratio):
                            segment = last_segments[last_segments_idx]
                            if segment.road_segment_id not in lane_connections:
                                lane_connections[segment.road_segment_id] = []
                            lane_connections[segment.road_segment_id].append(
                                (lane_idx, out_lane_idx + out_current_lane))

                            if out_current_lane + 1 >= self.roads[
                                last_segments[last_segments_idx].road_id].lanes:
                                break

                        if out_current_lane + lane_to_lanes_ratio < self.roads[
                            last_segments[last_segments_idx].road_id].lanes:
                            out_current_lane += lane_to_lanes_ratio
                        else:
                            last_segments_idx += 1
                            out_current_lane = 0

                        if last_segments_idx >= len(last_segments):
                            break
                    if last_segments_idx < len(last_segments):
                        for out_segment_idx in range(last_segments_idx - 1, len(last_segments)):
                            segment = last_segments[out_segment_idx]
                            if segment.road_segment_id not in lane_connections:
                                lane_connections[segment.road_segment_id] = []
                            lane_connections[segment.road_segment_id].append((road.lanes - 1, 0))
                road.intersecting_segment_lanes.update(lane_connections)

    def get_node_neighbors(self, node: Node) -> set[int]:
        neighbors_set = set()
        neighbors_set.update(self._road_graph.neighbors(node.node_id))
        return neighbors_set

    # def road_length(self, road_id: tuple[int, int]) -> float:
    #     return self._road_graph[road_id[0]][road_id[1]][0]['length']
    #
    # def normal_vector(self, road_id: tuple[int, int]) -> np.ndarray:
    #     return self._road_graph[road_id[0]][road_id[1]][0]['normal_vector']
    #
    # def direction_vector(self, road_id: tuple[int, int]) -> np.ndarray:
    #     return self._road_graph[road_id[0]][road_id[1]][0]['direction_vector']
    #
    def _astar_heuristic(self, n1_id: NodeId, n2_id: NodeId):
        """
        Heuristic function fo A* algorithm. Uses euclidean distance between nodes.
        :param n1_id: first node
        :param n2_id: second node
        :return:
        """
        n1_pos = self.nodes[n1_id].pos
        n2_pos = self.nodes[n2_id].pos
        return cdist([n1_pos], [n2_pos])

    def shortest_path(self, n1_id: NodeId, n2_id: NodeId) -> Optional[list[int]]:
        try:
            return nx.astar_path(self._road_graph, n1_id, n2_id,
                                 heuristic=self._astar_heuristic)
        except nx.NetworkXNoPath:
            return None

    def road_segment_from_nodes(self, n1_id: NodeId, n2_id: NodeId) -> RoadSegment:
        return self._road_graph[n1_id][n2_id][0]['road_segment']

    # def node_position(self, node_id: int) -> np.ndarray:
    #     return self._road_graph.nodes(data=True)[node_id]['node'].pos

    def send_to_kafka(self, producer: KafkaProducer):
        for _, building in self._buildings.iterrows():
            polygon = building['geometry'].exterior.xy
            geometry_x = list([value for value in polygon[0]])
            geometry_z = list([value for value in polygon[1]])
            producer.send('buildings', {
                'geometry_x': geometry_x,
                'geometry_z': geometry_z,
                'levels': building['building:levels'],
                'name': building['name'],
            })

        for road_segment in self.road_segments.values():
            road = self.roads[road_segment.road_id]

            start_pos = self.nodes[road_segment.start_node_id].pos
            end_pos = self.nodes[road_segment.end_node_id].pos
            producer.send('roads', {
                'start_x': start_pos[0],
                'start_y': start_pos[1],
                'start_z': start_pos[2],
                'end_x': end_pos[0],
                'end_y': end_pos[1],
                'end_z': end_pos[2],
                'length': road_segment.length,
                'lane_count': road.lanes,
            })
