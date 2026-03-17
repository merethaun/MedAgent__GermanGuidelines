from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PromptDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    system_prompt: Optional[str] = Field(
        default=None,
        description="Reusable system prompt template.",
    )
    prompt: str = Field(
        ...,
        description="Reusable example prompt or default prompt template stored alongside the system prompt.",
    )
