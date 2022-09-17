import json
import sys
from pathlib import Path

import requests


def get_namespace_data(lang_code, siprop):
    # https://www.mediawiki.org/wiki/API:Siteinfo
    # https://www.mediawiki.org/wiki/Manual:Namespace
    # https://www.mediawiki.org/wiki/Help:Namespaces
    params = {
        "action": "query",
        "format": "json",
        "meta": "siteinfo",
        "siprop": siprop,
        "formatversion": "2",
    }
    r = requests.get(f"https://{lang_code}.wiktionary.org/w/api.php", params=params)
    return r.json()


SAVED_KEYS = {"id", "name", "content", "canonical"}


def main():
    """
    Get namespace data from MediaWiki API, but the result needs manual inspection
    because sometimes it doesn't return the English canonical name.
    For example, the French Wiktionary API returns "Annexe" as Appendix
    namespace's canonical name.
    """
    lang_code = sys.argv[1]
    namespaces = get_namespace_data(lang_code, "namespaces")
    json_dict = {}
    for _, data in namespaces["query"]["namespaces"].items():
        for k in data:
            if k not in SAVED_KEYS:
                del data[k]
        data["aliases"] = []
        data["issubject"] = False
        data["istalk"] = False
        if data["id"] < 0 or data["id"] % 2 == 0:
            data["issubject"] = True
        elif data["id"] % 2 != 0:
            data["istalk"] = True
        if data["name"] == "":
            data["name"] = "Main"
        canonical_name = data.get("canonical", "Main")
        if "canonical" in data:
            del data["canonical"]
        json_dict[canonical_name] = data

    namespacealiases = get_namespace_data(lang_code, "namespacealiases")
    for data in namespacealiases["query"]["namespacealiases"]:
        for ns_name, ns_data in json_dict.items():
            if ns_data["id"] == data["id"] and data["alias"] != ns_data["name"]:
                ns_data["aliases"].append(data["alias"])

    data_folder = Path(f"wikitextprocessor/data/{lang_code}")
    if not data_folder.exists():
        data_folder.mkdir()
    with data_folder.joinpath("namespaces.json").open("w", encoding="utf-8") as f:
        json.dump(json_dict, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    sys.exit(main())
