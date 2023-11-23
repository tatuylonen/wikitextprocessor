from functools import cache


@cache
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


def mw_site_interwikiMap(wtp, filter_arg=None):
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
        if wtp.lang_code != "en":
            if new_map["url"].startswith(f"https://en.{wtp.project}.org"):
                new_map["isCurrentWiki"] = True
                new_map[
                    "url"
                ] = f"https://{wtp.lang_code}.{wtp.project}.org/wiki/$1"
            elif new_map["url"].startswith("https://en."):
                new_map[
                    "url"
                ] = f"https://{wtp.lang_code}.{new_map['url'][11:]}"
        if new_map["isProtocolRelative"]:
            new_map["url"] = new_map["url"].removeprefix("https:")
        if (
            filter_arg is None
            or (filter_arg == "local" and new_map["isLocal"])
            or (filter_arg == "!local" and not new_map["isLocal"])
        ):
            interwiki_map[result["prefix"]] = wtp.lua.table_from(new_map)

    return wtp.lua.table_from(interwiki_map)
