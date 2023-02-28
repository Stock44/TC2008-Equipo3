from abc import ABC, abstractmethod


class StateProducer(ABC):
    dirty: bool = False

    @abstractmethod
    def dump_state(self) -> dict[str, any]:
        pass
