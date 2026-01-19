from dataclasses import dataclass
from typing import Optional, Set


@dataclass(frozen=True)
class CurrentUser:
    sub: str
    username: Optional[str]
    roles: Set[str]
