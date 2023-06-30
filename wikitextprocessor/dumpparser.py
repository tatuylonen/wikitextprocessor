# WikiMedia dump file parser for Wiktionary, Wikipedia, and other projects.
#
# Copyright (c) 2018-2022 Tatu Ylonen.  See file LICENSE and https://ylonen.org

import hashlib
import logging
import os
from psutil import disk_partitions
import shutil
import subprocess
import sys

from pathlib import Path
from typing import Optional, Set, List, IO, TYPE_CHECKING, Protocol
import unicodedata

if TYPE_CHECKING:
    from .core import Wtp


class DumpPageHandler(Protocol):
    def __call__(
        self,
        title: str,
        namespace_id: int,
        body: Optional[str] = None,
        redirect_to: Optional[str] = None,
        need_pre_expand: bool = False,
        model: Optional[str] = None,
    ) -> None:
        ...


def pick_stream(path: str) -> IO:
    if path.endswith(".bz2"):
        bzcat_command = (
            "lbzcat" if shutil.which("lbzcat") is not None else "bzcat"
        )
        subp = subprocess.Popen([bzcat_command, path], stdout=subprocess.PIPE)
        if subp.stdout is not None:
            return subp.stdout
        else:
            logging.warning(
                "subprocess.Popen.stdout = None! Opening file directly."
            )
    return open(path, "rb")


def process_input(
    path: str,
    page_cb: DumpPageHandler,
    namespace_ids: Set[int],
) -> None:
    """Processes the entire input once, calling chunk_fn for each chunk.
    A chunk is a list of data, where ``data`` is a dict
    containing at least "title" and "text" keys.  This returns a list
    of the values returned by ``chunk_fn`` in arbitrary order.  Each return
    value must be json-serializable."""

    # Open the input file, optionally decompressing on the fly (in a parallel
    # process to maximize concurrency).  This requires the ``buffer`` program.
    from lxml import etree

    with pick_stream(path) as wikt_f:
        if not wikt_f:
            logging.error("File or stdout is None??")
            return

        namespace_str = "http://www.mediawiki.org/xml/export-0.10/"
        namespaces = {None: namespace_str}
        page_nums = 0
        for _, page_element in etree.iterparse(
            wikt_f, tag=f"{{{namespace_str}}}page"
        ):
            title = page_element.findtext("title", "", namespaces)
            namespace_id = int(page_element.findtext("ns", "0", namespaces))
            if (
                namespace_id not in namespace_ids
                or title.endswith("/documentation")
                or "/testcases" in title
            ):
                page_element.clear(keep_tail=True)
                continue

            text = None
            redirect_to = None
            model = page_element.findtext("revision/model", "", namespaces)
            if (
                redirect_element := page_element.find(
                    "redirect", namespaces=namespaces
                )
            ) is not None:
                redirect_to = redirect_element.get("title", "")
                # redirect_to existing implies a redirection, but having a
                # .get default to "" is a bit weird: redirect to empty string?
                # But you can't use None either..?
            else:
                if model not in {"wikitext", "Scribunto", "json"}:
                    # ignore css, javascript and sanitized-css pages
                    page_element.clear(keep_tail=True)
                    continue
                text = page_element.findtext("revision/text", "", namespaces)

            page_cb(
                title,
                namespace_id,
                body=text,
                redirect_to=redirect_to,
                model=model,
            )
            page_element.clear(keep_tail=True)
            page_nums += 1
            if page_nums % 10000 == 0:
                logging.info(f"  ... {page_nums} raw pages collected")


def process_dump(
    ctx: "Wtp",
    path: str,
    namespace_ids: Set[int],
    overwrite_folders: Optional[List[Path]] = None,
    skip_extract_dump: bool = False,
    page_handler: Optional[DumpPageHandler] = None,
    save_pages_path: Optional[Path] = None,
) -> None:
    """Parses a WikiMedia dump file ``path`` (which should point to a
    "<project>-<date>-pages-articles.xml.bz2" file.  This implements
    the first phase of processing a dump - copying it to a temporary
    file with some preprocessing.  The Wtp.reprocess() must then be
    called to actually process the data."""

    logging.info(
        f"skip_extract_dump: {skip_extract_dump}, save_pages_path: "
        f"{str(save_pages_path)}"
    )
    logging.info(f"dump file path: {path}")

    # Run Phase 1 in a single thread; this mostly just extracts pages into
    # a SQLite database file.
    if not skip_extract_dump:
        process_input(
            path,
            page_handler if page_handler is not None else ctx.add_page,
            namespace_ids,
        )
        if save_pages_path is not None:
            save_pages_to_file(ctx, save_pages_path)

    analyze_and_overwrite_pages(ctx, overwrite_folders)


def analyze_and_overwrite_pages(
    ctx: "Wtp", overwrite_folders: Optional[List[Path]]
) -> None:
    if overwrite_folders is not None:
        if overwrite_pages(ctx, overwrite_folders, False):
            # has template
            ctx.backup_db()
            overwrite_pages(ctx, overwrite_folders, True)
            ctx.analyze_templates()
        else:
            if not ctx.has_analyzed_templates():
                ctx.analyze_templates()
            ctx.backup_db()
            overwrite_pages(ctx, overwrite_folders, True)
    elif not ctx.has_analyzed_templates():
        ctx.analyze_templates()


def overwrite_pages(
    ctx: "Wtp", folder_paths: List[Path], do_overwrite: bool
) -> bool:
    """
    Read text from passed paths and overwrite the correspond pages in database.
    If `do_overwrite` is `False`, do not write to database and returns `True` if
    the overwritten pages include template.
    """
    for folder_path in folder_paths:
        for file_path in folder_path.iterdir():
            if file_path.name.startswith("."):
                continue
            with file_path.open(encoding="utf-8") as f:
                first_line = f.readline()
                if not first_line.startswith("TITLE: "):
                    logging.error(
                        "First line of file supplied with --override must be "
                        '"TITLE: <page title>" (The page title for this would '
                        "normally start with Module:"
                    )
                    sys.exit(1)
                title = first_line[7:].strip()
                local_ns_name = title[: title.find(":")]
                ns_id = ctx.NS_ID_BY_LOCAL_NAME.get(local_ns_name, 0)
                if do_overwrite:
                    module_ns_id = ctx.NAMESPACE_DATA.get("Module", {}).get(
                        "id"
                    )
                    model = "Scribunto" if ns_id == module_ns_id else "wikitext"
                    ctx.add_page(title, ns_id, f.read(), model=model)
                else:
                    template_ns_id = ctx.NAMESPACE_DATA.get("Template", {}).get(
                        "id"
                    )
                    if template_ns_id == ns_id:
                        return True

    ctx.db_conn.commit()
    return False


def path_is_on_windows_partition(path: Path) -> bool:
    """
    Return True if the path is on an exFAT or NTFS partition.
    """
    path_matching_fstypes_mountpoints = [
        part
        for part in disk_partitions()
        if str(path.resolve()).startswith(part.mountpoint)
    ]
    # we want the more specific (i.e. longer) matching mountpoint
    path_fstype = sorted(
        path_matching_fstypes_mountpoints, key=lambda x: len(x.mountpoint)
    )[-1].fstype.lower()
    return path_fstype in {"exfat", "fuseblk", "ntfs"}


def get_windows_invalid_chars() -> Set[str]:
    return set(map(chr, range(0x00, 0x20))) | set(
        ["/", "\\", ":", "*", "?", '"', "<", ">", "|"]
    )


def invalid_char_to_charname(char: str) -> str:
    default_name = f"__0x{ord(char):X}__"
    return f"__{unicodedata.name(char, default_name).replace(' ','')}__".lower()


def replace_invalid_substrings(s: str) -> str:
    s = s.replace("//", "__slashslash__")
    if ".." in s:
        s = s.replace(".", "__dot__")
    return s


def replace_invalid_windows_characters(s: str) -> str:
    for char in get_windows_invalid_chars():
        s = s.replace(char, invalid_char_to_charname(char))
    return s


def save_pages_to_file(ctx: "Wtp", directory: Path) -> None:
    on_windows = path_is_on_windows_partition(directory)
    name_max_length = os.pathconf("/", "PC_NAME_MAX")
    for page in ctx.get_all_pages():
        title = replace_invalid_substrings(page.title)
        if on_windows:
            title = replace_invalid_windows_characters(title)

        if page.namespace_id == 0:
            file_path = directory.joinpath(
                f"Words/{title[0:2]}/{title}.txt"
            )
        else:
            file_path = directory.joinpath(f'{title.replace(":", "/", 1)}.txt')

        if len(file_path.name.encode()) > name_max_length:
            file_path = file_path.with_stem(
                file_path.stem[:50]
                + "_"
                + hashlib.sha256(file_path.stem.encode("utf-8")).hexdigest()
            )

        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("w", encoding="utf-8") as f:
            f.write(f"TITLE: {page.title}\n")
            if page.body:
                f.write(page.body)
            elif page.redirect_to:
                f.write(page.redirect_to)


# XXX parse <namespaces> and use that in both Python and Lua code

# XXX parse <case> to determine whether titles are case-sensitive
