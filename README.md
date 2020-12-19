# wikitextprocessor

This is a Python package for processing [WikiMedia dump
files](https://dumps.wikimedia.org) for
[Wiktionary](https://www.wiktionary.org),
[Wikipedia](https://www.wikipedia.org), etc., for data extraction,
error checking, offline conversion into HTML or other formats, and
other uses.  Key features include:

* Parsing dump files, including built-in support for processing pages
  in parallel
* [Wikitext](https://en.wikipedia.org/wiki/Help:Wikitext) syntax
  parser that converts the whole page into a parse tree
* Extracting template definitions and
  [Scribunto](https://www.mediawiki.org/wiki/Extension:Scribunto/Lua_reference_manual)
  Lua module definitions from dump files
* Expanding selected templates or all templates, and
  heuristically identifying templates that need to be expanded before
  parsing is reasonably possible (e.g., templates that emit table
  start and end tags)
* Processing and expanding Wikitext parser functions
* Processing, executing, and expanding Scribunto Lua modules (they are
  very widely used in, e.g., Wiktionary, for example for generating
  [IPA](https://en.wikipedia.org/wiki/International_Phonetic_Alphabet)
  strings for many languages)
* Controlled expansion of parts of pages for applications that parse
  overall page structure before parsing but then expand templates on
  certain sections of the page
* Capturing information from template arguments while expanding them,
  as template arguments often contain useful information not available
  in the expanded content.

This module is primarily intended as a building block for other
packages that process Wikitionary or Wikipedia data, particularly for
data extraction.  You will need to write code to use this.

For pre-existing extraction modules that use this package, please see:

* [Wiktextract](https://github.com/tatuylonen/wiktextract/) for
extracting rich machine-readable dictionaries from Wiktionary.

## Getting started

### Installing

The best way to install this package is from [pypi](https://pypi.org):
```
pip3 install wikitextprocessor
```

Alternatively, you may install the master branch from github:
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
individual pages or other files that are in Wikitext format).  To
download WikiMedia dump files, go to the [dump download
page](https://dumps.wikimedia.org/backup-index.html).  We recommend
using the <name>-<date>-pages-articles.xml.bz2 files.

## Expected performance

This can generally process a few Wiktionary pages second per processor
core, including expansion of all templates, Lua macros, parsing the
full page, and analyzing the parse.  On a multi-core machine, this can
generally process a few dozen to a few hundred pages per second,
depending on the speed and number of cores.

Most of the processing effort goes to expanding Lua macros.  You can
elect not to expand Lua macros, but they are used extensively in
Wiktionary and for important information.  Expanding templates and Lua
macros allows much more robust and complete data extraction, but does
not come cheap.

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
         ... value = ctx.node_to_wikitext(node)

   ctx.process("enwiktionary-20201201-pages-articles.xml.bz2", page_handler)
```

The basic operation of ``Wtp.process()`` is as follows:
* Extract templates, modules, and other pages from the dump file and save
  them in a temporary file
* Heuristically analyze which templates need to be pre-expanded before
  parsing to make sense of the page structure (this cannot detect templates
  that call Lua code that outputs Wikitext that affects parsed structure).
  These first steps together are called the "first phase".
* Process the pages again, calling a page handler function for each page.
  The page handler can extract, parse, and otherwise process the page, and
  has full access to templates and Lua macros defined in the dump.  This may
  call the page handler in multiple processes in parallel.  Return values
  from the page handler calls are returned to the caller (this function acts
  as an iterator).  This is called the second phase.
* Optionally, the ``Wtp.reprocess()`` function may be used for processing the
  same data several times (it basically repeats the second phase).

Most of the functionality is hidden behind the ``Wtp`` object.
Additionally, ``WikiNode`` objects are used for representing the parse
tree that is returned by the ``Wtp.parse()`` function.  ``NodeKind``
is an enumeration type used to encode the type of a WikiNode.
Additionally, ``ALL_LANGUAGES`` is exported and is a list that
describes all languages (language codes, names, and other data) used
in Wiktionary.

### class Wtp(object)

```
def __init__(self, quiet=False, num_threads=None, cache_file=None)
```

The initializer can usually be called without arguments, but recognizes
the following arguments:
* ``quiet`` - if set to True, suppress progress messages during processing
* ``num_threads`` - if set to an integer, use that many parallel processes
  for processing the dump.  The default is to use as many processors as there
  are available cores/hyperthreads.  You may need to limit the number of
  parallel processes if you are limited by available memory; we have found
  that processing Wiktionary (including templates and Lua macros)
  requires 3-4GB of memory per process.  This MUST be set to 1 on Windows.
* ``cache_file`` can normally be ``None``, in which case a temporary file will
  be created under ``/tmp``, or a path (string) for the cache file(s).
  There are two reasons why you might want to
  set this: 1) you don't have enough space on ``/tmp`` (the whole uncompressed
  dump must fit there, which can easily be 10-20GB), or 2) for testing.
  If you specify the cache file, if an existing cache file exists, that will be
  loaded and used, eliminating the time needed for Phase 1 (this is very
  important for testing, allowing processing single pages reasonably fast).
  In this case, you should not call ``Wtp.process()`` but instead use
  ``Wtp.reprocess()`` or just call ``Wtp.expand()`` or ``Wtp.parse()`` on
  Wikitext that you have obtained otherwise (e.g., from some file).
  If the cache file doesn't exist, you will need to call ``Wtp.process()``
  to parse a dump file, which will initialize the cache file during the
  first phase.  If you wish to re-create cache file, you should remove
  the old cache file first.  The cache file path is actually a prefix for
  multiple individual files.

**Windows note: For now you probably need to set ``num_threads`` to 1
on Windows.** This is because Python's ``multiprocessing`` module
doesn't use ``fork()`` in Windows, and the code relies on being able
to access global variables in the child processes.  Setting
``num_threads`` to 1 avoids ``fork()`` altogether and should work.

**Based on notes in Python ``multiprocessing`` module version 3.8,
  MacOS also doesn't use fork() any more by default.** So you probably
  need to set ``num_threads`` to 1 on MacOS too for now.

```
def process(self, path, page_handler, phase1_only=False)
```

This function processes a WikiMedia dump, uncompressing and extracing pages
(including templates and Lua modules), and calling ``Wtp.add_page()`` for
each page (phase 1).  Then this calls ``Wtp.reprocess()`` to execute the
second phase.

This takes the following arguments:
* ``path`` (string) - path to the WikiMedia dump file to be processed
  (e.g., "enwiktionary-20201201-pages-articles.xml.bz2").  Note that the
  compressed file can be used.  Dump files can be
  downloaded [here](https://dumps.wikimedia.org).
* ``page_handler`` (function) - this function will be called for each page
  in phase 2 (unless ``phase1_only`` is set to True).  The call takes the form
  ``page_handler(model, title, data)``, where ``model`` is the ``model`` value
  for the page in the dump (``wikitext`` for normal wikitext pages and
  templates, ``Scribunto`` for Lua modules; other values are also possible),
  ``title`` is page title (e.g., ``sample`` or ``Template:foobar``
  or ``Module:mystic``), and ``data`` is the contents of the page (usually
  Wikitext).
* ``phase1_only`` (boolean) - if set to True, prevents calling phase 2
  processing and the ``page_handler`` function will not be called.  The
  ``Wtp.reprocess()`` function can be used to run the second phase separately,
  or ``Wtp.expand()``, ``Wtp.parse()`` and other functions can be used.

This function returns an iterator over the values returned by the
``page_handler`` function (if ``page_handler`` returns ``None`` or no value,
the iterator does not return those values).  Note that ``page_handler`` will
usually be run a separate process (separate processes in parallel), and
cannot pass any values back in global variables.  It can, however, access
global variables assigned before calling ``Wtp.process()`` (in Linux only).

```
def parse(text, pre_expand=False, expand_all=False, additional_expand=None)
```

      - parses the text as Wikitext, returning a parse tree.  If pre_expand
        is True, first expands those templates that affect the overall
        Wikitext syntax.  If expand_all is True, then expands all templates
        and Lua macros before parsing.  start_page() must be called before
        this.

    expand(text, pre_expand=False, template_fn=None,
           templates_to_expand=None, expand_parserfns=True,
           expand_invoke=True)
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

    add_page(model, title, text)
      - Adds a new page for interpretation (it could define template, lua
        macros, or could be a normal wikitext page).  Pages are saved in a
        temporary file for use during expansion.
      - This is exposed primarily for testing or for processing single pages
        without reading the whole dump file.
      - This is automatically called by process(), so there is normally no
        need to call this explicitly.

    analyze_templates()
      - Analyzes which templates should be expanded before parsing a page
        (e.g., because they may produce syntactic elements, such as table
        starts or table rows).
      - This is automatically called by process(), so there is normally no
        need to call this explicitly.  However, if templates are added by
        calling add_page() manually, then this should be called after adding
        the last template.
```
