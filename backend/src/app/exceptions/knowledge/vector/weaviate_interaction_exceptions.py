class ChunkNotFoundError(Exception):
    """Raised when no matching chunk is found in the collection."""
    pass


class MultipleChunksFoundError(Exception):
    """Raised when multiple matching chunks are found in the collection."""
    
    def __init__(self, uuids):
        message = f"Found multiple objects matching the desired chunk (IDs): {uuids}"
        super().__init__(message)
        self.uuids = uuids
