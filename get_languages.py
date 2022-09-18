import argparse
import csv
import json
import sys
from pathlib import Path

import requests


def download_lang_csv(domain: str, csv_path: Path) -> None:
    # https://www.mediawiki.org/wiki/API:Expandtemplates
    # https://en.wiktionary.org/wiki/Module:list_of_languages,_csv_format
    params = {
        "action": "expandtemplates",
        "format": "json",
        "text": "{{#invoke:list of languages, csv format|show}}",
        "prop": "wikitext",
        "formatversion": "2",
    }
    r = requests.get(f"https://{domain}/w/api.php", params=params)
    data = r.json()
    csv_text = (
        data["expandtemplates"]["wikitext"]
        .removeprefix("<pre>\n")
        .removesuffix("</pre>")
    )
    with csv_path.open("w", encoding="utf-8") as f:
        f.write(csv_text)


def parse_csv(domain: str, wiki_lang_code: str) -> dict[str, list[str]]:
    csv_path = Path(f"{wiki_lang_code}_languages.csv")
    if not csv_path.exists():
        download_lang_csv(domain, csv_path)

    lang_data = {}
    with csv_path.open(newline="", encoding="utf-8") as csvfile:
        next(csvfile)  # skip header line
        for row in csv.reader(csvfile, delimiter=";"):
            lang_code = row[1]
            canonical_name = row[2]
            other_names = row[-2].split(",") if row[-2] else []
            lang_data[lang_code] = [canonical_name] + other_names

    data_folder = Path(f"wikitextprocessor/data/{wiki_lang_code}")
    if not data_folder.exists():
        data_folder.mkdir()
    with data_folder.joinpath("languages.json").open("w", encoding="utf-8") as f:
        json.dump(lang_data, f, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "domain", help="MediaWiki domain, for example: en.wiktionary.org"
    )
    parser.add_argument("lang_code", help="MediaWiki language code")
    args = parser.parse_args()
    if args.lang_code in ["en", "zh"]:
        parse_csv(args.domain, args.lang_code)
    else:
        pass


if __name__ == "__main__":
    sys.exit(main())
