from mesa import Agent
from enum import IntEnum


class TrafficLightColor:
    RED = 0
    YELLOW = 1
    GREEN = 2


class TrafficLightAgent(Agent):
    def __init__(self, unique_id, model, green_duration=10, red_duration=10, yellow_duration=5, step_offset=0,
                 starting_color=TrafficLightColor.RED):
        super().__init__(unique_id, model)
        self.red_duration = red_duration
        self.yellow_duration = yellow_duration
        self.green_duration = green_duration
        self.color = starting_color
        self._next_color: TrafficLightColor | None = None

        self._step_counter = step_offset + 1
        self._paused = False

    def pause(self, paused: bool):
        self._paused = paused

    def step(self) -> None:
        if self._paused:
            self._next_color = None
            return

        if self.color is TrafficLightColor.YELLOW:
            self._step_counter %= self.yellow_duration
            next_color_in_sequence = TrafficLightColor.RED
        elif self.color is TrafficLightColor.RED:
            self._step_counter %= self.red_duration
            next_color_in_sequence = TrafficLightColor.GREEN
        else:
            self._step_counter %= self.green_duration
            next_color_in_sequence = TrafficLightColor.YELLOW

        if self._step_counter == 0:
            self._next_color = next_color_in_sequence
        self._step_counter += 1

    def advance(self) -> None:
        if self._next_color is not None:
            self.color = self._next_color
