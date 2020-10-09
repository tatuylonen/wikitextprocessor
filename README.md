# wikitextprocessor

**This is currently work in progress and expected to be relased in
  October-November 2020.  Until then, feel free to experiment but the
  code is likely to be broken at times and support will be limited.
  Most of the code exists and will be moved here from another
  repository and cleaned up during this time.  [This is not quite yet
  ready from experimentation.]**

This is a Python package for processing [WikiMedia dump
files](https://dumps.wikimedia.org) for
[Wiktionary](https://www.wiktionary.org),
[Wikipedia](https://www.wikipedia.org), etc., for data extraction,
error checking, offline conversion into HTML or other formats, and
other uses.  Key features include:

* Parsing WikiMedia dumps, including built-in support for processing pages
  in parallel
* [Wikitext](https://en.wikipedia.org/wiki/Help:Wikitext) syntax
  parser that converts the whole page into a parse tree
* Extracting template definitions and
  [Scribunto](https://www.mediawiki.org/wiki/Extension:Scribunto/Lua_reference_manual)
  Lua module definitions from dump files
* Expanding selected templates or all templates, and code for
  heuristically identifying templates that need to be expanded before
  parsing is reasonably possible (e.g., templates that emit table
  start and end tags)
* Processing and expanding parser functions
* Processing, executing, and expanding Scribunto Lua modules (they are
  very widely used in, e.g., Wiktionary, such as for generating
  [IPA](https://en.wikipedia.org/wiki/International_Phonetic_Alphabet)
  strings for many languages)
* Controlled expansion of selected page parts
* Capturing information from template arguments while expanding them,
  as tempate arguments often contain useful information not available
  in the expanded content.

This module is primarily intended as a building block for other
packages that process Wikitionary or Wikipedia data, particularly for
data extraction.  You will need to write code to use this.

For pre-existing extraction modules that use this package, please see:

* [Wiktextract](https://github.com/tatuylonen/wiktextract) for
extracting rich machine-readable dictionaries from Wiktionary.

## Getting started

### Installing

The best way to install this package is from [pypi](https://pypi.org)
(XXX may not yet be available):
```
pip3 install wikitextprocessor
```

Alternatively, you may install the master branch from Wiktionary:
```
git clone https://github.com/tatuylonen/wikitextprocessor
cd wikitextprocessor
pip3 install -e .
```

### Running tests

This package includes tests written using the ``unittest`` framework.
They can be run using, for example, ``nose``, which can be installed
using ``pip3 install nose``.

To run the tests, use the following command in the top-level directory:
```
nosetests
```

### Obtaining WikiMedia dump files

This package is primarily intended for processing Wiktionary and
Wikipedia dump files (though you can also use it for processing
individual pages or files that are in Wikitext format).  To download
WikiMedia dump files, go to the [dump download
page](https://dumps.wikimedia.org/backup-index.html).  We recommend
using the <name>-<date>-pages-articles.xml.bz2 files (for Wiktionary,
this is about 17GB as of October 2020).

## Expected performance

This can generally process a few pages second per processor core,
including expansion of all templates, Lua macros, and parsing the full
page.  On a multi-core machine, this can generally process a few dozen
pages per second, depending on the speed and number of cores.

## API documentation

XXX tentative plan:
```
   from wikitextprocessor import Wtp
   ctx = Wtp()

   def page_handler(title, text, XXX):
       ctx.start_page(title)
       tree = ctx.parse(text, pre_expand=True)
       ... process parse tree
         ... value = ctx.expand_node(node)

   ctx.process("enwiktionary-20200901-pages-articles.xml.bz2", page_handler)


XXX tentative class outline

```
class Wtp(object):

    __init__(self)

    set_backend(XXX)
      - optional, to set backend for storing captured templates and modules
        and pages somewhere else than main memory (or perhaps give relevant
        parameters, such as directory path, as argument to constructor)

    collect_specials(XXX)
      - intended to be directly used as a capture callback for dumpparser
      - XXX memory use, storage backend?

    import_specials(path)
      - import special page data from the given file

    export_specials(path)
      - save special page data to the given file

    analyze_templates()
      - analyzes which templates should be expanded before parsing (that
        affect the overall Wikitext syntax, for example by generating table
        start or end).  This will be automatically performed if not already
        done when calling expand the first time; however, when multiprocessing,
        it may be desirable to perform this once before forking.

    start_page(title)
      - this must be called to start processing a new page

    expand(text, pre_only=False, template_fn=None,
           templates_to_expand=None,
           expand_parserfns=True, expand_invoke=True)
      - expands templates, parser functions, and Lua macros from
        the text.  start_page() must be called before this.

    parse(text, pre_expand=False, expand_all=False)
      - parses the text as Wikitext, returning a parse tree.  If pre_expand
        is True, first expands those templates that affect the overall
        Wikitext syntax.  If expand_all is True, then expands all templates
        and Lua macros before parsing.  start_page() must be called before
        this.

    expand_node(node, template_fn=None, templates_to_expand=None,
                expand_parserfns=True, expand_invoke=True)
      - expands the wikitext covered by the given node in a parse tree
        returned by parse()

```

XXX processing dump files, parallelization
