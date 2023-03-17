import numpy as np
from numba import njit, vectorize, float64
from numpy.typing import ArrayLike


@vectorize([float64(float64, float64, float64, float64)])
def calculate_idm_free_accelerations(vehicle_speeds: ArrayLike,
                                     desired_speeds: ArrayLike, maximum_accelerations: ArrayLike,
                                     acceleration_reduction_factor: ArrayLike):
    velocity_factors = np.power(np.divide(vehicle_speeds, desired_speeds), acceleration_reduction_factor)

    accelerations = np.multiply(maximum_accelerations, np.subtract(1, velocity_factors))

    return accelerations


@vectorize([float64(float64, float64, float64, float64, float64, float64, float64, float64, float64)])
def calculate_idm_accelerations(vehicle_distances: ArrayLike, vehicle_speeds: ArrayLike, next_vehicle_speeds: ArrayLike,
                                desired_speeds: ArrayLike, minimum_safety_gaps: ArrayLike,
                                time_safety_gaps: ArrayLike, maximum_accelerations: ArrayLike,
                                comfortable_decelerations: ArrayLike, acceleration_reduction_factor: ArrayLike):
    velocity_factors = np.power(np.divide(vehicle_speeds, desired_speeds), acceleration_reduction_factor)

    delta_velocities = np.subtract(vehicle_speeds, next_vehicle_speeds)

    dynamic_gap_factors = np.divide(np.multiply(vehicle_speeds, delta_velocities), (
            2 * np.sqrt(np.multiply(maximum_accelerations, comfortable_decelerations))))

    time_gap_factors = np.multiply(vehicle_speeds, time_safety_gaps)
    desired_gap = np.add(minimum_safety_gaps, np.maximum(0.0, np.add(time_gap_factors, dynamic_gap_factors)))
    gap_factor = np.power(np.divide(desired_gap, vehicle_distances), 2)
    accelerations = np.multiply(maximum_accelerations, (np.subtract(np.subtract(1, velocity_factors), gap_factor)))
    return accelerations

# class IDMVehicleAgent(VehicleAgent):
#     def __init__(self, unique_id: int, model: Model, road_network: RoadNetwork, route: list[int], width: float,
#                  length: float,
#                  desired_speed: float = 80, acceleration_reduction_factor: float = 4, minimum_safety_gap: float = 1,
#                  time_safety_gap: float = 1, maximum_acceleration: float = 1.0,
#                  comfortable_deceleration: float = 1.5):
#         super().__init__(unique_id, model, road_network, width, length)
#         self._road_network = road_network
#
#         self.desired_speed = desired_speed
#         self.acceleration_reduction_factor = acceleration_reduction_factor
#         self.minimum_safety_gap = minimum_safety_gap
#         self.time_safety_gap = time_safety_gap
#         self.maximum_acceleration = maximum_acceleration
#         self.comfortable_deceleration = comfortable_deceleration
#         self.finished = False
#
#         self.route: list[int] = route
#
#         self._next_acceleration: float = 0.0
#
#     def step(self) -> None:
#         if self.finished:
#             return
#
#         velocity_factor = (self.velocity / self.desired_speed) ** self.acceleration_reduction_factor
#
#         next_vehicle = self._road_network.next_vehicle(self)
#         if next_vehicle is not None:
#             delta_velocity = self.velocity - next_vehicle.velocity
#
#             dynamic_gap_factor = (self.velocity * delta_velocity) / (
#                     2 * np.sqrt(self.maximum_acceleration * self.comfortable_deceleration))
#
#             desired_gap = self.minimum_safety_gap + max(0.0, np.linalg.norm(
#                 self.velocity * self.time_safety_gap + dynamic_gap_factor))
#
#             current_gap = next_vehicle.road_pos - self.road_pos
#
#             gap_factor = (desired_gap / current_gap) ** 2
#         else:
#             gap_factor = 0.0
#
#         self._next_acceleration = self.maximum_acceleration * (np.ones(3) - velocity_factor - gap_factor)
#
#     def advance(self) -> None:
#         if self.finished:
#             return
#
#         current_time = time.time()
#         delta_t = current_time - self.last_execution
#         self.last_execution = current_time
#
#         if we are at the end of the road
# road_length = self.road_network.road_length(self.road_id)
# at_end_of_road = road_length < (self.road_pos + np.linalg.norm(self.velocity))
# if at_end_of_road:
#     end_node_id = self.road_id[1]
#     end_node_idx = self.route.index(end_node_id)
#     print("segment_id: ", end_node_idx)
#     the old end is the new beginning
# try:
#     self.road_network.change_road(self, (end_node_id, self.route[end_node_idx + 1]))
# except IndexError:
#     self.finished = True
# else:
#     self.road_network.advance_vehicle(self, delta_t)
#
#     self.velocity += self.acceleration * delta_t * self.road_network.direction_vector(self.road_id)
#     self.acceleration = self._next_acceleration
#
