import json
import time

from kafka import KafkaProducer
from mesa import Model
from mesa.time import SimultaneousActivation

from model.idm_agent import IDMVehicleAgent
from model.road_network import RoadNetwork
from model.vehicle_agent import VehicleAgent


def json_serializer(input_dict: dict[str, any]):
    json_str = json.dumps(input_dict)
    return bytes(json_str, 'utf-8')


class TrafficModel(Model):
    def __init__(self):
        super().__init__()
        self.road_network = RoadNetwork(25.6759, 25.6682, -100.3481, -100.3582)
        self.schedule = SimultaneousActivation(self)
        self.vehicles: list[VehicleAgent] = []
        self._kafka_producer = KafkaProducer(bootstrap_servers='localhost:9092', value_serializer=json_serializer)

        entry_node = self.road_network.entry_nodes[0]
        exit_node = self.road_network.exit_nodes[0]
        path = self.road_network.shortest_path(entry_node, exit_node)

        self._car = IDMVehicleAgent(0, self, self.road_network, entry_node, 1.0, 2.0)
        self.schedule.add(self._car)
        self.road_network.place_vehicle(self._car, (path[0], path[1]))

    def step(self) -> None:
        self.schedule.step()
        self._kafka_producer.send('cars', {
            'id': self._car.unique_id,
            'x': self._car.pos[0],
            'y': self._car.pos[1],
        })


if __name__ == '__main__':
    model = TrafficModel()
    while True:
        model.step()
        time.sleep(0.1)
