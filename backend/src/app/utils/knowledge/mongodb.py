from pymongo import MongoClient

from app.constants.mongodb_constants import MONGODB_DATABASE, MONGODB_URI, EVAL_MONGODB_DATABASE

mongo_client = MongoClient(MONGODB_URI)
system_interaction_database = mongo_client[MONGODB_DATABASE]


def get_system_mongodb_database():
    return system_interaction_database


eval_database = mongo_client[EVAL_MONGODB_DATABASE]


def get_eval_mongodb_database():
    return eval_database
