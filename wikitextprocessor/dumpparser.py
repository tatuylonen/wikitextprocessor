# WikiMedia dump file parser for Wiktionary, Wikipedia, and other projects.
#
# Copyright (c) 2018-2022 Tatu Ylonen.  See file LICENSE and https://ylonen.org

import hashlib
import logging
import os
import json
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import IO, TYPE_CHECKING, Dict, List, Optional, Protocol, Set

from psutil import disk_partitions

if TYPE_CHECKING:
    from .core import Page, Wtp


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

    def pick_stream() -> IO[bytes]:
        if path.endswith(".bz2"):
            bzcat_command: str = (
                "lbzcat" if shutil.which("lbzcat") is not None else "bzcat"
            )
            subp: subprocess.Popen[bytes] = subprocess.Popen(
                [bzcat_command, path], stdout=subprocess.PIPE
            )
            if subp.stdout:
                return subp.stdout
            else:
                logging.error(
                    "subprocess.Popen.stdout = None!" "Opening file directly."
                )
        return open(path, "rb")

    with pick_stream() as wikt_f:
        if not wikt_f:
            logging.error("File or stdout is None??")
            return

        namespace_str: str = "http://www.mediawiki.org/xml/export-0.10/"
        namespaces: Dict[None, str] = {None: namespace_str}

        page_nums: int = 0
        page_element: etree._Element  # preannotate to make type-checker happy
        for _, page_element in etree.iterparse(
            wikt_f, tag=f"{{{namespace_str}}}page"
        ):
            title: str = page_element.findtext("title", "", namespaces)
            namespace_id: int = int(
                page_element.findtext("ns", "0", namespaces)
            )
            if (
                namespace_id not in namespace_ids
                or title.endswith("/documentation")
                or "/testcases" in title
            ):
                page_element.clear(keep_tail=True)
                continue

            text: Optional[str] = None
            redirect_to: Optional[str] = None
            model: Optional[str] = page_element.findtext(
                "revision/model", "", namespaces
            )
            redirect_element: Optional[etree._Element]  # can't annotate walrus
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

    def add_page_wrapper(ctx: "Wtp") -> DumpPageHandler:
        """Method to wrap ctx.add_page into a function that can be
        used with the type-checking Protocol DumpPageHandler.
        Because ctx.add_page is a method, even though it's method
        signature (and "Callable" form) look like they should be
        right, mypy doesn't accept it as a DumpPageHandler."""

        def _add_page_wrapper(
            title: str,
            namespace_id: int,
            body: Optional[str] = None,
            redirect_to: Optional[str] = None,
            need_pre_expand: bool = False,
            model: Optional[str] = None,
        ) -> None:
            ctx.add_page(
                title, namespace_id, body, redirect_to, need_pre_expand, model
            )

        return _add_page_wrapper

    wrapped_add_page = add_page_wrapper(ctx)

    # Run Phase 1 in a single thread; this mostly just extracts pages into
    # a SQLite database file.
    if not skip_extract_dump:
        process_input(
            path,
            page_handler if page_handler is not None else wrapped_add_page,
            namespace_ids,
        )
        if save_pages_path is not None:
            save_pages_to_file(ctx, save_pages_path)

    analyze_and_overwrite_pages(ctx, overwrite_folders, skip_extract_dump)


def analyze_and_overwrite_pages(
    ctx: "Wtp", overwrite_folders: Optional[List[Path]], skip_extract_dump: bool
) -> None:
    if overwrite_folders is not None:
        if overwrite_pages(ctx, overwrite_folders, False):
            # has template
            if skip_extract_dump:
                ctx.backup_db()
            overwrite_pages(ctx, overwrite_folders, True)
            ctx.analyze_templates()
        else:
            if not ctx.has_analyzed_templates():
                ctx.analyze_templates()
            if skip_extract_dump:
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
        if folder_path.is_file() and folder_path.suffix == ".json":
            with folder_path.open(encoding="utf-8") as f:
                for title, body in json.load(f).items():
                    is_template = overwite_single_page(
                        ctx, title, body, do_overwrite
                    )
                    if not do_overwrite and is_template:
                        return True
            continue

        # old overwite file format that stars with "TTILE: "
        for file_path in folder_path.iterdir():
            if file_path.name.startswith(".") or file_path.suffix == ".json":
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
                body = f.read()
                is_template = overwite_single_page(
                    ctx, title, body, do_overwrite
                )
                if not do_overwrite and is_template:
                    return True

    ctx.db_conn.commit()
    return False


def overwite_single_page(
    ctx: "Wtp", title: str, body: str, do_overwrite: bool
) -> bool:
    template_ns_id = ctx.NAMESPACE_DATA.get("Template", {"id": None}).get("id")
    if ":" in title:
        local_ns_name = title[: title.find(":")]
        ns_id = ctx.NS_ID_BY_LOCAL_NAME.get(local_ns_name, 0)
    else:
        ns_id = 0
    if do_overwrite:
        module_ns_id = ctx.NAMESPACE_DATA.get("Module", {"id": None}).get("id")
        model = "Scribunto" if ns_id == module_ns_id else "wikitext"
        ctx.add_page(title, ns_id, body, model=model)
    elif template_ns_id == ns_id:
        return True

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
    return (
        path_fstype == "exfat"
        or path_fstype == "fuseblk"
        or path_fstype == "ntfs"
    )


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
    on_windows: bool = path_is_on_windows_partition(directory)
    name_max_length: int = os.pathconf("/", "PC_NAME_MAX")
    page: "Page"
    for page in ctx.get_all_pages():
        title: str = replace_invalid_substrings(page.title)
        if on_windows:
            title = replace_invalid_windows_characters(title)

        if page.namespace_id == 0:
            file_path: Path = directory.joinpath(
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
            if page.body is not None:
                f.write(page.body)
            elif page.redirect_to:
                f.write(page.redirect_to)


# XXX parse <namespaces> and use that in both Python and Lua code

# XXX parse <case> to determine whether titles are case-sensitive
