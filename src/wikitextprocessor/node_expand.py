# Expanding parse tree nodes to Wikitext or HTML or plain text
#
# Copyright (c) 2020-2022 Tatu Ylonen.  See file LICENSE and https://ylonen.org

import re
import urllib.parse
from typing import (
    TYPE_CHECKING,
    Callable,
    Optional,
    Union,
)

from .parser import (
    GeneralNode,
    NodeKind,
    WikiNode,
    WikiNodeListArgs,
)
from .wikihtml import ALLOWED_HTML_TAGS

if TYPE_CHECKING:
    from wikitextprocessor.core import (
        PostTemplateFnCallable,
        TemplateFnCallable,
        Wtp,
    )

NodeHandlerFnCallable = Callable[[WikiNode], Union[None, GeneralNode]]

kind_to_level: dict[NodeKind, str] = {
    NodeKind.LEVEL2: "==",
    NodeKind.LEVEL3: "===",
    NodeKind.LEVEL4: "====",
    NodeKind.LEVEL5: "=====",
    NodeKind.LEVEL6: "======",
}


def to_attrs(node: WikiNode) -> str:
    parts: list[str] = []
    for k, v in node.attrs.items():
        k = str(k)
        if not v:
            parts.append(k)
            continue
        v = urllib.parse.quote_plus(str(v))
        parts.append('{}="{}"'.format(k, v))
    return " ".join(parts)


def to_wikitext(
    node: GeneralNode,
    node_handler_fn: Optional[NodeHandlerFnCallable] = None,
) -> str:
    """Converts a parse tree (or subtree) back to Wikitext.
    If ``node_handler_fn`` is supplied, it will be called for each WikiNode
    being rendered, and if it returns non-None, the returned value will be
    rendered instead of the node.  The returned value may be a list, tuple,
    string, or a WikiNode.  ``node_handler_fn`` will be called for any
    WikiNodes in the returned value."""
    assert node_handler_fn is None or callable(node_handler_fn)

    def recurse(node: Union[GeneralNode, WikiNodeListArgs]) -> str:
        if isinstance(node, str):
            # Certain constructs needs to be protected so that they don't get
            # parsed when we convert back and forth between wikitext and parsed
            # representations.
            node = re.sub(r"(?si)\[\[", "[<noinclude/>[", node)
            node = re.sub(r"(?si)\]\]", "]<noinclude/>]", node)
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
        parts: list[str] = []
        if kind in kind_to_level:
            tag = kind_to_level[kind]
            t = recurse(node.largs)  # This is where WikiNodeListArgs is needed
            # if you were wondering...
            parts.append("\n{} {} {}\n".format(tag, t, tag))
            parts.append(recurse(node.children))
        elif kind == NodeKind.HLINE:
            parts.append("\n----\n")
        elif kind == NodeKind.LIST:
            parts.append(recurse(node.children))
        elif kind == NodeKind.LIST_ITEM:
            parts.append(node.sarg)
            prev_list = False
            for x in node.children:
                if prev_list:
                    parts.append(node.sarg + ":")
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
            parts.append("|".join(map(recurse, node.largs)))
            parts.append("]]")
            parts.append(recurse(node.children))
        elif kind == NodeKind.TEMPLATE:
            parts.append("{{")
            parts.append("|".join(map(recurse, node.largs)))
            parts.append("}}")
        elif kind == NodeKind.TEMPLATE_ARG:
            parts.append("{{{")
            parts.append("|".join(map(recurse, node.largs)))
            parts.append("}}}")
        elif kind == NodeKind.PARSER_FN:
            first_part = "{{" + recurse(node.largs[0])
            if len(node.largs) > 1:
                # extra empty arg could affect expand result
                # only add ":" if parser function has args
                first_part += ":"
            parts.append(first_part)
            parts.append("|".join(map(recurse, node.largs[1:])))
            parts.append("}}")
        elif kind == NodeKind.URL:
            parts.append("[")
            if node.largs:
                parts.append(recurse(node.largs[0]))
                for x2 in node.largs[1:]:
                    parts.append(" ")
                    parts.append(recurse(x2))
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
                parts.append(
                    "\n! {} |{}\n".format(
                        to_attrs(node), recurse(node.children)
                    )
                )
            else:
                parts.append("\n!{}\n".format(recurse(node.children)))
        elif kind == NodeKind.TABLE_CELL:
            if node.attrs:
                parts.append(
                    "\n| {} |{}\n".format(
                        to_attrs(node), recurse(node.children)
                    )
                )
            else:
                parts.append("\n|{}\n".format(recurse(node.children)))
        elif kind == NodeKind.MAGIC_WORD:
            parts.append("\n{}\n".format(node.sarg))
        elif kind == NodeKind.HTML:
            if node.children:
                parts.append("<{}".format(node.sarg))
                if node.attrs:
                    parts.append(" ")
                    parts.append(to_attrs(node))
                parts.append(">")
                parts.append(recurse(node.children))
                parts.append("</{}>".format(node.sarg))
            else:
                parts.append("<{}".format(node.sarg))
                if node.attrs:
                    parts.append(" ")
                    parts.append(to_attrs(node))
                # We're using ALLOWED_HTML_TAGS here because we don't have
                # ctx.allowed_html_tags in this function, and it doesn't
                # *really* matter if there's an extract / at the end.
                if ALLOWED_HTML_TAGS.get(node.sarg, {"no-end-tag": True}).get(
                    "no-end-tag"
                ):
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


def to_html(
    ctx: "Wtp",
    node: GeneralNode,
    template_fn: Optional["TemplateFnCallable"] = None,
    post_template_fn: Optional["PostTemplateFnCallable"] = None,
    node_handler_fn: Optional[NodeHandlerFnCallable] = None,
) -> str:
    """Converts the parse (sub-)tree at ``node`` to HTML, expanding all
    templates in it."""
    assert template_fn is None or callable(template_fn)
    assert post_template_fn is None or callable(post_template_fn)
    assert node_handler_fn is None or callable(node_handler_fn)
    text = to_wikitext(node, node_handler_fn=node_handler_fn)
    # XXX we need to expand wikitext formatting.  That would best be done
    # in to_wikitext() or something similar.
    expanded = ctx.expand(
        text, template_fn=template_fn, post_template_fn=post_template_fn
    )
    # print("TO_HTML: node={!r} text={!r} expanded={!r}"
    #       .format(node, text, expanded))
    return expanded


def to_text(
    ctx: "Wtp",
    node: GeneralNode,
    template_fn: Optional["TemplateFnCallable"] = None,
    post_template_fn: Optional["PostTemplateFnCallable"] = None,
    node_handler_fn: Optional[NodeHandlerFnCallable] = None,
) -> str:
    """Converts the parse (sub-)tree at ``node`` to plain text, expanding
    all templates in it and stripping HTML tags."""
    assert template_fn is None or callable(template_fn)
    assert post_template_fn is None or callable(post_template_fn)
    assert node_handler_fn is None or callable(node_handler_fn)
    s = to_html(
        ctx,
        node,
        template_fn=template_fn,
        post_template_fn=post_template_fn,
        node_handler_fn=node_handler_fn,
    )
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
    # s = re.sub(r"(?s)[][]", "", s)
    s = re.sub(r"\n\n\n+", "\n\n", s)
    # print("TO_TEXT result:", repr(s))
    return s.strip()
