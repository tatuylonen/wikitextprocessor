# wikitextprocessor

**This is currently work in progress and expected to be relased in
  October-November 2020.  Until then, feel free to experiment but the
  code has not yet been fully tested and may be broken on some days.
  Most things should already work.**

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
* Processing and expanding Wikitext parser functions
* Processing, executing, and expanding Scribunto Lua modules (they are
  very widely used in, e.g., Wiktionary, for example for generating
  [IPA](https://en.wikipedia.org/wiki/International_Phonetic_Alphabet)
  strings for many languages)
* Controlled expansion parts of pages for applications that parse
  overall page structure before parsing but then expand templates on
  certain sections of the page
* Capturing information from template arguments while expanding them,
  as template arguments often contain useful information not available
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
(XXX not yet available):
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

Usage example:

```
   from wikitextprocessor import Wtp
   ctx = Wtp()

   def page_handler(model, title, text):
       if model != "wikitext" or title.startswith("Template:"):
           return None
       tree = ctx.parse(text, pre_expand=True)
       ... process parse tree
         ... value = ctx.expand_node(node)

   ctx.process("enwiktionary-20200901-pages-articles.xml.bz2", page_handler)
```

XXX

```
class Wtp(object):

    __init__(self)

    process(path, page_handler)
      - parses dump file, calls page_handler(title, text) for each page
        (in parallel using multiprocessing) and returns list of results

    parse(text, pre_expand=False, expand_all=False)
      - parses the text as Wikitext, returning a parse tree.  If pre_expand
        is True, first expands those templates that affect the overall
        Wikitext syntax.  If expand_all is True, then expands all templates
        and Lua macros before parsing.  start_page() must be called before
        this.

    expand(text, pre_only=False, template_fn=None,
           templates_to_expand=None,
           expand_parserfns=True, expand_invoke=True)
      - expands templates, parser functions, and Lua macros from
        the text.  start_page() must be called before this.

    expand_node(node, template_fn=None, templates_to_expand=None,
                expand_parserfns=True, expand_invoke=True)
      - expands the wikitext covered by the given node in a parse tree
        returned by parse()
      - XXX this function has not yet been implemented

    start_page(title)
      - this must be called to start processing a new page
      - automatically called by process() during the second page before
        calling the page handler
      - no need to call this when processing pages via process(), but this
        must be called if processing pages obtained otherwise

```
