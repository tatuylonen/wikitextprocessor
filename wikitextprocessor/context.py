# Definition of the processing context for Wikitext processing
#
# Copyright (c) 2020 Tatu Ylonen.  See file LICENSE and https://ylonen.org

# Character used for marking magic sequences.  This package assumes that this
# character does not occur on Wikitext pages.  This is a random character
# from a Unicode private area.
MAGIC_CHAR = "\U0010b03e"


class Wtp(object):
    """Context used for processing wikitext and for expanding templates,
    parser functions and Lua macros.  The indended usage pattern is to
    initialize this context once (this holds template and module definitions),
    and then using the context for processing many pages."""
    __slots__ = (
        "cookies",	 # Mapping from magic cookie -> expansion data
        "cookies_base",  # Cookies for processing template bodies
        "fullpage",	 # The unprocessed text of the current page (or None)
        "lua",		 # Lua runtime or None if not yet initialized
        "lua_path",	 # Path to Lua modules
        "modules",	 # Lua code for defined Lua modules
        "need_pre_expand",  # Set of template names to be expanded before parse
        "page_contents",  # Full content for selected pages (e.g., Thesaurus)
        "page_seq",	 # All content pages (title, ofs, len) in sequence
        "redirects",	 # Redirects in the wikimedia project
        "rev_ht",	 # Mapping from text to magic cookie
        "rev_ht_base",   # Rev_ht from processing template bodies
        "stack",	 # Saved stack before calling Lua function
        "template_fn",   # None or function to expand template
        "template_name", # name of template currently being expanded
        "templates",     # dict temlate name -> definition
        "title",         # current page title
        "tmp_file",	 # Temporary file used to store templates and pages
        "tmp_ofs",	 # Next write offset
        "writebuf",
        "writebufofs",
        "writebufsize",
    )
    def __init__(self):
        self.cookies_base = []
        self.cookies = []
        self.lua = None
        self.page_contents = {}
        self.page_seq = []
        self.rev_ht_base = {}
        self.rev_ht = {}
        self.stack = []
        self.modules = {}
        self.templates = {}
        # Some predefined templates
        self.templates["!"] = "&vert;"
        self.templates["%28%28"] = "&lbrace;&lbrace;"  # {{((}}
        self.templates["%29%29"] = "&rbrace;&rbrace;"  # {{))}}
        self.need_pre_expand = set()
        self.redirects = {}
        self.tmp_file = tempfile.TemporaryFile(mode="w+b", buffering=0) # XXXdir
        self.tmp_ofs = 0
        self.writebufofs = 0
        self.writebufsize = 1024 * 1024
        self.writebuf = bytearray(self.writebufsize)

    def _save_value(self, kind, args):
        """Saves a value of a particular kind and returns a unique magic
        cookie for it."""
        assert kind in ("T", "A", "L")  # Template/parserfn, arg, link
        assert isinstance(args, (list, tuple))
        args = tuple(args)
        v = (kind, args)
        if v in self.rev_ht_base:
            return MAGIC_CHAR + kind + str(self.rev_ht[v]) + MAGIC_CHAR
        if v in self.rev_ht:
            return MAGIC_CHAR + kind + str(self.rev_ht[v]) + MAGIC_CHAR
        idx = len(self.cookies)
        self.cookies.append(v)
        self.rev_ht[v] = idx
        ret = MAGIC_CHAR + kind + str(idx) + MAGIC_CHAR
        return ret

    def _encode(self, text):
        """Encode all templates, template arguments, and parser function calls
        in the text, from innermost to outermost."""

        def repl_arg(m):
            """Replacement function for template arguments."""
            orig = m.group(1)
            args = orig.split("|")
            return self.save_value("A", args)

        def repl_templ(m):
            """Replacement function for templates {{...}} and parser
            functions."""
            args = m.group(1).split("|")
            return self.save_value("T", args)

        def repl_link(m):
            """Replacement function for links [[...]]."""
            orig = m.group(1)
            return self.save_value("L", (orig,))

        # Main loop of encoding.  We encode repeatedly, always the innermost
        # template, argument, or parser function call first.  We also encode
        # links as they affect the interpretation of templates.
        while True:
            prev = text
            # Encode links.
            text = re.sub(r"\[\[([^][{}]+)\]\]", repl_link, text)
            # Encode template arguments.  We repeat this until there are
            # no more matches, because otherwise we could encode the two
            # innermost braces as a template transclusion.
            while True:
                prev2 = text
                text = re.sub(r"(?s)\{\{\{(([^{}]|\}[^}]|\}\}[^}])*?)\}\}\}",
                              repl_arg, text)
                if text == prev2:
                    break
            # Encode templates
            text = re.sub(r"(?s)\{\{(([^{}]|\}[^}])+?)\}\}",
                          repl_templ, text)
            # We keep looping until there is no change during the iteration
            if text == prev:
                break
            prev = text
        return text

    def collect_page(self, tag, title, text, save_pages=True):
        """Collects information about the page.  For templates and modules,
        this keeps the content in memory.  For other pages, this saves the
        content in a temporary file so that it can be accessed later.  There
        must be enough space on the volume containing the temporary file
        to store the entire contents of the uncompressed WikiMedia dump.
        The content is saved because it is common for Wiktionary Lua macros
        to access content from arbitrary pages.  Furthermore, this way we
        only need to decompress and parse the dump file once."""
        title = html.unescape(title)
        text = html.unescape(text)
        if tag == "#redirect":
            self.redirects[title] = text
            return
        if tag == "Scribunto":
            modname1 = re.sub(" ", "_", title)
            self.modules[modname1] = text
            return
        if title.endswith("/testcases"):
            return
        if title.startswith("User:"):
            return
        if tag == "Thesaurus":
            self.page_contents[title] = text
            return
        if tag != "Template":
            if not save_pages:
                return
            rawtext = text.encode("utf-8")
            if self.writebufofs + len(rawtext) > self.writebufsize:
                bufview = memoryview(self.writebuf)[0: self.writebufofs]
                self.tmp_file.write(bufview)
                self.writebufofs = 0
            ofs = self.tmp_ofs
            self.tmp_ofs += len(rawtext)
            if len(rawtext) >= self.writebufofs:
                self.tmp_file.write(rawtext)
            else:
                self.writebuf[self.writebufofs:
                              self.writebufofs + len(rawtext)] = rawtext
            self.page_contents[title] = (title, ofs, len(rawtext))
            self.page_seq.append((title, ofs, len(rawtext)))
            return

        # It is a template
        name = canonicalize_template_name(title)
        body = template_to_body(title, text)
        assert isinstance(body, str)
        ctx.templates[name] = body

    def analyze_templates(self):
        """Analyzes templates to determine which of them might create elements
        essential to parsing Wikitext syntax, such as table start or end
        tags.  Such templates generally need to be expanded before
        parsing the page."""
        included_map = collections.defaultdict(set)
        expand_q = []
        for name, body in self.templates.items():
            included_templates, pre_expand = analyze_template(name, body)
            for x in included_templates:
                included_map[x].add(name)
            if pre_expand:
                ctx.need_pre_expand.add(name)
                expand_q.append(name)

        # XXX consider encoding template bodies here (also need to save related
        # cookies).  This could speed up their expansion, where the first
        # operation is to encode them.  (Consider whether cookie numbers from
        # nested template expansions could conflict)

        # Propagate pre_expand from lower-level templates to all templates that
        # refer to them
        while expand_q:
            name = expand_q.pop()
            if name not in included_map:
                continue
            for inc in included_map[name]:
                if inc in ctx.need_pre_expand:
                    continue
                #print("propagating EXP {} -> {}".format(name, inc))
                ctx.need_pre_expand.add(inc)
                expand_q.append(name)

        # Copy template definitions to redirects to them
        for k, v in ctx.redirects.items():
            if not k.startswith("Template:"):
                # print("Unhandled redirect src", k)
                continue
            k = k[9:]
            if not v.startswith("Template:"):
                # print("Unhandled redirect dst", v)
                continue
            v = v[9:]
            k = canonicalize_template_name(k)
            v = canonicalize_template_name(v)
            if v not in ctx.templates:
                # print("{} redirects to non-existent template {}".format(k, v))
                continue
            if k in ctx.templates:
                # print("{} -> {} is redirect but already in templates"
                #       "".format(k, v))
                continue
            ctx.templates[k] = ctx.templates[v]
            if v in ctx.need_pre_expand:
                ctx.need_pre_expand.add(k)

    def _initialize_lua(self):
        assert self.lua is None
        # Load Lua sandbox code.
        lua_sandbox = open("lua/sandbox.lua").read()

        def filter_attribute_access(obj, attr_name, is_setting):
            print("FILTER:", attr_name, is_setting)
            if isinstance(attr_name, unicode):
                if not attr_name.startswith("_"):
                    return attr_name
            raise AttributeError("access denied")

        lua = LuaRuntime(unpack_returned_tuples=True,
                         register_eval=False,
                         attribute_filter=filter_attribute_access)
        lua.execute(lua_sandbox)
        lua.eval("lua_set_loader")(lambda x: lua_loader(self, x),
                                   mw_text_decode,
                                   mw_text_encode,
                                   lambda x: get_page_info(self, x),
                                   lambda x: get_page_content(self, x),
                                   fetch_language_name,
                                   lambda x: fetch_language_names(self, x))
        self.lua = lua


    def start_page(self, title):
        """Starts a new page for expanding Wikitext.  This saves the title and
        full page source in the context.  Calling this is mandatory for each
        page; expand_wikitext() can then be called multiple times for the same
        page."""
        assert isinstance(title, str)
        # variables and thus must be reloaded for each page.
        self.lua = None  # Force reloading modules for every page
        self.title = title

    def expand(self, text, pre_only=False, template_fn=None,
               templates_to_expand=None,
               expand_parserfns=True, expand_invoke=True)
        """Expands templates and parser functions (and optionally Lua macros)
        from ``text`` (which is from page with title ``title``).
        ``templates_to_expand`` should be a set (or dictionary)
        containing those canonicalized template names that should be
        expanded (None expands all).  ``template_fn``, if given, will
        be used to expand templates; if it is not defined or returns
        None, the default expansion will be used (it can also be used
        to capture template arguments).  This returns the text with
        the given templates expanded."""
        assert isinstance(text, str)
        assert isinstance(templates_to_expand, (set, dict, type(None)))
        assert template_fn is None or callable(template_fn)
        assert self.title is not None  # start_page() must have been called
        self.template_fn = template_fn
        self.cookies = []
        self.rev_ht = {}

        # If templates_to_expand is None, then expand all known templates
        if templates_to_expand is None:
            templates_to_expand = self.templates

        def unexpanded_template(args):
            """Formats an unexpanded template (whose arguments may have been
            partially or fully expanded)."""
            return "{{" + "|".join(args) + "}}"

        def invoke_fn(invoke_args, expander, stack, parent):
            """This is called to expand a #invoke parser function."""
            assert isinstance(invoke_args, (list, tuple))
            assert callable(expander)
            assert isinstance(stack, list)
            assert isinstance(parent, (tuple, type(None)))
            # print("invoke_fn", invoke_args)
            # sys.stdout.flush()
            if len(invoke_args) < 2:
                print("#invoke {}: too few arguments at {}"
                      "".format(invoke_args, stack))
                return ("{{" + invoke_args[0] + ":" +
                        "|".join(invoke_args[1:]) + "}}")

            # Initialize the Lua sandbox if not already initialized
            if self.lua is None:
                initialize_lua(self)
            lua = self.lua

            # Get module and function name
            modname = invoke_args[0].strip()
            modfn = invoke_args[1].strip()

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
                        print("extensionTag: missing arguments at {}"
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
                        print("callParserFunction: missing name at {}"
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
                    name = canonicalize_parserfn_name(name)
                    if name not in PARSER_FUNCTIONS:
                        print("frame:callParserFunction(): undefined function "
                              "{!r} at {}".format(name, stack))
                        return ""
                    return call_parser_function(name, new_args, lambda x: x,
                                                self.title, stack)

                def expand_all_templates(encoded):
                    # Expand all templates here, even if otherwise only
                    # expanding some of them.  We stay quiet about undefined
                    # templates here, because Wiktionary Module:ugly hacks
                    # generates them all the time.
                    ret = expand(encoded, stack, parent, self.templates,
                                 quiet=True)
                    return ret

                def preprocess(frame, *args):
                    if len(args) < 1:
                        print("preprocess: missing arg at {}".format(stack))
                        return ""
                    v = args[0]
                    if not isinstance(v, str):
                        v = str(v["text"] or "")
                    # Expand all templates, in case the Lua code actually
                    # inspects the output.
                    v = self._encode(v)
                    stack.append("frame:preprocess()")
                    ret = expand_all_templates(v)
                    stack.pop()
                    return ret

                def expandTemplate(frame, *args):
                    if len(args) < 1:
                        print("expandTemplate: missing arguments at {}"
                              "".format(stack))
                        return ""
                    dt = args[0]
                    if isinstance(dt, (int, float, str, type(None))):
                        print("expandTemplate: arguments should be named at {}"
                              "".format(stack))
                        return ""
                    title = dt["title"] or ""
                    args = dt["args"] or {}
                    new_args = [title]
                    for k, v in sorted(args.items(), key=lambda x: str(x[0])):
                        new_args.append("{}={}".format(k, v))
                    sys.stdout.flush()
                    encoded = self._save_value("T", new_args)
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
                frame["getParent"] = lambda self: pframe
                frame["getTitle"] = lambda self: title
                frame["preprocess"] = preprocess
                # XXX still untested:
                frame["newParserValue"] = \
                    lambda self, x: value_with_expand(self, "preprocess", x)
                frame["newTemplateParserValue"] = \
                    lambda self, x: value_with_expand(self, "expand", x)
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
            sys.stdout.flush()
            stack.append("Lua:{}:{}()".format(modname, modfn))
            old_stack = self.stack
            self.stack = stack
            try:
                ret = lua.eval("lua_invoke")(modname, modfn, frame, self.title)
                if not isinstance(ret, (list, tuple)):
                    ok, text = ret, ""
                elif len(ret) == 1:
                    ok, text = ret[0], ""
                else:
                    ok, text = ret[0], ret[1]
            except UnicodeDecodeError:
                print("ERROR: {}: invalid unicode returned by {} at {}"
                      .format(self.title, invoke_args, stack))
                ok, text = True, ""
            finally:
                self.stack = old_stack
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
                # print("ERROR at {}".format(stack))
                print("{}: {}"
                      .format(self.title,
                              re.sub(r".*?:\d+: ", "", text.split("\n")[0])))
            else:
                print("LUA ERROR IN #invoke {} at {}"
                      .format(invoke_args, stack))
                parts = []
                in_traceback = 0
                for line in text.split("\n"):
                    s = line.strip()
                    if s == "[C]: in function 'xpcall'":
                        break
                    parts.append(line)
                print("\n".join(parts))
            return ""

        def expand(coded, stack, parent, templates_to_expand, quiet=False):
            """This function does most of the work for expanding encoded
            templates, arguments, and parser functions."""
            assert isinstance(coded, str)
            assert isinstance(stack, list)
            assert isinstance(parent, (tuple, type(None)))
            assert isinstance(templates_to_expand, (set, dict))
            assert quiet in (False, True)

            def expand_args(coded, argmap):
                assert isinstance(coded, str)
                assert isinstance(argmap, dict)
                parts = []
                pos = 0
                for m in re.finditer(r"!{}(.)(\d+)!".format(magic), coded):
                    new_pos = m.start()
                    if new_pos > pos:
                        parts.append(coded[pos:new_pos])
                    pos = m.end()
                    kind = m.group(1)
                    idx = int(m.group(2))
                    kind = m.group(1)
                    kind2, args = self.cookies[idx]
                    assert isinstance(args, tuple)
                    assert kind == kind2
                    if kind == "T":
                        # Template transclusion - map arguments in its arguments
                        new_args = tuple(map(lambda x: expand_args(x, argmap),
                                             args))
                        parts.append(self._save_value(kind, new_args))
                        continue
                    if kind == "A":
                        # Template argument reference
                        if len(args) > 2:
                            print("{}: too many args ({}) in argument "
                                  "reference {!r} at {}"
                                  .format(self.title, len(args), args, stack))
                        stack.append("ARG-NAME")
                        k = expand(expand_args(args[0], argmap),
                                   stack, parent, self.templates).strip()
                        stack.pop()
                        if k.isdigit():
                            k = int(k)
                        v = argmap.get(k, None)
                        if v is not None:
                            parts.append(v)
                            continue
                        if len(args) >= 2:
                            stack.append("ARG-DEFVAL")
                            ret = expand_args(args[1], argmap)
                            stack.pop()
                            parts.append(ret)
                            continue
                        # The argument is not defined (or name is empty)
                        arg = "{{{" + str(k) + "}}}"
                        parts.append(arg)
                        continue
                    if kind == "L":
                        # Link to another page
                        content = args[0]
                        content = expand_args(content, argmap)
                        parts.append("[[" + content + "]]")
                        continue
                    print("{}: expand_arg: unsupported cookie kind {!r} in {}"
                          "".format(self.title, kind, m.group(0)))
                    parts.append(m.group(0))
                parts.append(coded[pos:])
                return "".join(parts)

            def expand_parserfn(fn_name, args):
                if not expand_parserfns:
                    if not args:
                        return "{{" + fn_name + "}}"
                    return "{{" + fn_name + ":" + "|".join(args) + "}}"
                # Call parser function
                stack.append(fn_name)
                expander = lambda arg: expand(arg, stack, parent,
                                              self.templates)
                if fn_name == "#invoke":
                    if not expand_invoke:
                        return "{{#invoke:" + "|".join(args) + "}}"
                    ret = invoke_fn(args, expander, stack, parent)
                else:
                    ret = call_parser_function(fn_name, args, expander,
                                               self.title, stack)
                stack.pop()  # fn_name
                # XXX if lua code calls frame:preprocess(), then we should
                # apparently encode and expand the return value, similarly to
                # template bodies (without argument expansion)
                # XXX current implementation of preprocess() does not match!!!
                return str(ret)

            # Main code of expand()
            parts = []
            pos = 0
            for m in re.finditer(r"!{}(.)(\d+)!".format(magic), coded):
                new_pos = m.start()
                if new_pos > pos:
                    parts.append(coded[pos:new_pos])
                pos = m.end()
                kind = m.group(1)
                idx = int(m.group(2))
                kind2, args = self.cookies[idx]
                assert isinstance(args, tuple)
                assert kind == kind2
                if kind == "T":
                    # Template transclusion or parser function call
                    # Limit recursion depth
                    if len(stack) >= 100:
                        print("{}: too deep expansion of templates via {}"
                              "".format(self.title, stack))
                        parts.append(unexpanded_template(args))
                        continue

                    # Expand template/parserfn name
                    stack.append("TEMPLATE_NAME")
                    tname = expand(args[0], stack, parent, templates_to_expand)
                    stack.pop()

                    # Strip safesubst: and subst: prefixes
                    tname = tname.strip()
                    if tname[:10].lower() == "safesubst:":
                        tname = tname[10:]
                    elif tname[:6].lower() == "subst:":
                        tname = tname[6:]

                    # Check if it is a parser function call
                    ofs = tname.find(":")
                    if ofs > 0:
                        # It might be a parser function call
                        fn_name = canonicalize_parserfn_name(tname[:ofs])
                        # Check if it is a recognized parser function name
                        if (fn_name in PARSER_FUNCTIONS or
                            fn_name.startswith("#")):
                            ret = expand_parserfn(fn_name,
                                                  (tname[ofs + 1:].lstrip(),) +
                                                  args[1:])
                            parts.append(ret)
                            continue

                    # As a compatibility feature, recognize parser functions
                    # also as the first argument of a template (withoout colon),
                    # whether there are more arguments or not.  This is used
                    # for magic words and some parser functions have an implicit
                    # compatibility template that essentially does this.
                    fn_name = canonicalize_parserfn_name(tname)
                    if fn_name in PARSER_FUNCTIONS or fn_name.startswith("#"):
                        ret = expand_parserfn(fn_name, args[1:])
                        parts.append(ret)
                        continue

                    # Otherwise it must be a template expansion
                    name = canonicalize_template_name(tname)
                    if name.startswith("Template:"):
                        name = name[9:]

                    # Check for undefined templates
                    if name not in self.templates:
                        if not quiet:
                            print("{}: undefined template {!r} at {}"
                                  "".format(self.title, tname, stack))
                        parts.append(unexpanded_template(args))
                        continue

                    # If this template is not one of those we want to expand,
                    # return it unexpanded (but with arguments possibly
                    # expanded)
                    if name not in templates_to_expand:
                        parts.append(unexpanded_template(args))
                        continue

                    # Construct and expand template arguments
                    stack.append(name)
                    ht = {}
                    num = 1
                    for i in range(1, len(args)):
                        arg = str(args[i])
                        m = re.match(r"""^\s*([^<>="']+?)\s*=\s*(.*?)\s*$""",
                                     arg)
                        if m:
                            # Note: Whitespace is stripped by the regexp
                            # around named parameter names and values per
                            # https://en.wikipedia.org/wiki/Help:Template
                            # (but not around unnamed parameters)
                            k, arg = m.groups()
                            if k.isdigit():
                                k = int(k)
                                if k < 1 or k > 1000:
                                    print("{}: invalid argument number {}"
                                          "".format(self.title, k))
                                    k = 1000
                                if num <= k:
                                    num = k + 1
                            else:
                                stack.append("ARGNAME")
                                k = expand(k, stack, parent, self.templates)
                                stack.pop()
                        else:
                            k = num
                            num += 1
                        # Expand arguments in the context of the frame where
                        # they are defined.  This makes a difference for
                        # calls to #invoke within a template argument (the
                        # parent frame would be different).
                        stack.append("ARGVAL-{}".format(k))
                        arg = expand(arg, stack, parent, self.templates)
                        stack.pop()
                        ht[k] = arg

                    # Expand the body, either using ``template_fn`` or using
                    # normal template expansion
                    t = None
                    if self.template_fn is not None:
                        t = template_fn(name, ht)
                    if t is None:
                        body = self.templates[name]
                        # XXX optimize by pre-encoding bodies during
                        # preprocessing
                        # (Each template is typically used many times)
                        # Determine if the template starts with a list item
                        contains_list = (re.match(r"(?s)^[#*;:]", body)
                                         is not None)
                        if contains_list:
                            body = "\n" + body
                        encoded_body = self._encode(body)
                        # Expand template arguments recursively.  The arguments
                        # are already expanded.
                        encoded_body = expand_args(encoded_body, ht)
                        # Expand the body using the calling template/page as
                        # the parent frame for any parserfn calls
                        new_title = tname.strip()
                        for prefix in ("Media", "Special", "Main", "Talk",
                                       "User",
                                       "User_talk", "Project", "Project_talk",
                                       "File", "Image", "File_talk",
                                       "MediaWiki", "MediaWiki_talk",
                                       "Template", "Template_talk",
                                       "Help", "Help_talk", "Category",
                                       "Category_talk", "Module",
                                       "Module_talk"):
                            if tname.startswith(prefix + ":"):
                                break
                        else:
                            new_title = "Template:" + new_title
                        new_parent = (new_title, ht)
                        # XXX no real need to expand here, it will expanded on
                        # next iteration anyway (assuming parent unchanged)
                        # Otherwise expand the body
                        t = expand(encoded_body, stack, new_parent,
                                   templates_to_expand)

                    assert isinstance(t, str)
                    stack.pop()  # template name
                    parts.append(t)
                elif kind == "A":
                    # The argument is outside transcluded template body
                    arg = "{{{" + "|".join(args) + "}}}"
                    parts.append(arg)
                elif kind == "L":
                    # Link to another page
                    content = args[0]
                    stack.append("[[link]]")
                    content = expand(content, stack, parent,
                                     templates_to_expand)
                    stack.pop()
                    parts.append("[[" + content + "]]")
                else:
                    print("{}: expand: unsupported cookie kind {!r} in {}"
                          "".format(self.title, kind, m.group(0)))
                    parts.append(m.group(0))
            parts.append(coded[pos:])
            return "".join(parts)

        # Encode all template calls, template arguments, and parser function
        # calls on the page.  This is an inside-out operation.
        # print("Encoding")
        encoded = self._encode(text)

        # Recursively expand the selected templates.  This is an outside-in
        # operation.
        # print("Expanding")
        expanded = expand(encoded, [self.title], None, templates_to_expand)

        return expanded


    def parse(self, text, pre_expand=False, expand_all=False):
        XXX

    # XXX collect_specials(self)
    # XXX import_specials(self, path)
    # XXX export_specials(self, path)

# XXX store errors and debug messages in the context
