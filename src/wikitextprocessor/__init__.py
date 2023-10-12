from .core import Wtp, MAGIC_FIRST, MAGIC_LAST, Page
from .parser import NodeKind, WikiNode

__all__ = (
    "Wtp",
    "NodeKind",
    "WikiNode",
    "MAGIC_FIRST",  # Some applications with to use the same ranges
    "MAGIC_LAST",
    "Page"
)
