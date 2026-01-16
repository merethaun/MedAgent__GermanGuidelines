from typing import Any, Optional

from bson import ObjectId
from pydantic_core import core_schema


class PyObjectId(str):
    @classmethod
    def __get_pydantic_core_schema__(cls, _source_type: Any, _handler: Any) -> core_schema.CoreSchema:
        return core_schema.json_or_python_schema(
            json_schema=core_schema.str_schema(),
            python_schema=core_schema.union_schema(
                [
                    core_schema.is_instance_schema(ObjectId),
                    core_schema.chain_schema(
                        [
                            core_schema.str_schema(),
                            core_schema.no_info_plain_validator_function(cls.validate),
                        ],
                    ),
                ],
            ),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda x: str(x), when_used="json",
            ),
        )
    
    @classmethod
    def validate(cls, value) -> Optional[ObjectId]:
        if value is None:
            return None
        if not ObjectId.is_valid(value):
            raise ValueError("Invalid ObjectId")
        return ObjectId(value)


def as_object_id(id_str: str) -> ObjectId:
    """
    Safely convert a string to an ObjectId.

    Args:
        id_str: The string to convert.

    Returns:
        ObjectId instance.

    Raises:
        ValueError: If the input is not a valid ObjectId string.
    """
    if not ObjectId.is_valid(id_str):
        raise ValueError(f"Invalid ObjectId string: {id_str}")
    return ObjectId(id_str)
