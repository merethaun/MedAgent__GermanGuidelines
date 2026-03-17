from enum import Enum
from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator


class EmbeddingPurpose(str, Enum):
    DOCUMENT = "document"
    QUERY = "query"


class VectorizerDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    provider: str
    display_name: str
    description: str
    supports_document_embeddings: bool = True
    supports_query_embeddings: bool = True
    is_available: bool
    availability_message: Optional[str] = None
    default_dimension: Optional[int] = None


class VectorizerListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    vectorizers: List[VectorizerDescriptor]


class OpenAIEmbeddingProviderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    provider: Literal["openai-text-embedding-3-large"]
    api_key: SecretStr = Field(..., description="API key used for this embedding request.")
    base_url: Optional[str] = Field(
        default=None,
        description="Optional OpenAI-compatible base URL, for example Azure OpenAI or another compatible gateway.",
    )
    model: str = Field(default="text-embedding-3-large", description="Embedding model name to call.")


class BGEM3EmbeddingProviderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    provider: Literal["baai-bge-m3"]
    model_name: str = Field(default="BAAI/bge-m3", description="Model id or local path to load.")
    batch_size: int = Field(default=8, ge=1, description="Batch size used for local inference.")


EmbeddingProviderSettings = Annotated[
    Union[OpenAIEmbeddingProviderSettings, BGEM3EmbeddingProviderSettings],
    Field(discriminator="provider"),
]


class EmbeddingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    provider: str = Field(..., description="Registered vectorizer provider id.")
    texts: List[str] = Field(..., min_length=1, description="One or more texts to embed.")
    provider_settings: Optional[EmbeddingProviderSettings] = Field(
        default=None,
        description="Request-scoped provider configuration such as API credentials or local model overrides.",
    )
    purpose: EmbeddingPurpose = Field(
        default=EmbeddingPurpose.DOCUMENT,
        description="Whether the texts represent documents or retrieval queries.",
    )
    normalize: bool = Field(
        default=False,
        description="If true, L2-normalize each returned vector before sending it back.",
    )
    
    @field_validator("texts")
    @classmethod
    def _validate_texts(cls, texts: List[str]) -> List[str]:
        if any(not text.strip() for text in texts):
            raise ValueError("texts must not contain empty entries")
        return texts
    
    @model_validator(mode="after")
    def _validate_provider_settings(self) -> "EmbeddingRequest":
        if self.provider_settings is not None and self.provider_settings.provider != self.provider:
            raise ValueError("provider_settings.provider must match provider")
        return self


class EmbeddingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    provider: str
    purpose: EmbeddingPurpose
    normalize: bool
    dimensions: int
    embeddings: List[List[float]]
