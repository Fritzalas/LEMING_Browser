from __future__ import annotations
from typing import Any
import itertools
import os
import sys
# getting the name of the directory
# where the this file is present.
current = os.path.dirname(os.path.realpath(__file__))
# Getting the parent directory name
# where the current directory is present.
parent = os.path.dirname(current)
# adding the parent directory to 
# the sys.path.
sys.path.append(parent)

from Classes.ProvenanceNode import ProvenanceNode

_next_id = itertools.count(1)

# id(Python object) -> provenance node
_registry: dict[int, ProvenanceNode] = {}

# Keep references so Python cannot recycle object ids while the
# provenance information is still active.
_objects: dict[int, Any] = {}


def register_provenance(
    obj: Any,
    kind: str,
    operation: str,
    parameters: dict[str, Any] | None = None,
    parents: list[Any] | None = None,
) -> Any:
    """
    Attach provenance information to an existing Python/PyROOT object.

    The object itself is returned so this can be inserted transparently
    into existing code.
    """
    parent_nodes = []

    for parent in parents or []:
        node = get_provenance(parent)

        if node is not None:
            parent_nodes.append(node)

    node = ProvenanceNode(
        id=next(_next_id),
        kind=kind,
        operation=operation,
        parameters=parameters or {},
        parents=parent_nodes,
    )

    object_id = id(obj)

    _registry[object_id] = node
    _objects[object_id] = obj

    return obj


def get_provenance(obj: Any) -> ProvenanceNode | None:
    return _registry.get(id(obj))