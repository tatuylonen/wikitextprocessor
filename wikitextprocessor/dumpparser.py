# WikiMedia dump file parser for Wiktionary, Wikipedia, and other projects.
#
# Copyright (c) 2018-2022 Tatu Ylonen.  See file LICENSE and https://ylonen.org

import html
import logging
import shutil
import subprocess
import sys

from pathlib import Path
from typing import Optional, Set, List

from typing import Optional
from collections.abc import Callable


def process_input(path: str, page_cb: Callable[[str, str], None], namespace_ids: Set[int]) -> None:
    """Processes the entire input once, calling chunk_fn for each chunk.
    A chunk is a list of data, where ``data`` is a dict
    containing at least "title" and "text" keys.  This returns a list
    of the values returned by ``chunk_fn`` in arbitrary order.  Each return
    value must be json-serializable."""

    # Open the input file, optionally decompressing on the fly (in a parallel
    # process to maximize concurrency).  This requires the ``buffer`` program.
    from lxml import etree

    if path.endswith(".bz2"):
        bzcat_command = "lbzcat" if shutil.which("lbzcat") is not None else "bzcat"
        subp = subprocess.Popen([bzcat_command, path], stdout=subprocess.PIPE)
        wikt_f = subp.stdout
    else:
        wikt_f = open(path, "rb")

    namespace_str = "http://www.mediawiki.org/xml/export-0.10/"
    namespaces = {None: namespace_str}

    for _, page_element in etree.iterparse(wikt_f, tag=f"{{{namespace_str}}}page"):
        title = html.unescape(page_element.findtext("title", "", namespaces))
        title_without_prefix = title[title.find(":") + 1:]
        namespace_id = int(page_element.findtext("ns", "0", namespaces))
        if namespace_id not in namespace_ids or title_without_prefix.startswith("User:") or \
           title.endswith(("/documentation", "/testcases", "/sandbox")):
            page_element.clear(keep_tail=True)
            continue

        text = None
        redirect_to = None
        model = page_element.findtext("revision/model", "", namespaces)
        if (redirect_element := page_element.find("redirect", namespaces=namespaces)) is not None:
            redirect_to = html.unescape(redirect_element.get("title", ""))
        else:
            if model not in {"wikitext", "Scribunto", "json"}:
                # ignore css, javascript and sanitized-css pages
                page_element.clear(keep_tail=True)
                continue
            text = html.unescape(page_element.findtext("revision/text", "", namespaces))

        page_cb(title, namespace_id, body=text, redirect_to=redirect_to, model=model)
        page_element.clear(keep_tail=True)

    wikt_f.close()

def process_dump(ctx: "Wtp", path: str, namespace_ids: Set[int], overwrite_folders: Optional[List[Path]] = None,
                 page_handler: Optional[Callable[[str, int], None]] = None) -> None:
    """Parses a WikiMedia dump file ``path`` (which should point to a
    "<project>-<date>-pages-articles.xml.bz2" file.  This implements
    the first phase of processing a dump - copying it to a temporary
    file with some preprocessing.  The Wtp.reprocess() must then be
    called to actually process the data."""

    # Run Phase 1 in a single thread; this mostly just extracts pages into
    # a temporary file.
    process_input(path, page_handler if page_handler else ctx.add_page, namespace_ids)
    if overwrite_folders is not None:
        overwrite_pages(ctx, overwrite_folders)

    ctx.db_session.commit()
    # Analyze which templates should be expanded before parsing
    logging.info("Analyzing which templates should be expanded before parsing")
    ctx.analyze_templates()


def overwrite_pages(ctx: "Wtp", folder_paths: List[Path]) -> None:
    for folder_path in folder_paths:
        for file_path in folder_path.iterdir():
            with file_path.open(encoding="utf-8") as f:
                first_line = f.readline()
                if not first_line.startswith("TITLE: "):
                    logging.error(
                        'First line of file supplied with --override must be "TITLE: <page title>"'
                        '(The page title for this would normally start with Module:')
                    sys.exit(1)
                title = first_line[7:].strip()
                local_ns_name = title[:title.find(":")]
                ns_id = ctx.NS_ID_BY_LOCAL_NAME.get(local_ns_name, 0)
                module_ns_id = ctx.NAMESPACE_DATA.get("Module", {}).get("id")
                model = "Scribunto" if ns_id == module_ns_id else "wikitext"
                ctx.add_page(title, ns_id, f.read(), model=model)

# XXX parse <namespaces> and use that in both Python and Lua code

# XXX parse <case> to determine whether titles are case-sensitive
