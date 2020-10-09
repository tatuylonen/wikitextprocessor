# wikitextprocessor

**This is currently work in progress and expected to be relased in
  October-November 2020.  Until then, feel free to experiment but the
  code is likely to be broken at times and support will be limited.**

This is a Python package for processing [WikiMedia dump
files](https://dumps;.wikimedia.org) from Wiktionary, Wikipedia, etc.,
for data extraction, error checking, offline conversion into HTML or
other formats, and other uses.  Key features include:

* Parsing WikiMedia dumps, including built-in support for processing pages
  in parallel
* WikiText syntax parser that converts the whole page into a parse tree
* Extracting template definitions and Lua module definitions from dump files
* Expanding selected templates or all templates, and code for
  heuristically identifying templates that need to be expanded before
  parsing is reasonably possible (e.g., templates that emit table
  start and end tags)
* Processing and expanding parser functions
* Processing, executing, and expanding Lua modules (they are very
  widely used in, e.g., Wiktionary, such as for generating IPA strings
  for many languages)
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

The best way to install this package is from pypi (XXX may not yet be
available):
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
WikiMedia dump files, go to [WikiMedia dump download
page](https://dumps.wikimedia.org/backup-index.html).  We recommend
using the <name>-<date>-pages-articles.xml.bz2 files (for Wiktionary,
this is about 17GB as of October 2020).

## API documentation

XXX
