from dataclasses import dataclass, field
from typing import Any

@dataclass
class ProvenanceNode:
    id: int
    kind: str
    operation: str
    parameters: dict[str, Any] = field(default_factory=dict)
    parents: list["ProvenanceNode"] = field(default_factory=list)