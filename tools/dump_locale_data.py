import argparse
import json
import locale
import os
import pathlib

from wikitextprocessor.core import LocalizationData

parser = argparse.ArgumentParser(
    description="Generate config files for locale stuff"
)
parser.add_argument(
    "langdirs",
    type=pathlib.Path,
    help="Directory containing language configuration "
    "directories, usually 'src/wikitextprocessor/data/...'."
    "This is used as input to determine what language codes "
    "need to have configs generated for them.",
)

parser.add_argument(
    "outputdir",
    type=pathlib.Path,
    help="Directory where individual directories named "
    "by language code ('en/', 'de/' etc.) are outputted. "
    "Recommended not to use src/wikitextprocessor/data "
    "directly, but to copy-paste into that directory later.",
)
args = parser.parse_args()


def main() -> None:
    # get the names (lang-codes) of the config directories
    dirs = sorted([f.name for f in os.scandir(args.langdirs) if f.is_dir()])
    # print(dirs)

    # list of language-code -> locale code
    # map. Based on your system, yet many of these locale codes fail
    aliases = locale.locale_alias

    configs: dict[str, LocalizationData] = {}

    for dir_code in dirs:
        main_code = dir_code.split("-")[0]
        if dir_code not in aliases and main_code not in aliases:
            continue
        if dir_code not in aliases:
            lang_code = main_code
        else:
            lang_code = dir_code

        alias = aliases[lang_code]
        utf8ed = alias.split(".")[0] + ".UTF-8"
        failed = True
        plog = []
        for x in (alias, utf8ed):
            try:
                locale.setlocale(locale.LC_ALL, x)
                failed = False
                plog.append(f"{x=} succeeded")
                break
            except Exception as e:
                plog.append(f"Failed {e=} for {x=}")

        if failed:
            plog.append(
                f"BOTH FAILED {dir_code=} {alias=}, {utf8ed=}; no "
                "config file will be generated"
            )
        print("[[" + "\n".join(plog) + "]]")
        if failed:
            continue

        envv = locale.localeconv()
        sep: str = envv["thousands_sep"]  # type: ignore
        decimal: str = envv["decimal_point"]  # type: ignore
        grouping: tuple[int] = tuple(envv["grouping"])  # type: ignore
        mon_grouping: tuple[int] = tuple(envv["mon_grouping"])  # type:ignore

        # For some reason, for hindi "grouping" and "mon_grouping" are
        # different, so we will use the "non-default" one.
        if grouping != mon_grouping:
            if grouping == (3, 0):
                grouping = mon_grouping

        configs[dir_code] = {
            "decimal_point": decimal,
            "grouping_method": tuple(grouping),
            "grouping_separator": sep,
        }

    for dirname, locdata in configs.items():
        data_folder = args.outputdir / dirname
        if not data_folder.exists():
            data_folder.mkdir()
        with open(
            data_folder / "localization.json",
            mode="w",
            encoding="utf-8",
        ) as f:
            json.dump(locdata, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
