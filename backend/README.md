# BACKEND: MedAgent for German medical guidelines (simplified)

The backend handles the interaction with external components like LLMs and databases and handles the main logic of the project.
It uses FastAPI, and mainly follows the approach of [Model-Controller-Service](https://medium.com/@jeremyalvax/fastapi-backend-architecture-model-controller-service-44e920567699):
- **Model** layer: define data models, database schemas, ...
- **Service** layer: core logic of program, including executing a defined workflow, invoking a LLM, computing evaluation
  results, ...
- **Controller** layer: FastAPI routers / endpoints handling HTTP requests and calling respective services + handling of
  format for input / output of
  endpoints
- Intended interaction of layers:
    - Controller and router only access services, and should contain as little logic as possible
    - Models are mainly accessed by services
    - Services ideally stand for themselves and are responsible for the interaction with external tools
    - Services can depend on / utilize each other; but !! no circular imports !!

## Project structure
