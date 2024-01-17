# WikiMedia dump file parser for Wiktionary, Wikipedia, and other projects.
#
# Copyright (c) 2018-2022 Tatu Ylonen.  See file LICENSE and https://ylonen.org

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .core import Wtp

from .interwiki import init_interwiki_map


def decompress_dump_file(dump_path: str) -> subprocess.Popen:
    if dump_path.endswith(".bz2"):
        decompress_command = (
            "lbzcat" if shutil.which("lbzcat") is not None else "bzcat"
        )
        p = subprocess.Popen(
            [decompress_command, dump_path], stdout=subprocess.PIPE
        )
        if p.stdout is not None:
            return p
        else:
            raise Exception(f"No stdout from command {decompress_command}")
    else:
        raise ValueError("Dump file extension is not .bz2")


def parse_dump_xml(wtp: "Wtp", dump_path: str, namespace_ids: set[int]) -> None:
    from lxml import etree

    with decompress_dump_file(dump_path) as p:
        namespace_str = "http://www.mediawiki.org/xml/export-0.10/"
        namespaces = {None: namespace_str}
        page_nums = 0
        for _, page_element in etree.iterparse(
            p.stdout,  # type: ignore
            tag=f"{{{namespace_str}}}page",
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

            text: Optional[str] = None
            redirect_to: Optional[str] = None
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

            wtp.add_page(
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
    wtp: "Wtp",
    path: str,
    namespace_ids: set[int],
    overwrite_folders: Optional[list[Path]] = None,
    skip_extract_dump: bool = False,
    save_pages_path: Optional[Path] = None,
    skip_analyze_templates: bool = False,
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
        parse_dump_xml(wtp, path, namespace_ids)
        if save_pages_path is not None:
            save_pages_to_file(wtp, save_pages_path)
        init_interwiki_map(wtp)

    add_default_templates(wtp)
    analyze_and_overwrite_pages(
        wtp, overwrite_folders, skip_extract_dump, skip_analyze_templates
    )


def add_default_templates(wtp: "Wtp") -> None:
    ns = wtp.NAMESPACE_DATA["Template"]
    ns_id = ns["id"]
    ns_local_name = ns["name"]
    default_templates = {
        "!": "|",  # magic word
        "=": "=",
        "((": "&lbrace;&lbrace;",  # {{((}} -> {{
        "))": "&rbrace;&rbrace;",  # {{))}} -> }}
    }
    for title, body in default_templates.items():
        title = f"{ns_local_name}:{title}"
        if not wtp.page_exists(title, ns_id):
            wtp.add_page(title, ns_id, body)


def analyze_and_overwrite_pages(
    wtp: "Wtp",
    overwrite_folders: Optional[list[Path]],
    skip_extract_dump: bool,
    skip_analyze_templates: bool,
) -> None:
    if overwrite_folders is not None:
        if overwrite_pages(wtp, overwrite_folders, False):
            # has template
            if skip_extract_dump:
                wtp.backup_db()
            overwrite_pages(wtp, overwrite_folders, True)
            if not skip_analyze_templates:
                wtp.analyze_templates()
        else:
            if not skip_analyze_templates and not wtp.has_analyzed_templates():
                wtp.analyze_templates()
            if skip_extract_dump:
                wtp.backup_db()
            overwrite_pages(wtp, overwrite_folders, True)
    elif not skip_analyze_templates and not wtp.has_analyzed_templates():
        wtp.analyze_templates()
    if skip_analyze_templates:
        wtp.db_conn.commit()


def overwrite_pages(
    wtp: "Wtp", folder_paths: list[Path], do_overwrite: bool
) -> bool:
    """
    Read text from passed paths and overwrite the correspond pages in database.
    If `do_overwrite` is `False`, do not write to database and returns `True` if
    the overwritten pages include template.
    """
    for folder_path in folder_paths:
        if not folder_path.exists():
            logging.warning(f"Override path: {folder_path} doesn't exist.")
            continue

        if folder_path.is_file() and folder_path.suffix == ".json":
            with folder_path.open(encoding="utf-8") as f:
                for title, page_data in json.load(f).items():
                    is_template = overwrite_single_page(
                        wtp,
                        title,
                        do_overwrite,
                        namespace_id=page_data.get("namespace_id"),
                        redirect_to=page_data.get("redirect_to"),
                        need_pre_expand=page_data.get("need_pre_expand", False),
                        body=page_data.get("body"),
                        model=page_data.get("model", "wikitext"),
                    )
                    if not do_overwrite and is_template:
                        return True
            continue

        if not folder_path.is_dir():
            continue
        # old overwrite file format that stars with "TTILE: "
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
                is_template = overwrite_single_page(
                    wtp, title, do_overwrite, body=body
                )
                if not do_overwrite and is_template:
                    return True

    wtp.db_conn.commit()
    return False


def overwrite_single_page(
    wtp: "Wtp",
    title: str,
    do_overwrite: bool,
    namespace_id: Optional[int] = None,
    redirect_to: Optional[str] = None,
    need_pre_expand: bool = False,
    body: Optional[str] = None,
    model: str = "wikitext",
) -> bool:
    template_ns_id = wtp.NAMESPACE_DATA.get("Template", {"id": None}).get("id")
    if namespace_id is None:
        if ":" in title:
            local_ns_name = title[: title.find(":")]
            namespace_id = wtp.NS_ID_BY_LOCAL_NAME.get(local_ns_name, 0)
        else:
            namespace_id = 0
    if do_overwrite:
        if model is None:
            module_ns_id = wtp.NAMESPACE_DATA.get("Module", {"id": None}).get(
                "id"
            )
            model = "Scribunto" if namespace_id == module_ns_id else "wikitext"
        wtp.add_page(
            title,
            namespace_id,
            body=body,
            redirect_to=redirect_to,
            need_pre_expand=need_pre_expand,
            model=model,
        )
    elif template_ns_id == namespace_id:
        return True

    return False


def path_is_on_windows_partition(path: Path) -> bool:
    """
    Return True if the path is on an exFAT or NTFS partition.
    """
    from psutil import disk_partitions

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


def get_windows_invalid_chars() -> set[str]:
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


def save_pages_to_file(wtp: "Wtp", directory: Path) -> None:
    on_windows = path_is_on_windows_partition(directory)
    name_max_length = os.pathconf("/", "PC_NAME_MAX")
    for page in wtp.get_all_pages():
        title = replace_invalid_substrings(page.title)
        if on_windows:
            title = replace_invalid_windows_characters(title)

        if page.namespace_id == 0:
            file_path = directory.joinpath(f"Words/{title[0:2]}/{title}.txt")
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
