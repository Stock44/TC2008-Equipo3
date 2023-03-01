from abc import ABC, abstractmethod

from mesa import Agent


class StateProducerAgent(Agent, ABC):
    dirty: bool = False

    @abstractmethod
    def dump_state(self) -> dict[str, any]:
        pass
