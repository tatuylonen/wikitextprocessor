# Helper functions for interfacing with the Lua sandbox for executing Lua
# macros in Wikitext (Wiktionary, Wikipedia, etc.)
#
# Copyright (c) Tatu Ylonen.  See file LICENSE and https://ylonen.org

import os
import re
import html
import traceback
import pkg_resources
import lupa
from lupa import LuaRuntime
from .parserfns import PARSER_FUNCTIONS, call_parser_function, tag_fn
from .languages import ALL_LANGUAGES

# List of search paths for Lua libraries.
builtin_lua_search_paths = [
    # [path, ignore_modules]
    [".", ["string", "debug"]],
    ["mediawiki-extensions-Scribunto/includes/engines/LuaCommon/lualib",
     []],
]

# Determine which directory our data files are in
lua_dir = pkg_resources.resource_filename("wikitextprocessor", "lua/")
#print("lua_dir", lua_dir)

# Set of known language codes.
# XXX remove this?
#KNOWN_LANGUAGE_TAGS = set(x["code"] for x in ALL_LANGUAGES
#                          if x.get("code") and x.get("name"))

# Mapping from language code code to language name.
LANGUAGE_CODE_TO_NAME = { x["code"]: x["name"]
                          for x in ALL_LANGUAGES
                          if x.get("code") and x.get("name") }

def lua_loader(ctx, modname):
    """This function is called from the Lua sandbox to load a Lua module.
    This will load it from either the user-defined modules on special
    pages or from a built-in module in the file system.  This returns None
    if the module could not be loaded."""
    assert isinstance(modname, str)
    # print("Loading", modname)
    modname = modname.strip()
    if modname.startswith("Module:"):
        modname = modname[7:]
    modname1 = ctx._canonicalize_template_name(modname)
    if modname1 in ctx.modules:
        return ctx.modules[modname1]
    path = modname
    path = re.sub(r":", "/", path)
    path = re.sub(r" ", "_", path)
    # path = re.sub(r"\.", "/", path)
    path = re.sub(r"//+", "/", path)
    path = re.sub(r"\.\.", ".", path)
    if path.startswith("/"):
        path = path[1:]
    path += ".lua"
    for prefix, exceptions in builtin_lua_search_paths:
        if modname in exceptions:
            continue
        p = lua_dir + "/" + prefix + "/" + path
        if os.path.isfile(p):
            with open(p, "r") as f:
                data = f.read()
            return data
    ctx.error("Lua module not found: NOT FOUND: {} at {}"
              .format(modname, ctx.expand_stack))
    return None


def mw_text_decode(text, decodeNamedEntities=False):
    """Implements the mw.text.decode function for Lua code."""
    if decodeNamedEntities:
        return html.unescape(text)

    # Otherwise decode only selected entities
    parts = []
    pos = 0
    for m in re.finditer(r"&(lt|gt|amp|quot|nbsp);", text):
        if pos < m.start():
            parts.append(text[pos:m.start()])
        pos = m.end()
        tag = m.group(1)
        if tag == "lt":
            parts.append("<")
        elif tag == "gt":
            parts.append(">")
        elif tag == "amp":
            parts.append("&")
        elif tag == "quot":
            parts.append('"')
        elif tag == "nbsp":
            parts.append("\xa0")
        else:
            assert False
    parts.append(text[pos:])
    return "".join(parts)

def mw_text_encode(text, charset='<>&\xa0"'):
    """Implements the mw.text.encode function for Lua code."""
    parts = []
    for ch in str(text):
        if ch in charset:
            chn = ord(ch)
            if chn in html.entities.codepoint2name:
                parts.append("&" + html.entities.codepoint2name.get(chn) + ";")
            else:
                parts.append(ch)
        else:
            parts.append(ch)
    return "".join(parts)


def get_page_info(ctx, title):
    """Retrieves information about a page identified by its table (with
    namespace prefix.  This returns a lua table with fields "id", "exists",
    and "redirectTo".  This is used for retrieving information about page
    titles."""
    assert isinstance(title, str)

    # XXX actually look at information collected in phase 1 to determine
    page_id = 0  # XXX collect required info in phase 1
    page_exists = False  # XXX collect required info in Phase 1
    redirect_to = ctx.redirects.get(title, None)

    # whether the page exists and what its id might be
    dt = {
        "id": page_id,
        "exists": page_exists,
        "redirectTo": redirect_to,
    }
    return ctx.lua.table_from(dt)


def get_page_content(ctx, title):
    """Retrieves the full content of the page identified by the title.
    Currently this will only return content for the current page.
    This returns None if the page is other than the current page, and
    False if the page does not exist (currently not implemented)."""
    assert isinstance(title, str)
    title = title.strip()

    # Read the page by its title
    data = ctx.read_by_title(title)
    if data is None:
        ctx.warning("attempted to access page content for {!r} which "
                    "is not available"
                    .format(title))
        return ""
    return data

def fetch_language_name(code):
    """This function is called from Lua code as part of the mw.language
    inmplementation.  This maps a language code to its name."""
    if code in LANGUAGE_CODE_TO_NAME:
        return LANGUAGE_CODE_TO_NAME[code]
    return None


def fetch_language_names(ctx, include):
    """This function is called from Lua code as part of the mw.language
    implementation.  This returns a list of known language names."""
    include = str(include)
    if include == "all":
        ret = LANGUAGE_CODE_TO_NAME
    else:
        ret = {"en": "English"}
    return ctx.lua.table_from(dt)


def initialize_lua(ctx):
    assert ctx.lua is None
    # Load Lua sandbox code.
    lua_sandbox = open(lua_dir + "/sandbox.lua").read()

    def filter_attribute_access(obj, attr_name, is_setting):
        if isinstance(attr_name, unicode):
            if not attr_name.startswith("_"):
                return attr_name
        raise AttributeError("access denied")

    lua = LuaRuntime(unpack_returned_tuples=True,
                     register_eval=False,
                     attribute_filter=filter_attribute_access)
    lua.execute(lua_sandbox)
    lua.eval("lua_set_loader")(lambda x: lua_loader(ctx, x),
                               mw_text_decode,
                               mw_text_encode,
                               lambda x: get_page_info(ctx, x),
                               lambda x: get_page_content(ctx, x),
                               fetch_language_name,
                               lambda x: fetch_language_names(ctx, x))
    ctx.lua = lua


def call_lua_sandbox(ctx, invoke_args, expander, stack, parent):
    """Calls a function in a Lua module in the Lua sandbox.  This creates
    the sandbox instance if it does not already exist and stores it in
    ctx.lua.  ``invoke_args`` is the arguments to the call;
    ``expander`` should be a function to expand an argument.  Stack
    indicates how we ended up in this call; it is for debugging and
    error messages only.  This will restore stack to as it was before
    returning.  ``parent`` should be None or (parent_title,
    parent_args) for the parent page."""
    assert isinstance(invoke_args, (list, tuple))
    assert callable(expander)
    assert isinstance(stack, list)
    assert parent is None or isinstance(parent, (list, tuple))

    if len(invoke_args) < 2:
        ctx.error("#invoke {}: too few arguments at {}"
                  "".format(invoke_args, stack))
        return ("{{" + invoke_args[0] + ":" +
                "|".join(invoke_args[1:]) + "}}")

    # Get module and function name
    modname = expander(invoke_args[0]).strip()
    modfn = expander(invoke_args[1]).strip()

    # Initialize the Lua sandbox if not already initialized
    if ctx.lua is None:
        initialize_lua(ctx)
    lua = ctx.lua

    def value_with_expand(frame, fexpander, x):
        assert isinstance(frame, dict)
        assert isinstance(fexpander, str)
        assert isinstance(x, str)
        obj = {"expand": lambda obj: frame[fexpander](x)}
        return lua.table_from(obj)

    def make_frame(pframe, title, args):
        assert isinstance(title, str)
        assert isinstance(args, (list, tuple, dict))
        # Convert args to a dictionary with default value None
        if isinstance(args, dict):
            frame_args = args
        else:
            assert isinstance(args, (list, tuple))
            frame_args = {}
            num = 1
            for arg in args:
                m = re.match(r"""^\s*([^<>="']+?)\s*=\s*(.*?)\s*$""",
                             arg)
                if m:
                    # Have argument name
                    k, arg = m.groups()
                    if k.isdigit():
                        k = int(k)
                        if k < 1 or k > 1000:
                            k = 1000
                        if num <= k:
                            num = k + 1
                else:
                    # No argument name
                    k = num
                    num += 1
                frame_args[k] = arg
        frame_args = lua.table_from(frame_args)

        def extensionTag(frame, *args):
            if len(args) < 1:
                ctx.error("extensionTag: missing arguments at {}"
                          .format(stack))
                return ""
            dt = args[0]
            if not isinstance(dt, (str, int, float, type(None))):
                name = str(dt["name"] or "")
                content = str(dt["content"] or "")
                attrs = dt["args"] or {}
            elif len(args) == 1:
                name = str(args[0])
                content = ""
                attrs = {}
            elif len(args) == 2:
                name = str(args[0] or "")
                content = str(args[1] or "")
                attrs = {}
            else:
                name = str(args[0] or "")
                content = str(args[1] or "")
                attrs = args[2] or {}
            if not isinstance(attrs, str):
                attrs = list(v if isinstance(k, int) else
                             '{}="{}"'
                             .format(k, html.escape(v, quote=True))
                             for k, v in
                             sorted(attrs.items(),
                                    key=lambda x: str(x[0])))
            elif not attrs:
                attrs = []
            else:
                attrs = [attrs]

            stack.append("extensionTag()")
            ret = tag_fn(title, "#tag", [name, content] + attrs,
                         lambda x: x,  # Already expanded
                         stack)
            stack.pop()
            # Expand any templates from the result
            ret = preprocess(frame, ret)
            return ret

        def callParserFunction(frame, *args):
            if len(args) < 1:
                ctx.error("callParserFunction: missing name at {}"
                          .format(stack))
                return ""
            name = args[0]
            if not isinstance(name, str):
                new_args = name["args"]
                if isinstance(new_args, str):
                    new_args = { 1: new_args }
                else:
                    new_args = dict(new_args)
                name = name["name"] or ""
            else:
                new_args = []
            name = str(name)
            for arg in args[1:]:
                if isinstance(arg, (int, float, str)):
                    new_args.append(str(arg))
                else:
                    for k, v in sorted(arg.items(),
                                       key=lambda x: str(x[0])):
                        new_args.append(str(v))
            name = ctx._canonicalize_parserfn_name(name)
            if name not in PARSER_FUNCTIONS:
                ctx.error("frame:callParserFunction(): undefined function "
                          "{!r} at {}".format(name, stack))
                return ""
            return call_parser_function(ctx, name, new_args, lambda x: x,
                                        stack)

        def expand_all_templates(encoded):
            # Expand all templates here, even if otherwise only
            # expanding some of them.  We stay quiet about undefined
            # templates here, because Wiktionary Module:ugly hacks
            # generates them all the time.
            ret = ctx.expand(encoded, stack, parent, quiet=True)
            return ret

        def preprocess(frame, *args):
            if len(args) < 1:
                ctx.error("preprocess: missing argument at {}".format(stack))
                return ""
            v = args[0]
            if not isinstance(v, str):
                v = str(v["text"] or "")
            # Expand all templates, in case the Lua code actually
            # inspects the output.
            v = ctx._encode(v)
            stack.append("frame:preprocess()")
            ret = expand_all_templates(v)
            stack.pop()
            return ret

        def expandTemplate(frame, *args):
            if len(args) < 1:
                ctx.error("expandTemplate: missing arguments at {}"
                          "".format(stack))
                return ""
            dt = args[0]
            if isinstance(dt, (int, float, str, type(None))):
                ctx.error("expandTemplate: arguments should be named at {}"
                          "".format(stack))
                return ""
            title = dt["title"] or ""
            args = dt["args"] or {}
            new_args = [title]
            for k, v in sorted(args.items(), key=lambda x: str(x[0])):
                new_args.append("{}={}".format(k, v))
            encoded = ctx._save_value("T", new_args, False)
            stack.append("frame:expandTemplate()")
            ret = expand_all_templates(encoded)
            stack.pop()
            return ret

        # Create frame object as dictionary with default value None
        frame = {}
        frame["args"] = frame_args
        # argumentPairs is set in sandbox.lua
        frame["callParserFunction"] = callParserFunction
        frame["extensionTag"] = extensionTag
        frame["expandTemplate"] = expandTemplate
        # getArgument is set in sandbox.lua
        frame["getParent"] = lambda ctx: pframe
        frame["getTitle"] = lambda ctx: title
        frame["preprocess"] = preprocess
        # XXX still untested:
        frame["newParserValue"] = \
            lambda ctx, x: value_with_expand(ctx, "preprocess", x)
        frame["newTemplateParserValue"] = \
            lambda ctx, x: value_with_expand(ctx, "expand", x)
        # newChild set in sandbox.lua
        return lua.table_from(frame)

    # Create parent frame (for page being processed) and current frame
    # (for module being called)
    if parent is not None:
        parent_title, page_args = parent
        expanded_key_args = {}
        for k, v in page_args.items():
            if isinstance(k, str):
                expanded_key_args[expander(k)] = v
            else:
                expanded_key_args[k] = v
        pframe = make_frame(None, parent_title, expanded_key_args)
    else:
        pframe = None
    frame = make_frame(pframe, modname, invoke_args[2:])

    # Call the Lua function in the given module
    stack.append("Lua:{}:{}()".format(modname, modfn))
    old_stack = ctx.expand_stack
    ctx.expand_stack = stack
    try:
        ret = lua.eval("lua_invoke")(modname, modfn, frame, ctx.title)
        if not isinstance(ret, (list, tuple)):
            ok, text = ret, ""
        elif len(ret) == 1:
            ok, text = ret[0], ""
        else:
            ok, text = ret[0], ret[1]
    except UnicodeDecodeError:
        ctx.error("ERROR: {}: invalid unicode returned by {} at {}"
                  .format(ctx.title, invoke_args, stack))
        ok, text = True, ""
    finally:
        ctx.expand_stack = old_stack
    stack.pop()
    if ok:
        if text is None:
            text = "nil"
        return str(text)
    if isinstance(text, Exception):
        parts = [str(text)]
        lst = traceback.format_exception(etype=type(text),
                                         value=text,
                                         tb=text.__traceback__)
        for x in lst:
            parts.append("\t" + x.strip())
        text = "\n".join(parts)
    elif not isinstance(text, str):
        text = str(text)
    if text.find("'debug.error'") >= 0:
        ctx.warning(re.sub(r".*?:\d+: ", "", text.split("\n")[0]))
    else:
        parts = []
        in_traceback = 0
        for line in text.split("\n"):
            s = line.strip()
            #if s == "[C]: in function 'xpcall'":
            #    break
            parts.append(line)
        trace = "\n".join(parts)
        ctx.error("LUA error in #invoke {} at {}"
                  .format(invoke_args, stack),
                  trace=trace)
    return ""
