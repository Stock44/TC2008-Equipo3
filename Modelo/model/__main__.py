import time

from model.idm_model import IDMModel

model = IDMModel()
while True:
    model.step()
# length = model_params['half_length'].value * 2
# canvas_element = CanvasGrid(
#     portray_agent, length, length,
#     pixel_ratio * length, pixel_ratio * length)
# chart_element = ChartModule([
#     {"Label": "Waiting", "Color": "#AA0000"},
#     {"Label": "Running", "Color": "#00AA00"}
# ])

# server = ModularServer(model_cls=CrossRoadModel,
#                        visualization_elements=[canvas_element, chart_element],
#                        name="Cross Road", model_params=model_params)

# server.max_steps = MAX_ITERATIONS
#
# server.launch()
