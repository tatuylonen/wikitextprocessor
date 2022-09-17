import csv
import json
import sys
from pathlib import Path

import requests


def download_lang_csv(lang_code: str, csv_path: Path) -> None:
    # https://www.mediawiki.org/wiki/API:Expandtemplates
    # https://en.wiktionary.org/wiki/Module:list_of_languages,_csv_format
    params = {
        "action": "expandtemplates",
        "format": "json",
        "text": "{{#invoke:list of languages, csv format|show}}",
        "prop": "wikitext",
        "formatversion": "2",
    }
    r = requests.get(f"https://{lang_code}.wiktionary.org/w/api.php", params=params)
    data = r.json()
    csv_text = (
        data["expandtemplates"]["wikitext"]
        .removeprefix("<pre>\n")
        .removesuffix("</pre>")
    )
    with csv_path.open("w", encoding="utf-8") as f:
        f.write(csv_text)


def parse_csv(wiki_lang_code: str) -> dict[str, list[str]]:
    csv_path = Path(f"{wiki_lang_code}_languages.csv")
    if not csv_path.exists():
        download_lang_csv(wiki_lang_code, csv_path)

    lang_data = {}
    with csv_path.open(newline="", encoding="utf-8") as csvfile:
        next(csvfile)  # skip header line
        for row in csv.reader(csvfile, delimiter=";"):
            lang_code = row[1]
            canonical_name = row[2]
            other_names = row[-2].split(",") if row[-2] else []
            lang_data[lang_code] = [canonical_name] + other_names

    with open(
        f"wikitextprocessor/data/{wiki_lang_code}/languages.json", "w", encoding="utf-8"
    ) as f:
        json.dump(lang_data, f, indent=2, ensure_ascii=False)


def main():
    lang_code = sys.argv[1]
    if lang_code in ["en", "zh"]:
        parse_csv(lang_code)
    else:
        pass


if __name__ == "__main__":
    sys.exit(main())
