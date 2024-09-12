from .common import MAGIC_FIRST, MAGIC_LAST
from .core import Page, TemplateArgs, Wtp
from .parser import HTMLNode, LevelNode, NodeKind, TemplateNode, WikiNode

__all__ = (
    "Wtp",
    "HTMLNode",
    "LevelNode",
    "NodeKind",
    "TemplateNode",
    "WikiNode",
    "MAGIC_FIRST",  # Some applications with to use the same ranges
    "MAGIC_LAST",
    "Page",
    "TemplateArgs",
)
