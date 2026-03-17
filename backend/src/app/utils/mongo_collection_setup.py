from dataclasses import dataclass
from typing import Optional

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from app.constants.mongodb_config import MONGODB_DB_NAME, MONGODB_URI


@dataclass(frozen=True)
class MongoState:
    client: MongoClient
    db: Database


_state: Optional[MongoState] = None


def init_mongo() -> None:
    """Initialize Mongo client/db once per process."""
    global _state
    if _state is not None:
        return
    
    if not MONGODB_URI:
        raise RuntimeError("MONGODB_URI is not set. Please configure it in .env")
    
    client = MongoClient(MONGODB_URI)
    db = client[MONGODB_DB_NAME]
    _state = MongoState(client=client, db=db)


def get_db() -> Database:
    if _state is None:
        init_mongo()
    assert _state is not None
    return _state.db


def get_collection(name: str) -> Collection:
    return get_db()[name]
