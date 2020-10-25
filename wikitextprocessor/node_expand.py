# Expanding parse tree nodes to Wikitext or HTML or plain text
#
# Copyright (c) 2020 Tatu Ylonen.  See file LICENSE and https://ylonen.org

import html
import urllib.parse
from .parser import WikiNode, NodeKind


kind_to_level = {
    NodeKind.LEVEL2: "==",
    NodeKind.LEVEL3: "===",
    NodeKind.LEVEL4: "====",
    NodeKind.LEVEL5: "=====",
    NodeKind.LEVEL6: "======",
}


def to_attrs(node):
    parts = []
    for k, v in node.attrs.items():
        k = str(k)
        if not v:
            parts.append(k)
            continue
        v = urllib.parse.quote_plus(str(v))
        parts.append('{}="{}"'.format(k, v))
    return " ".join(parts)


def to_wikitext(node):
    """Converts a parse tree (or subtree) back to Wikitext."""
    if isinstance(node, str):
        return html.escape(node)
    if isinstance(node, (list, tuple)):
        return "".join(map(to_wikitext, node))
    if not isinstance(node, WikiNode):
        raise RuntimeError("invalid WikiNode: {}".format(node))

    kind = node.kind
    parts = []
    if kind in kind_to_level:
        tag = kind_to_level[kind]
        t = to_wikitext(node.args)
        parts.append("\n{} {} {}\n".format(tag, t, tag))
        parts.append(to_wikitext(node.children))
    elif kind == NodeKind.HLINE:
        parts.append("\n----\n")
    elif kind == NodeKind.LIST:
        parts.append(to_wikitext(node.children))
    elif kind == NodeKind.LIST_ITEM:
        assert isinstance(node.args, str)
        parts.append(node.args)
        prev_list = False
        for x in node.children:
            if prev_list:
                parts.append(node.args + ":")
            parts.append(to_wikitext(x))
            prev_list = isinstance(x, WikiNode) and x.kind == NodeKind.LIST
    elif kind == NodeKind.PRE:
        parts.append("<pre>")
        parts.append(to_wikitext(node.children))
        parts.append("</pre>")
    elif kind == NodeKind.PREFORMATTED:
        parts.append(to_wikitext(node.children))
    elif kind == NodeKind.LINK:
        parts.append("[[")
        parts.append(" ".join(map(to_wikitext, node.args)))
        parts.append("]]")
        parts.append(to_wikitext(node.children))
    elif kind == NodeKind.TEMPLATE:
        parts.append("{{")
        parts.append("|".join(map(to_wikitext, node.args)))
        parts.append("}}")
    elif kind == NodeKind.TEMPLATE_ARG:
        parts.append("{{{")
        parts.append("|".join(map(to_wikitext, node.args)))
        parts.append("}}}")
    elif kind == NodeKind.PARSER_FN:
        parts.append("{{" + to_wikitext(node.args[0]) + ":")
        parts.append("|".join(map(to_wikitext, node.args[1:])))
        parts.append("}}")
    elif kind == NodeKind.URL:
        parts.append("[")
        parts.append(to_wikitext(node.args))
        parts.append("]")
    elif kind == NodeKind.TABLE:
        parts.append("\n{{| {}\n".format(to_attrs(node)))
        parts.append(to_wikitext(node.children))
        parts.append("\n|}\n")
    elif kind == NodeKind.TABLE_CAPTION:
        parts.append("\n|+ {}\n".format(to_attrs(node)))
        parts.append(to_wikitext(node.children))
    elif kind == NodeKind.TABLE_ROW:
        parts.append("\n|- {}\n".format(to_attrs(node)))
        parts.append(to_wikitext(node.children))
    elif kind == NodeKind.TABLE_HEADER_CELL:
        parts.append("\n! {}\n".format(to_attrs(node)))
        parts.append(to_wikitext(node.children))
    elif kind == NodeKind.TABLE_CELL:
        parts.append("\n| {}\n".format(to_attrs(node)))
        parts.append(to_wikitext(node.children))
    elif kind == NodeKind.MAGIC_WORD:
        parts.append("\n{}\n".format(node.args))
    elif kind == NodeKind.HTML:
        if node.children:
            parts.append("<{}".format(node.args))
            if node.attrs:
                parts.append(" ")
                parts.append(to_attrs(node))
            parts.append(">")
            parts.append(to_wikitext(node.children))
            parts.append("</{}>".format(node.args))
        else:
            parts.append("<{}".format(node.args))
            if node.attrs:
                parts.append(" ")
                parts.append(to_attrs(node))
            parts.append(" />")
    elif kind == NodeKind.ROOT:
        parts.append(to_wikitext(node.children))
    elif kind == NodeKind.BOLD:
        parts.append("'''")
        parts.append(to_wikitext(node.children))
        parts.append("'''")
    elif kind == NodeKind.ITALIC:
        parts.append("''")
        parts.append(to_wikitext(node.children))
        parts.append("''")
    else:
        raise RuntimeError("unimplemented {}".format(kind))
    return "".join(parts)
