from functools import cache


def get_interwiki_data():
    import requests

    r = requests.get(
        "https://www.mediawiki.org/w/api.php",
        params={
            "action": "query",
            "meta": "siteinfo",
            "siprop": "interwikimap",
            "format": "json",
            "formatversion": 2,
        },
        headers={"user-agent": "wikitextprocessor"},
    )
    if r.ok:
        results = r.json()
        return results.get("query", {}).get("interwikimap", [])
    return []


@cache
def get_interwiki_map(lang_code, project):
    # https://www.mediawiki.org/wiki/Manual:Interwiki
    # https://www.mediawiki.org/wiki/Extension:Scribunto/Lua_reference_manual#mw.site.interwikiMap
    interwiki_map = {}
    for result in get_interwiki_data():
        new_map = {
            "prefix": result["prefix"],
            "url": result["url"],
            "isProtocolRelative": result.get("protorel", False),
            "isLocal": result.get("local", False),
            "isCurrentWiki": False,
            "isTranscludable": False,
            "isExtraLanguageLink": False,
        }
        if lang_code != "en":
            if new_map["url"].startswith(f"https://en.{project}.org"):
                new_map["isCurrentWiki"] = True
                new_map[
                    "url"
                ] = f"https://{lang_code}.{project}.org/wiki/$1"
            elif new_map["url"].startswith("https://en."):
                new_map[
                    "url"
                ] = f"https://{lang_code}.{new_map['url'][11:]}"
        if new_map["isProtocolRelative"]:
            new_map["url"] = new_map["url"].removeprefix("https:")
        interwiki_map[result["prefix"]] = new_map

    return interwiki_map


def mw_site_interwikiMap(wtp, filter_arg=None):
    # https://www.mediawiki.org/wiki/Manual:Interwiki
    # https://www.mediawiki.org/wiki/Extension:Scribunto/Lua_reference_manual#mw.site.interwikiMap
    interwiki_map = {}
    for key, value in get_interwiki_map(wtp.lang_code, wtp.project).items():
        if (
            filter_arg is None
            or (filter_arg == "local" and value["isLocal"])
            or (filter_arg == "!local" and not value["isLocal"])
        ):
            interwiki_map[key] = wtp.lua.table_from(value)

    return wtp.lua.table_from(interwiki_map)
