from dataclasses import dataclass
from typing import Optional

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from app.constants.mongodb_config import EVALUATION_MONGODB_DB_NAME, EVALUATION_MONGODB_URI


@dataclass(frozen=True)
class MongoState:
    client: MongoClient
    db: Database


_state: Optional[MongoState] = None


def init_mongo() -> None:
    global _state
    if _state is not None:
        return

    if not EVALUATION_MONGODB_URI:
        raise RuntimeError("EVALUATION_MONGODB_URI is not set. Please configure it in the environment.")

    client = MongoClient(EVALUATION_MONGODB_URI)
    db = client[EVALUATION_MONGODB_DB_NAME]
    _state = MongoState(client=client, db=db)


def set_mongo_state(client: MongoClient, db: Database) -> None:
    global _state
    _state = MongoState(client=client, db=db)


def reset_mongo_state() -> None:
    global _state
    _state = None


def get_db() -> Database:
    if _state is None:
        init_mongo()
    assert _state is not None
    return _state.db


def get_collection(name: str) -> Collection:
    return get_db()[name]
