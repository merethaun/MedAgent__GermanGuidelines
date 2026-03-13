SUPPORTED_DISTANCE_METRICS = ["cosine", "dot", "l2-squared", "manhattan", "hamming"]

WEAVIATE_DATA_TYPE_MEMBER_MAP = {
    "text": "TEXT",
    "text[]": "TEXT_ARRAY",
    "int": "INT",
    "int[]": "INT_ARRAY",
    "number": "NUMBER",
    "number[]": "NUMBER_ARRAY",
    "boolean": "BOOL",
    "boolean[]": "BOOL_ARRAY",
    "date": "DATE",
    "date[]": "DATE_ARRAY",
    "uuid": "UUID",
    "uuid[]": "UUID_ARRAY",
    "geocoordinates": "GEO_COORDINATES",
    "blob": "BLOB",
    "phonenumber": "PHONE_NUMBER",
    "object": "OBJECT",
    "object[]": "OBJECT_ARRAY",
}

WEAVIATE_PROP_TEXT = "text"
WEAVIATE_PROP_HEADERS = "headers"
WEAVIATE_PROP_CHUNK_INDEX = "chunk_index"
WEAVIATE_PROP_GUIDELINE_ID = "guideline_id"
WEAVIATE_PROP_REFERENCE_ID = "reference_id"
WEAVIATE_PROP_REFERENCE_TYPE = "reference_type"
WEAVIATE_PROP_GUIDELINE_TITLE = "guideline_title"
WEAVIATE_PROP_GUIDELINE_KEYWORDS = "guideline_keywords"
WEAVIATE_PROP_REFERENCE_KEYWORDS = "reference_keywords"
