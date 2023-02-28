import json
import time

from asyncio import get_event_loop
from kafka import KafkaProducer
from mesa import Model
from abc import ABC, abstractmethod


class ProducerModel(Model, ABC):
    is_dirty = False

    @abstractmethod
    def dump_agent_states(self) -> list[dict[str, any]]:
        pass


def json_serializer(input_dict: dict[str, any]):
    json_str = json.dumps(input_dict)
    return bytes(json_str, 'utf-8')


def run_and_report_model(model: ProducerModel, kafka_bootstrap_server: str, tick_duration: int = 1):
    kafka_producer = KafkaProducer(bootstrap_servers=kafka_bootstrap_server, value_serializer=json_serializer)

    while True:
        begin = time.time()

        model.step()

        states = model.dump_agent_states()

        for state in states:
            kafka_producer.send('model', state)

        delta_t = time.time() - begin

        if delta_t < tick_duration:
            time.sleep(tick_duration - delta_t)
        else:
            print("ticks running behind by %f s!" % (delta_t - tick_duration))
            pass
