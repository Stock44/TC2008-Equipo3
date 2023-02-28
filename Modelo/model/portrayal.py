from mesa import Agent

from m3_model.field_agent import FieldAgent
from m3_model.traffic_light_agent import TrafficLightAgent, TrafficLightColor
from m3_model.car_agent import CarAgent


def portray_traffic_light(traffic_light: TrafficLightAgent):
    portrayal = {"Filled": "true"}
    if traffic_light.color is TrafficLightColor.GREEN:
        portrayal["Color"] = "#00FF00"
    elif traffic_light.color is TrafficLightColor.RED:  # red
        portrayal["Color"] = "#FF0000"
    else:
        portrayal["Color"] = "#FFFF00"
    portrayal["Shape"] = "circle"
    portrayal["r"] = 1
    portrayal["Layer"] = 1

    return portrayal


def portray_car(car: CarAgent):
    portrayal = {"Filled": "true"}
    # if car.colour == "orange":
    #     portrayal["Color"] = "#FF9C38"
    # elif car.colour == "blue":
    #     portrayal["Color"] = "#0000FF"
    # elif car.colour == "purple":
    #     portrayal["Color"] = "#D847FF"
    # else:  # black
    portrayal["Color"] = "#000000"
    portrayal["Shape"] = "circle"
    portrayal["r"] = 1.1
    portrayal["Layer"] = 1
    # if car.waiting == 1:
    #     portrayal["text"] = "x"
    #     portrayal["text_color"] = "Red"
    # else:
    portrayal["text"] = ""
    portrayal["text_color"] = "Green"

    return portrayal


def portray_field(field: FieldAgent):
    portrayal = {"Filled": "true"}
    if field.colour == 'brown':
        portrayal["Color"] = "#865700"
    elif field.colour == 'olive':
        portrayal["Color"] = "#828232"
    else:  # dark green
        portrayal["Color"] = "#0A6414"
    portrayal["Shape"] = "rect"
    portrayal["h"] = 1
    portrayal["w"] = 1
    portrayal["Layer"] = 0

    return portrayal


def portray_agent(agent: Agent):
    # Street
    if agent is None:
        portrayal = {"Filled": "true", "Color": "#A8A8A8", "Shape": "rect", "h": 1, "w": 1, "Layer": 0}
        return portrayal
    elif isinstance(agent, CarAgent):
        return portray_car(agent)

    elif isinstance(agent, TrafficLightAgent):
        return portray_traffic_light(agent)

    elif isinstance(agent, FieldAgent):
        return portray_field(agent)
    else:
        return {}
