# Expanding parse tree nodes to Wikitext or HTML or plain text
#
# Copyright (c) 2020-2021 Tatu Ylonen.  See file LICENSE and https://ylonen.org

import re
import html
import urllib.parse
from .parser import WikiNode, NodeKind
from .wikihtml import ALLOWED_HTML_TAGS

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


def to_wikitext(node, node_handler_fn=None):
    """Converts a parse tree (or subtree) back to Wikitext.
    If ``node_handler_fn`` is supplied, it will be called for each WikiNode
    being rendered, and if it returns non-None, the returned value will be
    rendered instead of the node.  The returned value may be a list, tuple,
    string, or a WikiNode.  ``node_handler_fn`` will be called for any
    WikiNodes in the returned value."""
    assert node_handler_fn is None or callable(node_handler_fn)

    def recurse(node):
        if isinstance(node, str):
            return node
        if isinstance(node, (list, tuple)):
            return "".join(map(recurse, node))
        if not isinstance(node, WikiNode):
            raise RuntimeError("invalid WikiNode: {}".format(node))

        if node_handler_fn is not None:
            ret = node_handler_fn(node)
            if ret is not None and ret is not node:
                if isinstance(ret, (list, tuple)):
                    return "".join(recurse(x) for x in ret)
                return recurse(ret)

        kind = node.kind
        parts = []
        if kind in kind_to_level:
            tag = kind_to_level[kind]
            t = recurse(node.args)
            parts.append("\n{} {} {}\n".format(tag, t, tag))
            parts.append(recurse(node.children))
        elif kind == NodeKind.HLINE:
            parts.append("\n----\n")
        elif kind == NodeKind.LIST:
            parts.append(recurse(node.children))
        elif kind == NodeKind.LIST_ITEM:
            assert isinstance(node.args, str)
            parts.append(node.args)
            prev_list = False
            for x in node.children:
                if prev_list:
                    parts.append(node.args + ":")
                parts.append(recurse(x))
                prev_list = isinstance(x, WikiNode) and x.kind == NodeKind.LIST
        elif kind == NodeKind.PRE:
            parts.append("<pre>")
            parts.append(recurse(node.children))
            parts.append("</pre>")
        elif kind == NodeKind.PREFORMATTED:
            parts.append(recurse(node.children))
        elif kind == NodeKind.LINK:
            parts.append("[[")
            parts.append("|".join(map(recurse, node.args)))
            parts.append("]]")
            parts.append(recurse(node.children))
        elif kind == NodeKind.TEMPLATE:
            parts.append("{{")
            parts.append("|".join(map(recurse, node.args)))
            parts.append("}}")
        elif kind == NodeKind.TEMPLATE_ARG:
            parts.append("{{{")
            parts.append("|".join(map(recurse, node.args)))
            parts.append("}}}")
        elif kind == NodeKind.PARSER_FN:
            parts.append("{{" + recurse(node.args[0]) + ":")
            parts.append("|".join(map(recurse, node.args[1:])))
            parts.append("}}")
        elif kind == NodeKind.URL:
            parts.append("[")
            if node.args:
                parts.append(recurse(node.args[0]))
                for x in node.args[1:]:
                    parts.append(" ")
                    parts.append(recurse(x))
            parts.append("]")
        elif kind == NodeKind.TABLE:
            parts.append("\n{{| {}\n".format(to_attrs(node)))
            parts.append(recurse(node.children))
            parts.append("\n|}\n")
        elif kind == NodeKind.TABLE_CAPTION:
            parts.append("\n|+ {}\n".format(to_attrs(node)))
            parts.append(recurse(node.children))
        elif kind == NodeKind.TABLE_ROW:
            parts.append("\n|- {}\n".format(to_attrs(node)))
            parts.append(recurse(node.children))
        elif kind == NodeKind.TABLE_HEADER_CELL:
            if node.attrs:
                parts.append("\n! {} |{}\n"
                             .format(to_attrs(node),
                                     recurse(node.children)))
            else:
                parts.append("\n!{}\n"
                             .format(recurse(node.children)))
        elif kind == NodeKind.TABLE_CELL:
            if node.attrs:
                parts.append("\n| {} |{}\n"
                             .format(to_attrs(node),
                                     recurse(node.children)))
            else:
                parts.append("\n|{}\n"
                             .format(recurse(node.children)))
        elif kind == NodeKind.MAGIC_WORD:
            parts.append("\n{}\n".format(node.args))
        elif kind == NodeKind.HTML:
            if node.children:
                parts.append("<{}".format(node.args))
                if node.attrs:
                    parts.append(" ")
                    parts.append(to_attrs(node))
                parts.append(">")
                parts.append(recurse(node.children))
                parts.append("</{}>".format(node.args))
            else:
                parts.append("<{}".format(node.args))
                if node.attrs:
                    parts.append(" ")
                    parts.append(to_attrs(node))
                if ALLOWED_HTML_TAGS.get(node.args, {
                        "no-end-tag": True}).get("no-end-tag"):
                    parts.append(">")
                else:
                    parts.append(" />")
        elif kind == NodeKind.ROOT:
            parts.append(recurse(node.children))
        elif kind == NodeKind.BOLD:
            parts.append("'''")
            parts.append(recurse(node.children))
            parts.append("'''")
        elif kind == NodeKind.ITALIC:
            parts.append("''")
            parts.append(recurse(node.children))
            parts.append("''")
        else:
            raise RuntimeError("unimplemented {}".format(kind))
        ret = "".join(parts)
        return ret

    return recurse(node)


def to_html(ctx, node, template_fn=None, post_template_fn=None,
            node_handler_fn=None):
    """Converts the parse (sub-)tree at ``node`` to HTML, expanding all
    templates in it."""
    assert template_fn is None or callable(template_fn)
    assert post_template_fn is None or callable(post_template_fn)
    assert node_handler_fn is None or callable(node_handler_fn)
    text = to_wikitext(node, node_handler_fn=node_handler_fn)
    # XXX we need to expand wikitext formatting.  That would best be done
    # in to_wikitext() or something similar.
    expanded = ctx.expand(text, template_fn=template_fn,
                          post_template_fn=post_template_fn)
    # print("TO_HTML: node={!r} text={!r} expanded={!r}"
    #       .format(node, text, expanded))
    return expanded


def to_text(ctx, node, template_fn=None, post_template_fn=None,
            node_handler_fn=None):
    """Converts the parse (sub-)tree at ``node`` to plain text, expanding
    all templates in it and stripping HTML tags."""
    assert template_fn is None or callable(template_fn)
    assert post_template_fn is None or callable(post_template_fn)
    assert node_handler_fn is None or callable(node_handler_fn)
    s = to_html(ctx, node, template_fn=template_fn,
                post_template_fn=post_template_fn,
                node_handler_fn=node_handler_fn)
    # print("TO_TEXT:", repr(s))
    s = re.sub(r"(?is)<\s*ref\s*[^>]*?>\s*.*?<\s*/\s*ref\s*>\n*", "", s)
    s = re.sub(r"(?is)<\s*/?\s*h[123456]\b[^>]*>\n*", "\n\n", s)
    s = re.sub(r"(?is)<\s*/?\s*div[123456]\b[^>]*>\n*", "\n\n", s)
    s = re.sub(r"(?s)<\s*br\s*/?>\n*", "\n\n", s)
    s = re.sub(r"(?s)<\s*hr\s*/?>\n*", "\n\n----\n\n", s)
    s = re.sub(r"(?s)<\s*[^/][^>]*>\s*", "", s)
    s = re.sub(r"(?s)<\s*/\s*[^>]+>\n*", "", s)
    # Remove category links
    s = re.sub(r"(?s)\[\[\s*Category:[^]<>]*\]\]", "", s)
    s = re.sub(r"(?s)\[\[([^]|<>]*?\|([^]]*?))\]\]", r"\2", s)
    s = re.sub(r"(?s)\[(https?:|mailto:)?//[^]\s<>]+\s+([^]]+)\]", r"\2", s)
    #s = re.sub(r"(?s)[][]", "", s)
    s = re.sub(r"\n\n\n+", "\n\n", s)
    # print("TO_TEXT result:", repr(s))
    return s.strip()
