import json
import time

from asyncio import get_event_loop
from kafka import KafkaProducer
from mesa import Model, Agent
from abc import ABC, abstractmethod

from model.state_producer_agent import StateProducerAgent


def json_serializer(input_dict: dict[str, any]):
    json_str = json.dumps(input_dict)
    return bytes(json_str, 'utf-8')


class AgentStateProducerModel(Model, ABC):
    __agent_lists: dict[type, list[StateProducerAgent]] = {}
    __agent_topic_names: dict[type, str] = {}

    def __init__(self, kafka_address: str, *args: any, **kwargs: any):
        super().__init__(*args, **kwargs)
        self.__kafka_producer = KafkaProducer(bootstrap_servers=kafka_address, value_serializer=json_serializer)

    def register_agent_type(self, agent_cls: type, topic_name: str):
        self.__agent_lists[agent_cls] = []
        self.__agent_topic_names[agent_cls] = topic_name

    def register_agent(self, agent: StateProducerAgent):
        self.__agent_lists[type(agent)].append(agent)

    def send_states(self):
        for agent_type, agents in self.__agent_lists.items():
            for agent in agents:
                state = agent.dump_state()
                self.__kafka_producer.send(self.__agent_topic_names[agent_type], state)

