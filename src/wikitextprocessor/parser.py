# Simple WikiMedia markup (WikiText) syntax parser
#
# Copyright (c) 2020-2022 Tatu Ylonen.  See file LICENSE and https://ylonen.org
import enum
import html
import re
from collections import defaultdict
from collections.abc import Iterator
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Literal,
    Optional,
    Union,
    overload,
)

from .common import (
    MAGIC_FIRST,
    MAGIC_LAST,
    MAGIC_NOWIKI_CHAR,
    MAGIC_SQUOTE_CHAR,
    nowiki_quote,
)
from .parserfns import PARSER_FUNCTIONS

if TYPE_CHECKING:
    from .core import Wtp


def set_html_tag_data(ctx: "Wtp") -> dict[str, set[str]]:
    # Set of tags that can be parents of "flow" parents
    html_flow_parents: set[str] = set(
        k
        for k, v in ctx.allowed_html_tags.items()
        if "flow" in v.get("content", []) or "*" in v.get("content", [])
    )

    # Set of tags that can be parents of "phrasing" parents (includes those
    # of flow parents since flow implies phrasing)
    html_phrasing_parents = set(
        k
        for k, v in ctx.allowed_html_tags.items()
        if "phrasing" in v.get("content", [])
        or "flow" in v.get("content", [])
        or "*" in v.get("content", [])
    )

    # Mapping from HTML tag or "text" to permitted parent tags
    html_permitted_parents = {
        k: (
            (
                html_flow_parents
                if "flow" in v.get("parents", []) or "*" in v.get("parents", [])
                else set()
            )
            | (
                html_phrasing_parents
                if "phrasing" in v.get("parents", [])
                or "*" in v.get("parents", [])
                else set()
            )
            | set(v.get("parents", []))
        )
        for k, v in ctx.allowed_html_tags.items()
    }
    html_permitted_parents["text"] = html_phrasing_parents

    return html_permitted_parents


# Set of HTML tag like names that we treat as literal without any warning
SILENT_HTML_LIKE: set[str] = set(
    [
        "gu",
        "qu",
        "e",
    ]
)


# MediaWiki magic words.  See https://www.mediawiki.org/wiki/Help:Magic_words
MAGIC_WORDS: set[str] = set(
    [
        "__NOTOC__",
        "__FORCETOC__",
        "__TOC__",
        "__NOEDITSECTION__",
        "__NEWSECTIONLINK__",
        "__NONEWSECTIONLINK__",
        "__NOGALLERY__",
        "__HIDDENCAT__",
        "__EXPECTUNUSEDCATEGORY__",
        "__NOCONTENTCONVERT__",
        "__NOCC__",
        "__NOTITLECONVERT__",
        "__NOTC__",
        "__START__",
        "__END__",
        "__INDEX__",
        "__NOINDEX__",
        "__STATICREDIRECT__",
        "__NOGLOBAL__",
        "__DISAMBIG__",
    ]
)


@enum.unique
class NodeKind(enum.Flag):
    """Node types in the parse tree."""

    # Root node of the tree.  This represents the parsed document.
    # Its arguments are [pagetitle].
    ROOT = enum.auto()

    # Level 1 title, used in Russian Wiktionary as language title.
    LEVEL1 = enum.auto()

    # Level2 subtitle.  Arguments are the title, children are what the section
    # contains.
    LEVEL2 = enum.auto()

    # Level3 subtitle
    LEVEL3 = enum.auto()

    # Level4 subtitle
    LEVEL4 = enum.auto()

    # Level5 subtitle
    LEVEL5 = enum.auto()

    # Level6 subtitle
    LEVEL6 = enum.auto()

    # Content to be rendered in italic.  Content is in children.
    ITALIC = enum.auto()

    # Content to be rendered in bold.  Content is in children.
    BOLD = enum.auto()

    # Horizontal line.  No arguments or children.
    HLINE = enum.auto()

    # A list.  Each list will be started with this node, also nested
    # lists.  Args is a string that contains the prefix used to open the list.
    # Children will contain LIST_ITEM nodes that belong to this list.
    # For definition lists the prefix ends in ";".
    # Prefixes ending with : are either for items that are just meant
    # to be indented (without numbers or list markers), or are part
    # of a definition after ";". We leave this to be interpreted by
    # the user, because it depends a bit on the Wiki-project itself
    # how ":" is used in general; one of the uses is to concatenate
    # data to the end of the parent list node, instead of creating
    # sublists, but because this loses some data that is useful for
    # parsing and interpretation, we do not perform the concatenation
    # in Wikitextprocessor.
    LIST = enum.auto()  # args = prefix for all items of this list

    # A list item.  Nested items will be in children.  Items on the same
    # level will be on the same level.  There is no explicit node for a list.
    # Args is directly the token for this item (not as a list).  Children
    # is what goes in this list item.  List items where the prefix ends in
    # ";" are definition list items.  For them, children contain the item
    # to be defined and node.definition contains the definition, which has
    # the same format as children (i.e., a list of strings and WikiNode).
    LIST_ITEM = enum.auto()  # args = token for this item

    # Preformatted text were markup is interpreted.  Content is in children.
    # Indicated in WikiText by starting lines with a space.
    PREFORMATTED = enum.auto()  # Preformatted inline text

    # Preformatted text where markup is NOT interpreted.  Content is in
    # children. Indicated in WikiText by <pre>...</pre>.
    PRE = enum.auto()  # Preformatted text where specials not interpreted

    # An internal Wikimedia link (marked with [[...]]).  The link arguments
    # are in args.  This tag is also used for media inclusion.  Links with
    # trailing word end immediately after the link have the trailing part
    # in link children.
    LINK = enum.auto()

    # A template call (transclusion).  Template name is in first argument
    # and template arguments in subsequent args.  Children are not used.
    # In WikiText {{name|arg1|...}}.
    TEMPLATE = enum.auto()

    # A template argument expansion.  Argument name is in first argument and
    # subsequent arguments in remaining arguments.  Children are not used.
    # In WikiText {{{name|...}}}
    TEMPLATE_ARG = enum.auto()

    # A parser function invocation.  This is also used for built-in
    # variables such as {{PAGENAME}}.  Parser function name is in
    # first argument and subsequent arguments are its parameters.
    # Children are not used.  In WikiText {{name:arg1|arg2|...}}.
    PARSER_FN = enum.auto()

    # An external URL.  The first argument is the URL.  The second optional
    # argument is the display text. Children are not used.
    URL = enum.auto()

    # A table.  Content is in children.
    TABLE = enum.auto()

    # A table caption (under TABLE).  Content is in children.
    TABLE_CAPTION = enum.auto()

    # A table row (under TABLE).  Content is in children.
    TABLE_ROW = enum.auto()

    # A table header cell (under TABLE_ROW).  Content is in children.
    # Rows where all cells are header cells are header rows.
    TABLE_HEADER_CELL = enum.auto()

    # A table cell (under TABLE_ROW).  Content is in children.
    TABLE_CELL = enum.auto()

    # A MediaWiki magic word.  The magic word is assigned directly to args
    # (not as a list).  Children are not used.
    MAGIC_WORD = enum.auto()

    # HTML tag (open or close tag).  Pairs of open and close tags are
    # merged into a single node and the content between them is stored
    # in the node's children.  Args is the name of the tag directly
    # (i.e., not a list and always without a slash).  Attrs contains
    # attributes from the HTML start tag.  Contents in a paired tag
    # are stored in ``children``.
    HTML = enum.auto()


# Maps subtitle token to its kind
SUBTITLE_TO_KIND: dict[str, NodeKind] = {
    "=": NodeKind.LEVEL1,
    "==": NodeKind.LEVEL2,
    "===": NodeKind.LEVEL3,
    "====": NodeKind.LEVEL4,
    "=====": NodeKind.LEVEL5,
    "======": NodeKind.LEVEL6,
}

LITERAL_LEVEL_KINDS = Literal[
    NodeKind.LEVEL1
    | NodeKind.LEVEL2
    | NodeKind.LEVEL3
    | NodeKind.LEVEL4
    | NodeKind.LEVEL5
    | NodeKind.LEVEL6
]

# Maps subtitle node kind to its level.  Keys include all title/subtitle nodes
# (this is also used like a set of all subtitle kinds, including the root).
KIND_TO_LEVEL: dict[NodeKind, int] = {
    v: len(k) for k, v in SUBTITLE_TO_KIND.items()
}
KIND_TO_LEVEL[NodeKind.ROOT] = 0

# This variable could be used in `WikiNode.find_child()` to search level nodes
LEVEL_KIND_FLAGS = (
    NodeKind.LEVEL1
    | NodeKind.LEVEL2
    | NodeKind.LEVEL3
    | NodeKind.LEVEL4
    | NodeKind.LEVEL5
    | NodeKind.LEVEL6
)

# Node types that have arguments separated by the vertical bar (|)
HAVE_ARGS_KIND_FLAGS = (
    NodeKind.LINK
    | NodeKind.TEMPLATE
    | NodeKind.TEMPLATE_ARG
    | NodeKind.PARSER_FN
    | NodeKind.URL
)


# Node kinds that generate an error if they have not been properly closed.
MUST_CLOSE_KIND_FLAGS = (
    NodeKind.ITALIC
    | NodeKind.BOLD
    | NodeKind.PRE
    | NodeKind.HTML
    | NodeKind.LINK
    | NodeKind.TEMPLATE
    | NodeKind.TEMPLATE_ARG
    | NodeKind.PARSER_FN
    | NodeKind.URL
    | NodeKind.TABLE
)

# regex for finding html-tags so that we can replace single-quotes
# inside of them with magic characters.
# the (?:) signifies a non-capturing group, which is necessary for
# re.split; if the splitting pattern has capturing groups (like
# the outer parentheses here), those groups are sent out by
# the iterator; otherwise it skips the splitting pattern.
# This means that if you have nesting capturing groups,
# the contents will be repeated partly.


def set_inside_html_tags_re(ctx: "Wtp") -> re.Pattern:
    return re.compile(
        r"(<(?:" + r"|".join(ctx.allowed_html_tags.keys()) + r")[^><]*>)",
        re.IGNORECASE,
    )


# We don't have specs for this, so let's assume...
# HTML nodes have args be strings.
# Others have a list of lists, *at least*.
# Sometimes, args.append(children) happens, so those
# lists can contain at least strings and WikiNodes.
# I think there is no third list layer, maximum is args[x][y].
WikiNodeChildrenList = list[Union[str, "WikiNode"]]
WikiNodeArgsSublist = WikiNodeChildrenList  # XXX Currently identical to above
# WikiNodeArgs = Union[str, # Just a string
#                      List[
#                         Union[
#                             WikiNodeArgsSublist,
#                             WikiNodeChildrenList]
#                         ]
#                     ]
WikiNodeStrArg = str
WikiNodeListArgs = list[WikiNodeArgsSublist]
WikiNodeHTMLAttrsDict = dict[str, str]  # XXX Probably not just HTML...


class WikiNode:
    """Node in the parse tree for WikiMedia text."""

    __slots__ = (
        "kind",
        "sarg",
        "largs",
        "attrs",
        "children",
        "loc",
        "definition",
        "temp_head",
    )

    def __init__(self, kind: NodeKind, loc: int) -> None:
        assert isinstance(kind, NodeKind)
        assert isinstance(loc, int)
        self.kind = kind
        self.sarg: WikiNodeStrArg = ""
        self.largs: WikiNodeListArgs = []  # String, or a list of lists
        self.attrs: WikiNodeHTMLAttrsDict = {}
        self.children: WikiNodeChildrenList = []
        self.loc = loc  # used for debugging lines
        self.definition: Optional[WikiNodeChildrenList] = None
        self.temp_head: Optional[WikiNodeChildrenList] = None

    def __str__(self) -> str:
        return "<{}({}){} {}>".format(
            self.kind.name,
            self.sarg if self.sarg else ", ".join(map(repr, self.largs)),
            self.attrs,
            ", ".join(map(repr, self.children)),
        )

    def __repr__(self) -> str:
        return self.__str__()

    @overload
    def find_child(
        self,
        target_kinds: LITERAL_LEVEL_KINDS,
        with_index: Literal[True],
    ) -> Iterator[tuple[int, "LevelNode"]]: ...

    @overload
    def find_child(
        self,
        target_kinds: LITERAL_LEVEL_KINDS,
        with_index: Literal[False] = ...,
    ) -> Iterator["LevelNode"]: ...

    @overload
    def find_child(
        self,
        target_kinds: Literal[NodeKind.TEMPLATE],
        with_index: Literal[True],
    ) -> Iterator[tuple[int, "TemplateNode"]]: ...

    @overload
    def find_child(
        self,
        target_kinds: Literal[NodeKind.TEMPLATE],
        with_index: Literal[False] = ...,
    ) -> Iterator["TemplateNode"]: ...

    @overload
    def find_child(
        self,
        target_kinds: Literal[NodeKind.HTML],
        with_index: Literal[True],
    ) -> Iterator[tuple[int, "HTMLNode"]]: ...

    @overload
    def find_child(
        self,
        target_kinds: Literal[NodeKind.HTML],
        with_index: Literal[False] = ...,
    ) -> Iterator["HTMLNode"]: ...

    @overload
    def find_child(
        self, target_kinds: NodeKind, with_index: Literal[True]
    ) -> Iterator[tuple[int, "WikiNode"]]: ...

    @overload
    def find_child(
        self, target_kinds: NodeKind, with_index: Literal[False] = ...
    ) -> Iterator["WikiNode"]: ...

    def find_child(
        self,
        target_kinds: NodeKind,
        with_index: bool = False,
    ) -> Iterator[Union["WikiNode", tuple[int, "WikiNode"]]]:
        """
        Find direct child nodes that match the target node type, also return
        the node index that could be used to divide child node list.

        `target_kinds` could be a single NodeKind enum member or multiple
        NodeKind members combined with the "|"(OR) operator.
        """
        for index, child in enumerate(self.children):
            if isinstance(child, WikiNode) and child.kind in target_kinds:
                if with_index:
                    yield index, child
                else:
                    yield child

    def invert_find_child(
        self,
        target_kinds: NodeKind,
        include_empty_str: bool = False,
    ) -> Iterator[Union["WikiNode", str]]:
        # Find direct child nodes that don't match the target node type.
        for child in self.children:
            if isinstance(child, str) and (
                include_empty_str or len(child.strip()) > 0
            ):
                yield child
            elif isinstance(child, WikiNode) and child.kind not in target_kinds:
                yield child

    def _find_node_recursively(
        self,
        start_node: "WikiNode",
        current_node: Union["WikiNode", str],
        target_kinds: Union[list[NodeKind], NodeKind],
    ) -> Iterator["WikiNode"]:
        # Find nodes in WikiNode.children and WikiNode.largs recursively.
        # Search WikiNode.largs probably is not needed, add it because the
        # original `contains_list()` in wiktextract does this.
        if isinstance(current_node, WikiNode):
            if current_node != start_node and current_node.kind in target_kinds:
                yield current_node
            for child in current_node.children:
                yield from self._find_node_recursively(
                    start_node, child, target_kinds
                )
            for arg_list in current_node.largs:
                for arg in arg_list:
                    yield from self._find_node_recursively(
                        start_node, arg, target_kinds
                    )

    def find_child_recursively(
        self, target_kinds: Union[list[NodeKind], NodeKind]
    ) -> Iterator["WikiNode"]:
        # Similar to `find_child()` but also search nested nodes.
        yield from self._find_node_recursively(self, self, target_kinds)

    def contain_node(
        self, target_kinds: Union[list[NodeKind], NodeKind]
    ) -> bool:
        for node in self._find_node_recursively(self, self, target_kinds):
            return True
        return False

    def filter_empty_str_child(self) -> Iterator[Union[str, "WikiNode"]]:
        # Remove string child nodes that only contain space or new line.
        for node in self.children:
            if isinstance(node, str):
                if len(node.strip()) > 0:
                    yield node
            else:
                yield node

    @overload
    def find_html(
        self,
        target_tags: str | list[str],
        with_index: Literal[True],
        attr_name: str,
        attr_value: str,
    ) -> Iterator[tuple[int, "HTMLNode"]]: ...

    @overload
    def find_html(
        self,
        target_tags: str | list[str],
        with_index: Literal[False] = ...,
        attr_name: str = ...,
        attr_value: str = ...,
    ) -> Iterator["HTMLNode"]: ...

    def find_html(
        self,
        target_tags: str | list[str],
        with_index: bool = False,
        attr_name: str = "",
        attr_value: str = "",
    ) -> Iterator[Union["HTMLNode", tuple[int, "HTMLNode"]]]:
        # Find direct HTMl child nodes match the target tag and attribute.
        for index, node in self.find_child(NodeKind.HTML, True):
            if TYPE_CHECKING:
                assert isinstance(node, HTMLNode)
            # node.tag is an alias for node.sarg defined in HTMLNode
            if isinstance(target_tags, str):
                target_tags = [target_tags]
            if node.tag in target_tags:
                if len(attr_name) > 0 and attr_value not in node.attrs.get(
                    attr_name, {}
                ):
                    continue
                if with_index:
                    yield index, node
                else:
                    yield node

    def find_html_recursively(
        self,
        target_tag: str,
        attr_name: str = "",
        attr_value: str = "",
    ) -> Iterator["HTMLNode"]:
        for node in self.find_child_recursively(NodeKind.HTML):
            if TYPE_CHECKING:
                assert isinstance(node, HTMLNode)
            if node.tag == target_tag:
                if len(attr_name) > 0 and attr_value not in node.attrs.get(
                    attr_name, {}
                ):
                    continue
                yield node


# We have many functions that can take any 'level' of a WikiNode tree,
# which includes lists (and tuples, although that might be rare or even
# non-existent in the codebase.
GeneralNode = Union[
    str,
    WikiNode,
    list[Union[str, WikiNode]],
    tuple[Union[str, WikiNode], ...],
    list[str],
    list[WikiNode],
    tuple[str, ...],
    tuple[WikiNode, ...],
    list[list[Union[str, WikiNode]]],  # for node largs specifically
]

TemplateParameters = dict[
    Union[str, int],
    Union[str, WikiNode, list[Union[str, WikiNode]]],
]


class TemplateNode(WikiNode):
    def __init__(self, linenum: int, ns_prefixes: tuple[str, ...]):
        super().__init__(NodeKind.TEMPLATE, linenum)
        self._template_parameters: Optional[TemplateParameters] = None
        self._ns_prefixes = ns_prefixes

    @property
    def template_name(self) -> str:
        if (
            isinstance(self.largs, list)
            and len(self.largs) > 0
            and isinstance(self.largs[0], list)
            and len(self.largs[0]) > 0
        ):
            if isinstance(self.largs[0][0], str):
                name = self.largs[0][0].strip()
                if name.lower().startswith(self._ns_prefixes):  # remove prefix
                    name = name[name.index(":") + 1 :]
                return name
            else:
                return "<WikiNode>"
        return ""

    @property
    def template_parameters(self) -> TemplateParameters:
        # Convert the list type arguments to a dictionary.
        if self._template_parameters is not None:
            return self._template_parameters

        parameters: Any = defaultdict(list)
        unnamed_parameter_index = 0
        for parameter_list in self.largs[1:]:
            is_named = False
            parameter_name: Union[str, int] = ""
            if len(parameter_list) == 0:
                unnamed_parameter_index += 1
                parameters[unnamed_parameter_index] = ""

            for index, parameter in enumerate(parameter_list):
                if index == 0:
                    if not isinstance(parameter, str):
                        unnamed_parameter_index += 1
                    else:
                        if "=" in parameter:
                            is_named = True
                        else:
                            unnamed_parameter_index += 1
                        if is_named:
                            parameter = parameter.strip()
                        if len(parameter) == 0:
                            continue
                        if "=" in parameter:
                            equal_sign_index = parameter.index("=")
                            parameter_name = parameter[
                                :equal_sign_index
                            ].strip()
                            parameter_value = parameter[
                                equal_sign_index + 1 :
                            ].strip()
                            if parameter_name.isdigit():  # value contains "="
                                parameter_name = int(parameter_name)
                                is_named = False
                            if len(parameter_value) > 0:
                                parameters[parameter_name].append(
                                    parameter_value
                                )
                            continue

                if (
                    is_named
                    and isinstance(parameter_name, str)
                    and len(parameter_name) > 0
                ) or isinstance(parameter_name, int):
                    parameters[parameter_name].append(parameter)
                else:
                    parameters[unnamed_parameter_index].append(parameter)

        for p_name, p_value in parameters.items():
            if isinstance(p_value, list) and len(p_value) == 1:
                parameters[p_name] = p_value[0]

        self._template_parameters = dict(parameters)
        return self._template_parameters


class HTMLNode(WikiNode):
    def __init__(self, linenum: int):
        super().__init__(NodeKind.HTML, linenum)

    @property
    def tag(self):
        return self.sarg


class LevelNode(WikiNode):
    def __init__(self, level_type: NodeKind, linenum: int):
        super().__init__(level_type, linenum)

    @overload
    def find_content(
        self, target_types: Literal[NodeKind.TEMPLATE]
    ) -> Iterator[TemplateNode]: ...

    @overload
    def find_content(self, target_types: NodeKind) -> Iterator[WikiNode]: ...

    def find_content(self, target_types: NodeKind) -> Iterator[WikiNode]:
        """
        Find WikiNode in `WikiNode.largs`. This method could be used to find
        templates "inside" the level node but not the child nodes under the
        level node.
        """
        for content in (
            level_node_arg
            for level_node_arg_list in self.largs
            for level_node_arg in level_node_arg_list
            if isinstance(level_node_arg, WikiNode)
            and level_node_arg.kind in target_types
        ):
            yield content


def _parser_push(ctx: "Wtp", kind: NodeKind) -> WikiNode:
    """Pushes a new node of the specified kind onto the stack."""
    assert isinstance(kind, NodeKind)
    _parser_merge_str_children(ctx)
    node: WikiNode
    if kind == NodeKind.TEMPLATE:
        node = TemplateNode(
            ctx.linenum,
            ctx.namespace_prefixes(ctx.NAMESPACE_DATA["Template"]["id"]),
        )
    elif kind == NodeKind.HTML:
        node = HTMLNode(ctx.linenum)
    elif kind in KIND_TO_LEVEL:
        node = LevelNode(kind, ctx.linenum)
    else:
        node = WikiNode(kind, ctx.linenum)
    prev = ctx.parser_stack[-1]
    prev.children.append(node)
    ctx.parser_stack.append(node)
    ctx.suppress_special = False
    return node


def _parser_merge_str_children(ctx: "Wtp") -> None:
    """Merges multiple consecutive str children into one.  We merge them
    as a separate step, because this gives linear worst-case time, vs.
    quadratic worst case (albeit with lower constant factor) if we just
    added to the previously accumulated string in text_fn() instead.
    Importantly, this also finalizes string children so that any magic
    characters are expanded and nowiki characters removed."""
    node = ctx.parser_stack[-1]
    new_children: WikiNodeChildrenList = []
    strings: list[str] = []
    for x in node.children:
        if isinstance(x, str):
            strings.append(x)
        else:
            if strings:
                s = ctx._finalize_expand("".join(strings))
                if s:
                    new_children.append(s)
                strings = []
            new_children.append(x)
    if strings:
        s = ctx._finalize_expand("".join(strings))
        if s:
            new_children.append(s)
    node.children = new_children


def _parser_pop(ctx: "Wtp", warn_unclosed: bool) -> None:
    """Pops a node from the stack.  If the node has arguments, this moves
    remaining children of the node into its arguments.  If ``warn_unclosed``
    is True, this warns about nodes that should be explicitly closed
    not having been closed.  Also performs certain other operations on
    the parse tree; this is a place for various kludges that manipulate
    the nodes when their parsing completes."""
    assert warn_unclosed in (True, False)
    _parser_merge_str_children(ctx)
    node = ctx.parser_stack[-1]

    # Warn about unclosed syntaxes.
    if warn_unclosed and node.kind in MUST_CLOSE_KIND_FLAGS:
        if node.kind == NodeKind.HTML:
            ctx.debug(
                "HTML tag <{}> not properly closed".format(node.sarg),
                trace="started on line {}, detected on line {}".format(
                    node.loc, ctx.linenum
                ),
                sortid="parser/304",
            )
        elif node.kind == NodeKind.PARSER_FN:
            ctx.debug(
                "parser function invocation {!r} not properly closed".format(
                    node.largs[0]
                ),
                trace="started on line {}, detected on line {}".format(
                    node.loc, ctx.linenum
                ),
                sortid="parser/309",
            )
        elif node.kind == NodeKind.URL and not node.children:
            # This can happen at least when [ is inside template argument.
            ctx.parser_stack.pop()
            node2 = ctx.parser_stack[-1]
            node3 = node2.children.pop()
            assert node3 is node
            text_fn(ctx, "[")
            return
        elif node.kind in (NodeKind.ITALIC, NodeKind.BOLD):
            # Unbalanced italic/bold annotation is so extremely common
            # in Wiktionary that let's suppress any warnings about
            # them.
            pass
        else:
            ctx.debug(
                "{} not properly closed".format(node.kind.name),
                trace="started on line {}, detected on line {}".format(
                    node.loc, ctx.linenum
                ),
                sortid="parser/328",
            )

    # When popping BOLD and ITALIC nodes, if the node has no children,
    # just remove the node from it's parent's children.  We may otherwise
    # generate spurious empty BOLD and ITALIC nodes when closing them
    # out-of-order (which happens always with '''''bolditalic''''').
    if node.kind in (NodeKind.BOLD, NodeKind.ITALIC) and not node.children:
        ctx.parser_stack.pop()
        if TYPE_CHECKING:
            assert isinstance(ctx.parser_stack[-1].children[-1], WikiNode)
        assert ctx.parser_stack[-1].children[-1].kind == node.kind
        ctx.parser_stack[-1].children.pop()
        return

    # If the node has arguments, move remaining children to be the last
    # argument
    if node.kind in HAVE_ARGS_KIND_FLAGS:
        node.largs.append(node.children)
        node.children = []

    # When popping a TEMPLATE, check if its name is a constant that
    # is a known parser function (including predefined variable).
    # If so, turn this node into a PARSER_FN node.
    if (
        node.kind == NodeKind.TEMPLATE
        and node.largs
        and len(node.largs[0]) == 1
        and isinstance(node.largs[0][0], str)
        and node.largs[0][0] in PARSER_FUNCTIONS
    ):
        # Change node type to PARSER_FN.  Otherwise it has identical
        # structure to a TEMPLATE.
        node.kind = NodeKind.PARSER_FN

    # When popping description list nodes that have a definition,
    # shuffle WikiNode.temp_head and children to have head in children and
    # definition in WikiNode.definition
    if (
        node.kind == NodeKind.LIST_ITEM
        and node.sarg.endswith(";")
        and node.temp_head
    ):
        head = node.temp_head
        node.temp_head = None
        node.definition = node.children
        node.children = head

    # Remove the topmost node from the stack.  It should be on its parent's
    # children list.
    ctx.parser_stack.pop()


def _parser_have(ctx: "Wtp", kind_flags: NodeKind) -> bool:
    """Returns True if any node on the stack is of the given kind."""
    assert isinstance(kind_flags, NodeKind)
    for node in ctx.parser_stack:
        if node.kind in kind_flags:
            return True
    return False


def close_begline_lists(ctx: "Wtp") -> None:
    """Closes currently open list if at the beginning of a line."""
    if not (ctx.beginning_of_line and ctx.begline_enabled):
        return
    while _parser_have(ctx, NodeKind.LIST):
        _parser_pop(ctx, True)


def pop_until_nth_list(ctx: "Wtp", list_token: str) -> None:
    """
    Pop nodes in the parser stack until the correct depth.
    """
    if not (ctx.beginning_of_line and ctx.begline_enabled):
        return
    list_count = len(list_token)
    passed_nodes = 0
    for node in ctx.parser_stack:
        passed_nodes += 1
        if node.kind == NodeKind.LIST:
            list_count -= 1
        if list_count == 0:
            break

    if list_token.startswith((":", ";")):
        # pop until target list node's item child node is at the stack top
        # in order to add a new nested list node
        passed_nodes += 1

    # pop until the stack top is the taregt list node
    for _ in range(len(ctx.parser_stack) - passed_nodes):
        _parser_pop(ctx, True)


def text_fn(ctx: "Wtp", token: str) -> None:
    """Inserts the token as raw text into the parse tree."""
    close_begline_lists(ctx)

    node = ctx.parser_stack[-1]

    # Convert certain characters from the token into HTML entities
    # XXX this breaks tags inside templates, e.g. <math> in
    # "conjugacy class"/English examples
    # token = re.sub(r"<", "&lt;", token)
    # token = re.sub(r">", "&gt;", token)

    # External links [https://...] require some magic.  They only seem to
    # be links if the content looks like a URL."""
    if node.kind == NodeKind.URL:
        if not node.largs and not node.children:
            if not re.match(r"(https?:|mailto:|//)", token):
                # It does not look like a URL
                ctx.parser_stack.pop()
                node2 = ctx.parser_stack[-1]
                node3 = node2.children.pop()
                assert node3 is node
                return text_fn(ctx, "[" + token)

        # Whitespaces inside an external link divide its first argument from its
        # second argument.  All remaining words go into the second argument.
        if token.isspace() and not node.largs:
            _parser_merge_str_children(ctx)
            node.largs.append(node.children)
            node.children = []
            return

    # Some nodes are automatically popped on newline/text
    if ctx.beginning_of_line and ctx.begline_enabled:
        while True:
            node = ctx.parser_stack[-1]
            if node.kind == NodeKind.LIST_ITEM:
                if token.startswith(" ") or token[0].startswith("\t"):
                    node.children.append(token)
                    return
                _parser_merge_str_children(ctx)
                if (
                    node.children
                    and isinstance(node.children[-1], str)
                    and (
                        len(node.children) > 1
                        or not node.children[-1].isspace()
                    )
                    and node.children[-1].endswith("\n")
                ):
                    _parser_pop(ctx, False)
                    continue
            elif node.kind == NodeKind.LIST:
                _parser_pop(ctx, False)
                continue
            elif node.kind == NodeKind.PREFORMATTED:
                _parser_merge_str_children(ctx)
                if (
                    node.children
                    and isinstance(node.children[-1], str)
                    and node.children[-1].endswith("\n")
                    and not token.startswith(" ")
                ):
                    _parser_pop(ctx, False)
                    continue
            elif node.kind in (NodeKind.BOLD, NodeKind.ITALIC):
                _parser_merge_str_children(ctx)
                ctx.debug(
                    "{} not properly closed on the same line".format(
                        node.kind.name
                    ),
                    sortid="parser/449",
                )
                _parser_pop(ctx, False)
            break

        # Spaces at the beginning of a line indicate preformatted text
        if token.startswith(" "):
            if ctx.parser_stack[-1].kind in (
                NodeKind.TABLE,
                NodeKind.TABLE_ROW,
            ):
                return
            # print(f"{token=}")
            if (
                node.kind != NodeKind.PREFORMATTED
                and not ctx.pre_parse
                and not any(  # GH issue #336
                    isinstance(n, HTMLNode) and n.tag in ["ref", "p"]
                    for n in ctx.parser_stack
                )
            ):
                node = _parser_push(ctx, NodeKind.PREFORMATTED)

    # If the previous child was a link that doesn't yet have children,
    # and the text to be added starts with valid word characters, assume
    # they are link trail and add them as a child of the link.
    if (
        node.children
        and isinstance(node.children[-1], WikiNode)
        and node.children[-1].kind == NodeKind.LINK
        and not node.children[-1].children
        and not ctx.suppress_special
    ):
        m = re.match(r"(?s)(\w+)(.*)", token)
        if m:
            node.children[-1].children.append(m.group(1))
            token = m.group(2)
            if not token:
                return

    # Add a text child
    node.children.append(token)


def hline_fn(ctx: "Wtp", token: str) -> None:
    """Processes a horizontal line token."""
    # Pop nodes from the stack until we reach a LEVEL2 subtitle or a
    # table element.  We also won't pop HTML nodes as they might appear
    # in template definitions.
    close_begline_lists(ctx)
    while True:
        node = ctx.parser_stack[-1]
        if node.kind in (
            NodeKind.ROOT,
            NodeKind.LEVEL2,
            NodeKind.TABLE,
            NodeKind.TABLE_CAPTION,
            NodeKind.TABLE_ROW,
            NodeKind.TABLE_HEADER_CELL,
            NodeKind.TABLE_CELL,
            NodeKind.HTML,
        ):
            break
        _parser_pop(ctx, True)

    _parser_push(ctx, NodeKind.HLINE)
    _parser_pop(ctx, True)


def subtitle_start_fn(ctx, token) -> None:
    """Processes a subtitle start token.  The token has < prepended to it."""
    assert isinstance(token, str)
    token = token[1:]
    if ctx.pre_parse or not ctx.beginning_of_line:
        return text_fn(ctx, token)

    close_begline_lists(ctx)
    kind = SUBTITLE_TO_KIND[token]
    level = KIND_TO_LEVEL[kind]

    # Keep popping subtitles and other formats until the next subtitle
    # is of a higher level - but only if there are remaining subtitles.
    # Subtitles sometimes occur inside <noinclude> and similar tags, and we
    # don't want to force closing those.
    while any(x.kind in KIND_TO_LEVEL for x in ctx.parser_stack):
        node = ctx.parser_stack[-1]
        if KIND_TO_LEVEL.get(node.kind, 99) < level:
            break
        if node.kind == NodeKind.HTML and node.sarg not in ("span",):
            break
        if node.kind in MUST_CLOSE_KIND_FLAGS & ~NodeKind.HTML:
            break
        _parser_pop(ctx, True)

    # Push the subtitle node.  Subtitle start nodes are guaranteed to have
    # a close node, though the close node could have an incorrect level.
    _parser_push(ctx, kind)
    return None


def subtitle_end_fn(ctx: "Wtp", token: str) -> None:
    """Processes a subtitle end token.  The token has > prepended to it."""
    assert isinstance(token, str)
    token = token[1:]
    if ctx.pre_parse:
        return text_fn(ctx, token)

    kind = SUBTITLE_TO_KIND[token]

    # Keep popping formats until we get to the subtitle node
    pop_count = 0
    find_start_node = False
    for parent_node in reversed(ctx.parser_stack):
        if parent_node.kind == kind:
            for _ in range(pop_count):
                _parser_pop(ctx, True)
            find_start_node = True
            break
        pop_count += 1

    if not find_start_node:
        ctx.debug("can't find subtitle start token", sortid="parser/545")
        return text_fn(ctx, token)

    # Move children of the subtitle node to be its first argument.
    node = ctx.parser_stack[-1]
    _parser_merge_str_children(ctx)
    node.largs.append(node.children)
    node.children = []


def italic_fn(ctx: "Wtp", token: str) -> None:
    """Processes an italic start/end token ('')."""
    if ctx.pre_parse:
        return text_fn(ctx, token)
    close_begline_lists(ctx)

    node = ctx.parser_stack[-1]

    if node.kind in (NodeKind.TEMPLATE, NodeKind.TEMPLATE_ARG):
        return text_fn(ctx, token)

    if not _parser_have(ctx, NodeKind.ITALIC) or node.kind in (NodeKind.LINK,):
        # Push new formatting node
        _parser_push(ctx, NodeKind.ITALIC)
        return

    # Pop the italic.  If there is an intervening BOLD, push it afterwards
    # to allow closing them in either order.
    push_bold = False
    while True:
        node = ctx.parser_stack[-1]
        if node.kind == NodeKind.ITALIC:
            _parser_pop(ctx, False)
            break
        if node.kind == NodeKind.BOLD:
            push_bold = True
        _parser_pop(ctx, False)
    if push_bold:
        _parser_push(ctx, NodeKind.BOLD)


def bold_fn(ctx: "Wtp", token: str) -> None:
    """Processes a bold start/end token (''')."""
    if ctx.pre_parse:
        return text_fn(ctx, token)

    close_begline_lists(ctx)
    node = ctx.parser_stack[-1]

    if node.kind in (NodeKind.TEMPLATE, NodeKind.TEMPLATE_ARG):
        return text_fn(ctx, token)

    if not _parser_have(ctx, NodeKind.BOLD) or node.kind in (NodeKind.LINK,):
        # Push new formatting node
        _parser_push(ctx, NodeKind.BOLD)
        return

    # Pop the bold.  If there is an intervening ITALIC, push it afterwards
    # to allow closing them in either order.
    push_italic = False
    while True:
        node = ctx.parser_stack[-1]
        if node.kind == NodeKind.BOLD:
            _parser_pop(ctx, False)
            break
        if node.kind == NodeKind.ITALIC:
            push_italic = True
        _parser_pop(ctx, False)
    if push_italic:
        _parser_push(ctx, NodeKind.ITALIC)


def url_fn(ctx: "Wtp", token: str) -> None:
    """Processes an URL written as URL in the text (an external link is
    automatically generated)."""
    close_begline_lists(ctx)
    if ctx.pre_parse:
        return text_fn(ctx, token)

    # If the URL ends in certain common punctuation characters, put the
    # punctuation as text after it.
    suffix: Optional[str] = None
    if token[-1] in ".!?,":
        suffix = token[-1]
        token = token[:-1]

    node = ctx.parser_stack[-1]
    if node.kind == NodeKind.URL:
        return text_fn(ctx, token)
    node = _parser_push(ctx, NodeKind.URL)
    text_fn(ctx, token)
    _parser_pop(ctx, False)
    if suffix:
        text_fn(ctx, suffix)


def magic_fn(ctx: "Wtp", token: str) -> None:
    """Handler for a magic character used to encode templates, template
    arguments, and parser function calls."""
    # Close lists if at the beginning of a line
    close_begline_lists(ctx)
    # Handle the magic character token
    idx = ord(token) - MAGIC_FIRST
    if idx >= len(ctx.cookies):
        return text_fn(ctx, token)
    kind, args, nowiki = ctx.cookies[idx]
    # print("MAGIC_FN:", kind, args, nowiki)
    ctx.beginning_of_line = False

    if kind == "T":
        if nowiki:
            process_text(
                ctx,
                "&lbrace;&lbrace;" + "&vert;".join(args) + "&rbrace;&rbrace;",
            )
            return
        # Template tranclusion or parser function call
        _parser_push(ctx, NodeKind.TEMPLATE)

        with ctx.begline_disabled:
            # Process arguments
            process_text(ctx, args[0])
            for arg in args[1:]:
                # prevent new lines in template arguments pop parser stack
                vbar_fn(ctx, "|")
                process_text(ctx, arg)

        while True:
            node = ctx.parser_stack[-1]
            if node.kind == NodeKind.ROOT:
                break
            if node.kind in (NodeKind.TEMPLATE, NodeKind.PARSER_FN):
                _parser_pop(ctx, False)
                break
            _parser_pop(ctx, True)

    elif kind == "A":
        if nowiki:
            process_text(
                ctx,
                "&lbrace;&lbrace;&lbrace;"
                + "&vert;".join(args)
                + "&rbrace;&rbrace;&rbrace;",
            )
            return
        # Template argument reference
        _parser_push(ctx, NodeKind.TEMPLATE_ARG)

        # Process arguments
        with ctx.begline_disabled:
            process_text(ctx, args[0])
            for arg in args[1:]:
                vbar_fn(ctx, "|")
                process_text(ctx, arg)

        while True:
            node = ctx.parser_stack[-1]
            if node.kind == NodeKind.ROOT:
                break
            if node.kind == NodeKind.TEMPLATE_ARG:
                _parser_pop(ctx, False)
                break
            _parser_pop(ctx, True)

    elif kind == "L":
        if nowiki:
            process_text(
                ctx, "&lsqb;&lsqb;" + "&vert;".join(args) + "&rsqb;&rsqb;"
            )
            return
        # Link to another page
        _parser_push(ctx, NodeKind.LINK)

        # Process arguments
        with ctx.begline_disabled:
            process_text(ctx, args[0])
            for arg in args[1:]:
                vbar_fn(ctx, "|")
                process_text(ctx, arg)

        while True:
            node = ctx.parser_stack[-1]
            if node.kind == NodeKind.ROOT:
                break
            if node.kind == NodeKind.LINK:
                _parser_pop(ctx, False)
                break
            _parser_pop(ctx, True)

    elif kind == "E":
        # Link to an external page (or just text in brackets, e.g. [...])
        if not nowiki and args and (":" in args[0] or args[0].startswith("//")):
            _parser_push(ctx, NodeKind.URL)

            # Process arguments
            with ctx.begline_disabled:
                process_text(ctx, args[0])
                for arg in args[1:]:
                    vbar_fn(ctx, "|")
                    process_text(ctx, arg)

            # The URL could have been popped if the content does not look like
            # a URL.
            if not _parser_have(ctx, NodeKind.URL):
                # It must have been popped.
                text_fn(ctx, "]")
            else:
                # Pop until we are back at this level and close the URL node
                while True:
                    node = ctx.parser_stack[-1]
                    if node.kind == NodeKind.ROOT:
                        break
                    if node.kind == NodeKind.URL:
                        _parser_pop(ctx, False)
                        break
                    _parser_pop(ctx, True)
        else:
            process_text(ctx, "[" + "&vert;".join(args) + "]")
    elif kind == "N":  # Nowiki
        # Replace nowiki by the escaped versions here
        text = nowiki_quote(args[0])
        text_fn(ctx, text)
    else:
        ctx.error(
            "magic_fn: unsupported cookie kind {!r}".format(kind),
            sortid="parser/780",
        )


def colon_fn(ctx: "Wtp", token: str) -> None:
    """Handler for a special colon ":" within a template call.  This indicates
    that it is actually a parser function call.  This is called from list_fn()
    when it detects that it is inside a template node."""
    node = ctx.parser_stack[-1]

    # Unless we are in the first argument of a template, treat a colon that is
    # not at the beginning of a
    if node.kind != NodeKind.TEMPLATE or node.largs:
        return text_fn(ctx, token)

    # Merge string children.  This is needed for both the following text and
    # for args.
    _parser_merge_str_children(ctx)

    # Check if the template argument is a parser function name.
    if (
        len(node.children) != 1
        or not isinstance(node.children[0], str)
        or node.children[0] not in PARSER_FUNCTIONS
    ):
        return text_fn(ctx, token)

    # Colon in the first argument of {{name:...}} turns it into a parser
    # function call.
    node.kind = NodeKind.PARSER_FN
    node.largs.append(node.children)
    node.children = []


def mistokenized_start_fn(ctx: "Wtp", token: str) -> None:
    """Handler for table start token or text + double pipe toke."""
    if ctx.pre_parse:
        return text_fn(ctx, token)

    if not (ctx.beginning_of_line or ctx.wsp_beginning_of_line):
        text_fn(ctx, "{")
        return double_vbar_fn(ctx, "||")

    table_start_fn(ctx, "{|")
    return vbar_fn(ctx, "|")


def table_start_fn(ctx: "Wtp", token: str) -> None:
    """Handler for table start token "{|"."""
    if ctx.pre_parse:
        return text_fn(ctx, token)

    if not (ctx.beginning_of_line or ctx.wsp_beginning_of_line):
        text_fn(ctx, "{")
        return vbar_fn(ctx, "|")

    close_begline_lists(ctx)
    _parser_push(ctx, NodeKind.TABLE)


# kludge to fix intertwined templates
# [' class="translations" (...)
# data-gloss="butterfly ', <ITALIC(){} 'Lasiommata megera'>, '"\n']
#                          ^^^- this shouldn't be here -^^^
# XXX this kludge is only needed because the interleaved
# trans-top and multi-trans templates break the parser somewhere
# else.

# something=other, something="other", something = 'other'
attr_assignment_pair = (
    r"""\s*[^"'>/=\0-\037\s]+""" r"""\s*=\s*("[^"]*"|'[^']*'|[^"'<>`\s]+)"""
)

attr_assignments_re = re.compile(
    attr_assignment_pair + r"""(""" + attr_assignment_pair + r""")*\s*$"""
)  # to account for spaces between entities


def check_for_attributes(ctx: "Wtp", node: WikiNode) -> tuple[bool, str]:
    """Check if the children of this node conform to the format of
    attribute assignment in tables"""

    # Old behavior added here to return earlier without needing
    # to use regex matching; if the old version worked, why not?
    # If this fail, then resort to the reverse parsing + regex.
    _parser_merge_str_children(ctx)
    if len(node.children) == 1 and isinstance(node.children[0], str):
        ret = node.children.pop()
        if TYPE_CHECKING:
            assert isinstance(ret, str)
        return (True, ret)

    candidate = ""
    for child in node.children:
        if isinstance(child, str):
            candidate += child
        else:
            candidate += html.escape(ctx.node_to_wikitext(child))
    if not candidate.strip():
        return (True, "")  # No idea why this has to be like this
        # Later on: I figured it out, the original behavior was to
        # pass on empty lines (with a newline), which took them out
        # of the normal 'parsing loop' and discarded the data,
        # because attribute string data is discarded after it is parsed.
        # So when you *don't* feed the empty string to the attribute
        # parsing function and empty node.children, you're leaving
        # 'alive' a newline that used to be killed. This is why the
        # tests failed because of 'extra' newlines.
    if re.match(attr_assignments_re, candidate):
        return (True, candidate)
    return (False, "")


def table_check_attrs(ctx: "Wtp") -> None:
    """Checks if the table has attributes, and if so, parses them."""
    node = ctx.parser_stack[-1]
    if node.kind != NodeKind.TABLE:
        return

    if len(node.children) < 1:
        return

    check, attribute_string = check_for_attributes(ctx, node)
    if not check:
        return
    node.children = []
    parse_attrs(node, attribute_string)


def table_row_check_attrs(ctx: "Wtp") -> None:
    """Checks if the table row has attributes, and if so, parses them."""
    close_begline_lists(ctx)
    node = ctx.parser_stack[-1]
    if node.kind != NodeKind.TABLE_ROW:
        return

    if len(node.children) < 1:
        return

    check, attribute_string = check_for_attributes(ctx, node)
    if not check:
        return
    node.children = []
    parse_attrs(node, attribute_string)


def table_caption_fn(ctx: "Wtp", token: str) -> None:
    """Handler for table caption token "|+"."""
    if ctx.pre_parse:
        return text_fn(ctx, token)

    if not (ctx.beginning_of_line or ctx.wsp_beginning_of_line):
        vbar_fn(ctx, "|")
        return text_fn(ctx, "+")

    close_begline_lists(ctx)
    table_check_attrs(ctx)
    if not _parser_have(ctx, NodeKind.TABLE):
        return text_fn(ctx, token)
    while True:
        node = ctx.parser_stack[-1]
        if node.kind == NodeKind.TABLE:
            break
        _parser_pop(ctx, True)
    _parser_push(ctx, NodeKind.TABLE_CAPTION)


def table_hdr_cell_fn(ctx: "Wtp", token: str) -> None:
    """Handler function for table header row cell separator ! or !!."""
    if ctx.pre_parse:
        return text_fn(ctx, token)

    close_begline_lists(ctx)
    table_row_check_attrs(ctx)
    table_check_attrs(ctx)

    # Outside tables, just interpret ! and !! as raw text
    if not _parser_have(ctx, NodeKind.TABLE):
        return text_fn(ctx, token)

    if token == "!" and (
        not (ctx.beginning_of_line or ctx.wsp_beginning_of_line)
    ):
        return text_fn(ctx, token)

    while True:
        node = ctx.parser_stack[-1]
        if node.kind == NodeKind.TABLE_ROW:
            _parser_push(ctx, NodeKind.TABLE_HEADER_CELL)
            return
        if node.kind == NodeKind.TABLE:
            _parser_push(ctx, NodeKind.TABLE_ROW)
            _parser_push(ctx, NodeKind.TABLE_HEADER_CELL)
            return
        if node.kind == NodeKind.TABLE_CAPTION:
            if ctx.beginning_of_line and ctx.begline_enabled:
                _parser_pop(ctx, False)
                _parser_push(ctx, NodeKind.TABLE_ROW)
                _parser_push(ctx, NodeKind.TABLE_HEADER_CELL)
            else:
                text_fn(ctx, token)
            return
        if node.kind in (
            NodeKind.HTML,
            NodeKind.TEMPLATE,
            NodeKind.LINK,
            NodeKind.URL,
        ):
            # Inside nested HTML, interpret ! and !! as normal text
            return text_fn(ctx, token)
        if (
            node.kind == NodeKind.TABLE_CELL
            and not (ctx.beginning_of_line and ctx.begline_enabled)
            and not ctx.wsp_beginning_of_line
        ):
            # Inside a cell, ! and !! are normal text unless at the beginning
            # of a line
            return text_fn(ctx, token)
        _parser_pop(ctx, True)


def table_row_fn(ctx: "Wtp", token: str) -> None:
    """Handler function for table row separator "|-"."""
    if ctx.pre_parse:
        return text_fn(ctx, token)

    if not (ctx.beginning_of_line or ctx.wsp_beginning_of_line):
        vbar_fn(ctx, "|")
        return text_fn(ctx, "-")

    close_begline_lists(ctx)
    table_check_attrs(ctx)
    if not _parser_have(ctx, NodeKind.TABLE):
        return text_fn(ctx, token)
    while True:
        node = ctx.parser_stack[-1]
        if node.kind == NodeKind.TABLE:
            break
        _parser_pop(ctx, True)
    _parser_push(ctx, NodeKind.TABLE_ROW)


def table_cell_fn(ctx: "Wtp", token: str) -> None:
    """Handler function for table row cell separator | or ||."""
    if ctx.pre_parse:
        return text_fn(ctx, token)

    close_begline_lists(ctx)
    table_row_check_attrs(ctx)
    table_check_attrs(ctx)

    if not _parser_have(ctx, NodeKind.TABLE):
        return text_fn(ctx, token)

    if (
        token == "|"
        and not ctx.wsp_beginning_of_line
        and not (ctx.beginning_of_line and ctx.begline_enabled)
    ):
        # This might separate attributes for captions, header cells, and
        # data cells
        _parser_merge_str_children(ctx)
        node = ctx.parser_stack[-1]
        if (
            not node.attrs
            and len(node.children) == 1
            and isinstance(attrs := node.children[0], str)
        ):
            if node.kind in (
                NodeKind.TABLE_CAPTION,
                NodeKind.TABLE_HEADER_CELL,
                NodeKind.TABLE_CELL,
            ):
                node.children.pop()
                # Using the walrus operator and pop()ing without return
                # is just to make the type-checker happy without using
                # an assert that attrs is definitely a str...
                parse_attrs(node, attrs)
                return
        return text_fn(ctx, token)

    while True:
        node = ctx.parser_stack[-1]
        if node.kind == NodeKind.TABLE_ROW:
            break
        if node.kind == NodeKind.TABLE:
            _parser_push(ctx, NodeKind.TABLE_ROW)
            break
        if node.kind == NodeKind.TABLE_CAPTION:
            return text_fn(ctx, token)
        if node.kind == NodeKind.HTML:
            # Inside nested HTML, treat | and || as normal text
            return text_fn(ctx, token)
        _parser_pop(ctx, True)
    _parser_push(ctx, NodeKind.TABLE_CELL)


def vbar_fn(ctx: "Wtp", token: str) -> None:
    """Handler function for vertical bar |.  The interpretation of
    the vertical bar depends on context; it can separate arguments to
    templates, template argument references, links, etc, and it can
    also separate table row cells."""
    node = ctx.parser_stack[-1]
    if node.kind in HAVE_ARGS_KIND_FLAGS and node.kind is not NodeKind.URL:
        # [http://url.com these do not use vbars, only one initial space]
        _parser_merge_str_children(ctx)
        node.largs.append(node.children)
        node.children = []
        return
    elif _parser_have(ctx, NodeKind.TABLE):
        table_cell_fn(ctx, token)
    elif _parser_have(ctx, HAVE_ARGS_KIND_FLAGS):
        _parser_pop(ctx, True)
        vbar_fn(ctx, token)
    else:
        text_fn(ctx, token)


def double_vbar_fn(ctx: "Wtp", token: str) -> None:
    """Handle function for double vertical bar ||.  This is used as a
    column separator in tables.  At the beginning of a line it starts
    a new column.  If it occurs in other contexts, it should be
    interpreted as two vertical bars.  It appears that on lines that
    contain header cells this actually generates a new header cell in
    MediaWiki, so we'll do the same."""
    node = ctx.parser_stack[-1]
    if node.kind in HAVE_ARGS_KIND_FLAGS:
        vbar_fn(ctx, "|")
        vbar_fn(ctx, "|")
        return

    # If it is at the beginning of a line, interpret it as starting a new
    # cell, without any HTML attributes.  We do this by emitting two individual
    # vbars.
    if ctx.beginning_of_line and ctx.begline_enabled:
        vbar_fn(ctx, "|")
        vbar_fn(ctx, "|")
        return

    while True:
        node = ctx.parser_stack[-1]
        if node.kind == NodeKind.TABLE_ROW:
            break
        if node.kind == NodeKind.TABLE:
            _parser_push(ctx, NodeKind.TABLE_ROW)
            break
        if node.kind == NodeKind.TABLE_CAPTION:
            return text_fn(ctx, token)
        if node.kind == NodeKind.HTML:
            # Inside nested HTML, treat as normal text
            return text_fn(ctx, token)
        if node.kind in (NodeKind.TABLE_CELL, NodeKind.TABLE_HEADER_CELL):
            _parser_pop(ctx, True)
            continue
        break

    if (
        node.kind == NodeKind.TABLE_ROW
        and len(node.children) > 0
        and isinstance(node.children[-1], WikiNode)
        and node.children[-1].kind == NodeKind.TABLE_HEADER_CELL
    ):
        table_hdr_cell_fn(ctx, token)
    else:
        table_cell_fn(ctx, token)


def table_end_fn(ctx: "Wtp", token: str) -> None:
    """Handler function for end of a table token "|}"."""
    if ctx.pre_parse:
        return text_fn(ctx, token)

    if not (ctx.beginning_of_line or ctx.wsp_beginning_of_line):
        vbar_fn(ctx, "|")
        return text_fn(ctx, "}")

    close_begline_lists(ctx)
    table_row_check_attrs(ctx)
    table_check_attrs(ctx)
    if not _parser_have(ctx, NodeKind.TABLE):
        return text_fn(ctx, token)
    while True:
        node = ctx.parser_stack[-1]
        if node.kind == NodeKind.TABLE:
            _parser_pop(ctx, False)
            break
        _parser_pop(ctx, True)


def list_fn(ctx: "Wtp", token: str) -> None:
    """Handles various tokens that start unordered or ordered list items,
    description list items, or indented lines.  This also recognizes the
    colon used to separate parser function name from its first argument."""
    if ctx.pre_parse:
        return text_fn(ctx, token)

    node = ctx.parser_stack[-1]

    # A colon inside a template means it is a parser function call.  We use
    # colon_fn() to handle that kind of colon.
    if token == ":" and node.kind == NodeKind.TEMPLATE:
        colon_fn(ctx, token)
        return

    # Colons can occur inside links and don't mean a list item
    if node.kind in (NodeKind.LINK, NodeKind.URL):
        return text_fn(ctx, token)

    # List items must start a new line; otherwise treat as text.  This is
    # particularly the case for colon, which is recognized as a token also
    # in the middle of a line.  Some of these cases were handled above; some
    # are handled here.
    if not (ctx.beginning_of_line and ctx.begline_enabled):
        node = ctx.parser_stack[-1]
        if (
            token == ":"
            and node.kind == NodeKind.LIST_ITEM
            and node.sarg.endswith(";")
            and node.temp_head is None
        ):
            # Got definition for a head in a definition list on the same line
            #   "; term : definition"
            # Shuffle node.temp_head and children (they will be unshuffled
            # in _parser_pop()) and do not change the stack otherwise
            _parser_merge_str_children(ctx)
            node.temp_head = node.children
            node.children = []
            return
        # Otherwise treat colons that do not start a line as normal text
        return text_fn(ctx, token)

    # Pop any lower-level list items
    while True:
        node = ctx.parser_stack[-1]

        # Check for a definition in a definition list
        if (
            node.kind == NodeKind.LIST_ITEM
            and node.sarg.endswith(";")
            and token.endswith(":")
            and token[:-1] == node.sarg[:-1]
            and node.temp_head is None
        ):
            # Got definition for a definition list item, on a separate line.
            # Shuffle node.temp_head and children (they will be unshuffled in
            # _parser_pop()) and do not change the stack otherwise
            _parser_merge_str_children(ctx)
            node.temp_head = node.children
            node.children = []
            return

        # Check for continuing an earlier list item, possibly after an
        # intervening sublist
        if (
            node.kind == NodeKind.LIST_ITEM
            and token.endswith(":")
            and node.sarg == token[:-1]
            and node.children
            and isinstance(node.children[-1], WikiNode)
        ):
            # Suffixing a list item prefix with a colon can be used to continue
            # the same item after an intervening sublist.
            # Previously we would return here, but the behavior has been changed
            # so that a new list and list item will be created instead of
            # appending things at the end of the parent node.
            break

        # Check for another list item on the same level (adding a new
        # list item to an earlier list)
        if node.kind == NodeKind.LIST_ITEM and node.sarg == token:
            _parser_pop(ctx, False)
            break

        # Check for adding an item to the same list.  If the list has a
        # different prefix, we will close it and either add to a parent list
        # or start a new list.  Note that definition list definitions were
        # already handled above so we won't be seeing them here.
        if node.kind == NodeKind.LIST_ITEM and len(node.sarg) < len(token):
            for i in range(len(node.sarg)):
                if token[i] not in (":", node.sarg[i]):
                    break  # Tokens do not match
            else:
                # Tokens match (with non-last : matching * or #)
                # Create a sublist
                break

        # Stop popping if we are at a header.  Headers cannot be used inside
        # list items.  In this case we always start a new list.
        if node.kind in KIND_TO_LEVEL:
            break  # Always break before section header

        # There are various kinds of nodes that can contain lists.  We won't
        # pop them.
        if node.kind in (
            NodeKind.HTML,
            NodeKind.TEMPLATE,
            NodeKind.TEMPLATE_ARG,
            NodeKind.PARSER_FN,
            NodeKind.TABLE,
            NodeKind.TABLE_HEADER_CELL,
            NodeKind.TABLE_ROW,
            NodeKind.TABLE_CELL,
        ):
            break

        # Otherwise pop the current node, possibly causing an error message.
        # For example, italics or bold must be contained in a single list item.
        _parser_pop(ctx, True)

    pop_until_nth_list(ctx, token)
    # If not already in a list, create a new list.
    node = ctx.parser_stack[-1]
    if node.kind != NodeKind.LIST:
        node = _parser_push(ctx, NodeKind.LIST)
        node.sarg = token

    # Add a new list item to the list.
    node = _parser_push(ctx, NodeKind.LIST_ITEM)
    node.sarg = token


def parse_attrs(node: WikiNode, attrs: str) -> None:
    # XXX this could be a WikiNode method?
    """Parses HTML tag attributes from ``attrs`` and adds them to
    ``node.attrs``."""
    assert isinstance(node, WikiNode)
    assert isinstance(attrs, str)

    # Extract attributes from the tag into the node.attrs dictionary
    for m in re.finditer(
        r"""(?si)\b([^"'>/=\0-\037\s]+)"""
        r"""(?:\s*=\s*("[^"]*"|'[^']*'|[^"'<>`\s]*))?\s*""",
        attrs,
    ):
        name = m.group(1)
        value = m.group(2) or ""
        if value.startswith("'") or value.startswith('"'):
            value = value[1:-1]
        node.attrs[name] = value


def tag_fn(ctx: "Wtp", token: str) -> None:
    """Handler function for tokens that look like HTML tags and their end
    tags.  This includes various built-in tags that aren't actually
    HTML.  Some WikiText tags that resemble HTML are described as HTML
    nodes, even though they are not really HTML."""

    # Note: <nowiki> and HTML comments have already been handled in
    # preprocessing

    # There are strings like <<country>> in some template arguments
    if (
        token.startswith("<<")
        or _parser_have(ctx, NodeKind.TEMPLATE)
        or _parser_have(ctx, NodeKind.TEMPLATE_ARG)
        or _parser_have(ctx, NodeKind.PARSER_FN)
    ):
        return text_fn(ctx, token)

    # If we are at the beginning of a line, close pending list,
    # UNLESS we are closing a tag (</tag>) in which case if the
    # element being closed is inside the newest link item,
    # just continue the link item and allow newlines inside
    # between the tags... XXX Double+ newlines break this still.
    # """
    # # Example <ref> the text...
    # </ref> here is still part of the above list item, unexpectedly...
    # """
    end_tag_name = None
    if token.startswith("</"):
        # See if this looks like an end-tag
        m = re.match(r"</([-a-zA-Z0-9]+)\s*>", token)
        if m is None:
            close_begline_lists(ctx)
        else:
            # end_tag_name is also saved for later, reusing the regex output
            end_tag_name = m.group(1)
            end_tag_name = end_tag_name.lower()
            # See if we can find the opening tag from the stack
            # or if we bump into a LIST_ITEM first, going from newest to oldest
            for i in reversed(range(0, len(ctx.parser_stack))):
                node = ctx.parser_stack[i]
                if node.kind == NodeKind.HTML and node.sarg == end_tag_name:
                    break  # do not close_begline_lists
                if node.kind == NodeKind.LIST_ITEM:
                    close_begline_lists(ctx)
                    break
    else:
        close_begline_lists(ctx)

    # Try to parse it as a start tag
    m = re.match(
        r"""<([-a-zA-Z0-9]+)\s*((\b[-a-zA-Z0-9:]+(\s*=\s*("[^"]*"|"""
        r"""'[^']*'|[^ \t\n"'`=<>]*))?\s*)*)/?>""",
        token,
    )
    if m is not None:
        # This is a start tag
        name = m.group(1).lower()
        attrs = m.group(2)
        also_end = m.group(0).endswith("/>")

        # Some templates have markers like <1> in their arguments.  Only parse
        # valid HTML tags in template arguments (tags like <math> can and
        # do occur in them).
        if (
            name not in ctx.allowed_html_tags
            and _parser_have(ctx, NodeKind.TEMPLATE)
            or _parser_have(ctx, NodeKind.TEMPLATE_ARG)
        ):
            return text_fn(ctx, token)

        # If preparsing, only handle template control tags like <noinclude>
        if ctx.pre_parse:
            return text_fn(ctx, token)

        # If the tag is <section ...>, ignore it
        if name == "section":
            return

        # Check for unmatched <nowiki> start tag.  <nowiki> should be handled
        # in preprocessing, but an unmatched start tag may be missed.
        if name == "nowiki":
            if also_end:
                text_fn(ctx, MAGIC_NOWIKI_CHAR)
                return
            ctx.debug("unmatched <nowiki>", sortid="parser/1227")
            return text_fn(ctx, token)

        # Ignore <noinclude/> tags.  They are sometimes used to prevent
        # parsing of wikitext constructions in the normal way.  Here we
        # throw them away; they should already have done their job.
        if name == "noinclude" and also_end:
            # print("IGNORING NOINCLUDE/")
            return

        # Handle <pre> start tag
        if name == "pre":
            node = _parser_push(ctx, NodeKind.PRE)
            parse_attrs(node, attrs)
            if also_end:
                _parser_pop(ctx, False)
            else:
                ctx.pre_parse = True
            return

        # Give a warning on unsupported HTML tags.  WikiText limits the set of
        # tags that are allowed.
        if name not in ctx.allowed_html_tags:
            if not name.isdigit() and not SILENT_HTML_LIKE:
                ctx.debug(
                    "html tag <{}{}> not allowed in WikiText".format(
                        name, "/" if also_end else ""
                    ),
                    sortid="parser/1251",
                )
            text_fn(ctx, token)
            return

        # Automatically close parent HTML tags that should be ended by this tag
        # until we have a parent that is not a HTML tag or that is an allowed
        # parent for this node
        permitted_parents = ctx.html_permitted_parents.get(name, set())
        while True:
            node = ctx.parser_stack[-1]
            if node.kind == NodeKind.URL and not node.children:
                ctx.parser_stack.pop()
                ctx.parser_stack[-1].children.pop()
                text_fn(ctx, "[")
                continue
            if node.kind != NodeKind.HTML:
                break
            if node.sarg in permitted_parents:
                break
            close_next = ctx.allowed_html_tags.get(node.sarg, {}).get(
                "close-next", []
            )
            # Warn about unclosed tag unless it is one we close automatically
            _parser_pop(ctx, name not in close_next)

        # Handle other start tag.  We push HTML tags as HTML nodes.
        node = _parser_push(ctx, NodeKind.HTML)
        node.sarg = name
        parse_attrs(node, attrs)

        # If the tag contains a trailing slash or it is an empty tag,
        # close it immediately.
        no_end_tag = ctx.allowed_html_tags.get(name, {}).get("no-end-tag")
        if no_end_tag or also_end:
            _parser_pop(ctx, False)
        return

    # Since it was not a start tag, it should be an end tag
    if end_tag_name:
        # Duplicated code from above
        name = end_tag_name
    else:
        m = re.match(r"</([-a-zA-Z0-9]+)\s*>", token)
        if m is None:
            raise Exception("Could not match end tag token: {!r}".format(token))
        name = m.group(1)
        name = name.lower()

    # We should never see </section>
    if name == "section":
        ctx.debug("unexpected </section>", sortid="parser/1299")
        return

    # Check for </pre> end tag
    if name == "pre":
        # Handle </pre> end tag
        ctx.pre_parse = False
        node = ctx.parser_stack[-1]
        if node.kind != NodeKind.PRE:
            ctx.debug("unexpected </pre>", sortid="parser/1308")
            return text_fn(ctx, token)
        _parser_pop(ctx, False)
        return

    # If preparsing, treat this as plain text
    if ctx.pre_parse:
        return text_fn(ctx, token)

    # Give a warning on unsupported HTML tags.  WikiText limits the set of
    # tags that are allowed.
    if name not in ctx.allowed_html_tags and name != "nowiki":
        ctx.debug(
            "html tag </{}> not allowed in WikiText".format(name),
            sortid="parser/1320",
        )

    # See if we can find the opening tag from the stack
    for i in reversed(range(0, len(ctx.parser_stack))):
        node = ctx.parser_stack[i]
        if node.kind == NodeKind.HTML and node.sarg == name:
            break
    else:
        # No corresponding start tag found
        if name in ("br", "hl", "wbr"):
            # This is incorrect but occurs; synthesize empty tag
            node = _parser_push(ctx, NodeKind.HTML)
            node.sarg = name
            _parser_pop(ctx, False)
            return
        ctx.debug(
            "no corresponding start tag found for {}".format(token),
            sortid="parser/1336",
        )
        text_fn(ctx, token)
        return

    # Close nodes until we close the corresponding start tag
    while True:
        node = ctx.parser_stack[-1]
        if node.kind == NodeKind.URL and not node.children:
            ctx.parser_stack.pop()
            ctx.parser_stack[-1].children.pop()
            text_fn(ctx, "[")
            continue
        if node.kind == NodeKind.HTML and node.sarg == name:
            # Found the corresponding start tag.  Close this node and
            # then stop.
            _parser_pop(ctx, False)
            break
        if node.kind == NodeKind.HTML:
            # If close-next is set, then end tag is optional and can be closed
            # implicitly by closing the parent tag
            close_next2 = ctx.allowed_html_tags.get(node.sarg, {}).get(
                "close-next", None
            )
            if close_next2:
                _parser_pop(ctx, False)
                continue
        _parser_pop(ctx, True)


def magicword_fn(ctx: "Wtp", token: str) -> None:
    """Handles a magic word, such as "__NOTOC__"."""
    close_begline_lists(ctx)
    node = _parser_push(ctx, NodeKind.MAGIC_WORD)
    node.sarg = token
    _parser_pop(ctx, False)


# Headers need to be detected before be partition lines with ''-tokens
header_re = re.compile(r"(?m)^(={1,6})\s*(([^=]|=[^=])+?)\s*(={1,6})\s*$")

token_list: list[str] = [
    r"'''''",
    r"'''",
    r"''",
    r"\n",
    r"\|\}",
    r"\{\|\|",
    r"\{\|",
    r"\|\+",
    r"\|-",
    r"!!",
    r"\s*https?://[a-zA-Z0-9.]+(/[^][{}<>|\s]*)?",
    r"^[ \t]*!",
    r"\|\|",
    r"\|",
    r"^----+",
    r"^[*:;#]+",
    r"[ \t]+\n*",
    r":",  # sometimes special when not beginning of line
    r"<<[-a-zA-Z0-9/]*>>",
    r"""<[-a-zA-Z0-9]+\s*(\b[-a-zA-Z0-9:]+(\s*=\s*("[^<>"]*"|"""  # HTML start
    r"""'[^<>']*'|[^ \t\n"'`=<>]*))?\s*)*/?>""",  # HTML start tag
    r"</[-a-zA-Z0-9]+\s*>",
    r"(" + r"|".join(r"\b{}\b".format(x) for x in MAGIC_WORDS) + r")",
    r"[{:c}-{:c}]".format(MAGIC_FIRST, MAGIC_LAST),
]
# Regular expressions for matching a token in WikiMedia text.  This is used for
# tokenizing the input.
# Because we partition each line on italics and bold tokens (''' etc)
# the regex cannot distinguish if a token is at the beginning of a line
# or just the beginning of a partitioned string. The most performant thing
# seems to be to have two versions of the regex, one used at the beginning
# of a line (after a newline) and another in other parts of a line; this
# only costs switching between the two regex patterns inside the for loop.
TOKEN_RE_BEGINNING_OF_LINE = re.compile(r"|".join(token_list))
TOKEN_RE_NO_CARET = re.compile(
    r"|".join(x for x in token_list if not x.startswith(r"^"))
)


# Matches a </pre> end token
pre_end_re = re.compile(r"(?i)</pre\s*>")

# Matches a list item prefix
list_prefix_re = re.compile(r"[*:;#]+")

# Dictionary mapping fixed form tokens to their handler functions.
# Tokens that have variable form are handled in the code in token_iter().
tokenops: dict[str, Callable[["Wtp", str], None]] = {
    "'''": bold_fn,
    "''": italic_fn,
    "{|": table_start_fn,
    "{||": mistokenized_start_fn,
    "|}": table_end_fn,
    "|+": table_caption_fn,
    "!": table_hdr_cell_fn,
    "!!": table_hdr_cell_fn,
    "|-": table_row_fn,
    "||": double_vbar_fn,
    "|": vbar_fn,
    # The following are here only because it speeds up operations over handling
    # them in the general way (by about 10% in overall parsing speed)
    " ": text_fn,
    "\n": text_fn,
    "\t": text_fn,
    "\n\n": text_fn,
}
for x in MAGIC_WORDS:
    tokenops[x] = magicword_fn


def bold_follows(parts: list[str], i: int) -> bool:
    """Checks if there is a bold (''') in parts after parts[i].  We allow
    intervening italics ('')."""
    parts = parts[i + 1 :]
    for p in parts:
        if not p.startswith("''"):
            continue
        if p.startswith("'''"):
            return True
    return False


def token_iter(ctx: "Wtp", text: str) -> Iterator[tuple[bool, str]]:
    """Tokenizes MediaWiki page content.  This yields (is_token, text) for
    each token.  ``is_token`` is False for text and True for other tokens.
    Wikitext bold and italic are interpreted WITHIN A SINGLE LINE.  It seems
    impossible to always disambiguate them without looking at what follows
    on the same line."""
    assert isinstance(text, str)
    # print(f"token_iter: {text=}")
    # Replace single quotes inside HTML tags with MAGIC_SQUOTE_CHAR
    tag_parts = ctx.inside_html_tags_re.split(text)
    if len(tag_parts) > 1:
        new_parts: list[str] = []
        for tp in tag_parts:
            if ctx.inside_html_tags_re.match(tp):
                # we're inside an HTML tag
                tp = tp.replace("'", MAGIC_SQUOTE_CHAR)
                tp = tp.replace("\n", "")
            new_parts.append(tp)
        text = "".join(new_parts)

    lines = re.split(r"(\n+)", text)  # Lines and separators
    parts_re = re.compile(r"('{2,})")
    for line in lines:
        if not line.strip(" \t"):
            continue
        # Detected headers before partitioning on "''"s
        hm = header_re.match(line)
        if hm:
            token = hm.group(0)
            if token.startswith("="):
                # Wikimedia parses heading tokens from inside out:
                # == Foo = is parsed as  =, "= Foo ", =, with leftover
                # `=` characters in-between the bookends ending up in the
                # the heading itself. Fixes issue #352.
                start, mid, _, end = hm.groups()
                if len(start) < len(end):
                    ctx.debug(
                        f"Heading `{start}`, `{mid}`, `{end}` "
                        f"has a start token shorter than end token: "
                        f"shorten end and append ='s to title",
                        sortid="parser20241218-2219",
                    )
                    mid += end[len(start) :]
                elif len(start) > len(end):
                    ctx.debug(
                        f"Heading `{start}`, `{mid}`, `{end}` "
                        f"has an end token shorter than start token: "
                        f"shorten start and prepend ='s to title",
                        sortid="parser20241218-2219",
                    )
                    mid = start[len(end) :] + mid
                    start = start[: len(end)]
                yield True, "<" + start
                # Tokenize header contents
                for x in token_iter(ctx, mid):
                    yield x
                # The two heading tokens returned here should be identical,
                # so we use `start` for both, which has been modified if
                # the length is longer than the end token was.
                yield True, ">" + start
            continue
        # Partition on '', so that we can detect bold/italics
        parts = re.split(parts_re, line)
        state = 0  # 1=in italic 2=in bold 3=in both
        for i, part in enumerate(parts):
            if part.startswith("''"):
                # This is a bold/italic part.  Scan the rest of the line
                # to determine how it should be interpreted if there are
                # more than two apostrophes.
                if part.startswith("'''''"):
                    if state == 1:  # in italic
                        yield True, "''"
                        yield True, "'''"
                        part = part[5:]
                        state = 2
                    elif state == 2:  # in bold
                        yield True, "'''"
                        yield True, "''"
                        part = part[5:]
                        state = 1
                    elif state == 3:  # in both
                        yield True, "'''"
                        yield True, "''"
                        state = 0
                        part = part[5:]
                    else:  # in nothing
                        if bold_follows(parts, i):
                            yield True, "''"
                            yield True, "'''"
                        else:
                            yield True, "'''"
                            yield True, "''"
                        part = part[5:]
                        state = 3
                elif part.startswith("'''"):
                    if state == 1:  # in italic
                        if bold_follows(parts, i):
                            yield True, "'''"
                            part = part[3:]
                            state = 3
                        else:
                            yield True, "''"
                            part = part[2:]
                            state = 0
                    elif state == 2:  # in bold
                        yield True, "'''"
                        part = part[3:]
                        state = 0
                    elif state == 3:  # in both
                        yield True, "'''"
                        part = part[3:]
                        state = 1
                    else:  # in nothing
                        yield True, "'''"
                        part = part[3:]
                        state = 2
                elif part.startswith("''"):
                    if state == 1:  # in italic
                        yield True, "''"
                        part = part[2:]
                        state = 0
                    elif state == 2:  # in bold
                        yield True, "''"
                        part = part[2:]
                        state = 3
                    elif state == 3:  # in both
                        yield True, "''"
                        part = part[2:]
                        state = 2
                    else:  # in nothing
                        yield True, "''"
                        part = part[2:]
                        state = 1
                if part:
                    # Shouldn't contain MAGIC_SQUOTE_CHAR
                    yield False, part
                continue
            # All other parts handled with normal tokenization
            pos = 0
            # Revert to single quotes from MAGIC_SQUOTE_CHAR
            part = part.replace(MAGIC_SQUOTE_CHAR, "'")
            # print(f"{part=}")
            if i == 0:
                token_re = TOKEN_RE_BEGINNING_OF_LINE
            else:
                token_re = TOKEN_RE_NO_CARET
            for m in token_re.finditer(part):
                # print(f"{m=}")
                start = m.start()
                if pos != start:
                    yield False, part[pos:start]
                pos = m.end()
                token = m.group(0)
                if token.strip().startswith(("https://", "http://")):
                    if start > 0 and part[start - 1] == "=":
                        # treat URL in template argument as plain text
                        # otherwise it'll be converted to wikitext link: [url]
                        yield False, token.strip()
                    elif token.startswith(" "):
                        yield True, token[: token.find("http")]
                        yield True, token.strip()
                    else:
                        yield True, token
                else:
                    yield True, token
            if pos != len(part):
                yield False, part[pos:]


def process_text(ctx: "Wtp", text: str) -> None:
    """Tokenizes ``text`` and processes each token in sequence.  This can be
    called recursively (which we do to process tokens inside templates and
    certain other structures)."""
    # print("PARSER PROCESS_TEXT:", repr(text))
    for is_token, token in token_iter(ctx, text):
        # print(f"process_text: token_iter yielded: {is_token=}, {token=}")
        node = ctx.parser_stack[-1]
        if not is_token:
            # Process it as normal text.
            text_fn(ctx, token)
        elif node.kind == NodeKind.PRE and not re.match(pre_end_re, token):
            # Remove the artificially added prefix from subtitle tokens.
            # Then process the token as normal text as we are in a
            # non-interpreting context.
            if token.startswith("<=="):
                token = token[1:]
            elif token.startswith(">=="):
                token = token[1:]
            text_fn(ctx, token)
        else:
            # Process it as a token.  In some contexts some tokens may still
            # be interpreted as text.
            if token in tokenops:
                tokenops[token](ctx, token)
            elif token.startswith("<="):  # Note: < added by tokenizer
                subtitle_start_fn(ctx, token)
            elif token.startswith(">="):  # Note: > added by tokenizer
                subtitle_end_fn(ctx, token)
            elif token.startswith("<"):  # HTML tag like construct
                tag_fn(ctx, token)
            elif token.startswith("----") and ctx.beginning_of_line:
                hline_fn(ctx, token)
            elif re.match(list_prefix_re, token):
                list_fn(ctx, token)
            elif token.startswith("https://") or token.startswith("http://"):
                url_fn(ctx, token)
            elif (
                len(token) == 1
                and ord(token) >= MAGIC_FIRST
                and ord(token) <= MAGIC_LAST
            ):
                magic_fn(ctx, token)
            else:
                t2 = token.strip()
                if t2 in tokenops:
                    tokenops[t2](ctx, t2)
                else:
                    text_fn(ctx, token)
        ctx.linenum += token.count("\n")
        ctx.wsp_beginning_of_line = ctx.beginning_of_line and token.isspace()
        ctx.beginning_of_line = token[-1] == "\n"


def parse_encoded(ctx: "Wtp", text: str) -> WikiNode:
    """Parses the text, which should already have been encoded using magic
    characters (see Wtp._encode()).  Parses the encoded string and returns
    the parse tree."""
    assert ctx.title is not None  # ctx.start_page() must have been called
    node = WikiNode(NodeKind.ROOT, 0)
    node.largs = [[ctx.title]]
    ctx.beginning_of_line = True
    ctx.wsp_beginning_of_line = False
    ctx.linenum = 1
    ctx.pre_parse = False
    ctx.parser_stack = [node]
    ctx.suppress_special = False

    try:
        # Process all tokens from the input.
        process_text(ctx, text)
        # We are at the end of the text.  Keep popping stack until we only have
        # the root node left.  This is used to finalize processing any nodes
        # on the stack.
        while True:
            node = ctx.parser_stack[-1]
            if node.kind == NodeKind.ROOT:
                break
            _parser_pop(ctx, True)
        assert len(ctx.parser_stack) == 1
        # If the last children are strings, merge them to one string.
        _parser_merge_str_children(ctx)
        ret = ctx.parser_stack[0]
    finally:
        ctx.parser_stack = []
    return ret


@overload
def print_tree(
    tree: Union[str, WikiNode], indent: int, ret_value: Literal[True]
) -> str: ...


@overload
def print_tree(
    tree: Union[str, WikiNode],
    indent: int = ...,
    ret_value: Literal[False] = ...,
) -> None: ...


def print_tree(
    tree: Union[str, WikiNode], indent: int = 0, ret_value=False
) -> Optional[str]:
    """Prints the parse tree for debugging purposes.  This does not expand
    HTML entities; that should be done after processing templates."""
    assert isinstance(tree, (WikiNode, str))
    assert isinstance(indent, int)
    parts = []
    if isinstance(tree, str):
        parts.append("{}{}".format(" " * indent, repr(tree)))
        if ret_value:
            return "\n".join(parts)
        else:
            print("\n".join(parts))
    assert isinstance(tree, WikiNode)
    parts.append(
        "{}{} {}".format(
            " " * indent, tree.kind.name, tree.sarg if tree.sarg else tree.largs
        )
    )
    for k, v in tree.attrs.items():
        parts.append("{}    {}={}".format(" " * indent, k, v))
    for child in tree.children:
        parts.append(print_tree(child, indent + 2, ret_value=True))

    if ret_value:
        return "\n".join(parts)
    else:
        print("\n".join(parts))
        return None
