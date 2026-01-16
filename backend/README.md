# MedAgent Guidelines - Backend

The backend combines functionality for:

- Interaction with external components (LLMs, databases, ...)
- Handling the 'logic' of the project

It mainly follows the approach
of [Model-Controller-Service](https://medium.com/@jeremyalvax/fastapi-backend-architecture-model-controller-service-44e920567699)
architecture and is
implemented using FastAPI

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

The project structure looks as follows:

```
backend
├── src/                       # Source code directory
│   ├── logs/                  # Storage for log files
│   └── app/                   # Main application code
│       ├── main.py            # Application entry point
│       ├── models/            # Data models and schemas
│       ├── services/          # Business logic and helper services
│       └── routers/           # API endpoint definitions
├── data/                      # Persistent storage across Docker restarts
├── requirements.txt           # Python dependencies list
└── README.md                  # Project overview and documentation
```

- TODO: finish

Documentation of service interaction and datamodels: TODO

- Include the powerpoint presentations for visualization
