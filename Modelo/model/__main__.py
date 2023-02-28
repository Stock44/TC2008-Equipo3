from mesa.visualization.ModularVisualization import ModularServer
from mesa.visualization.UserParam import Slider
from mesa.visualization.modules import CanvasGrid, ChartModule
from .cross_road_model import CrossRoadModel
from .portrayal import portray_agent

NUM_CARS = 50
HALF_LENGTH = 20
TRAFFIC_TIMER = 10
# CAR_TURNING_RATE = 0.5
MAX_ITERATIONS = 500

pixel_ratio = 10

model_params = {
    'num_agents': Slider("Number of cars", NUM_CARS, 5, 200, 5),
    'half_length': Slider("Half length", HALF_LENGTH, 5, 50, 5),
    'traffic_time': Slider("Traffic timer", TRAFFIC_TIMER, 5, 100, 5),
    # 'car_turning_rate': Slider("Turning rate", CAR_TURNING_RATE, 0.0, 1.0, 0.1)
}

length = model_params['half_length'].value * 2
canvas_element = CanvasGrid(
    portray_agent, length, length,
    pixel_ratio * length, pixel_ratio * length)
chart_element = ChartModule([
    {"Label": "Waiting", "Color": "#AA0000"},
    {"Label": "Running", "Color": "#00AA00"}
])

server = ModularServer(model_cls=CrossRoadModel,
                       visualization_elements=[canvas_element, chart_element],
                       name="Cross Road", model_params=model_params)

server.max_steps = MAX_ITERATIONS

server.launch()
