from typing import Any

from bson import ObjectId
from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic_core import core_schema


class PyObjectId(ObjectId):
    """ObjectId that Pydantic can validate + serialize."""
    
    @classmethod
    def __get_pydantic_core_schema__(
            cls,
            _source_type: Any,
            _handler: GetCoreSchemaHandler,
    ) -> core_schema.CoreSchema:
        def validate(v: Any) -> ObjectId:
            if isinstance(v, ObjectId):
                return v
            if isinstance(v, str) and ObjectId.is_valid(v):
                return ObjectId(v)
            raise ValueError("Invalid ObjectId")
        
        return core_schema.no_info_plain_validator_function(
            validate,
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda v: str(v),
                return_schema=core_schema.str_schema(),
            ),
        )
    
    @classmethod
    def __get_pydantic_json_schema__(
            cls,
            _core_schema: core_schema.CoreSchema,
            handler: GetJsonSchemaHandler,
    ) -> dict:
        # Represent as string in OpenAPI/JSON schema
        return {"type": "string", "examples": ["507f1f77bcf86cd799439011"]}
