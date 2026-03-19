class GraphNotFoundError(ValueError):
    """Raised when a requested Neo4j graph name does not exist."""

    def __init__(self, graph_name: str):
        self.graph_name = graph_name
        super().__init__(f"Graph '{graph_name}' does not exist.")
