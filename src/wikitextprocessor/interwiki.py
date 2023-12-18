from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from .core import Wtp


def get_interwiki_data(wtp: "Wtp") -> list[dict[str, Union[str, bool]]]:
    import requests

    r = requests.get(
        f"https://{wtp.lang_code}.{wtp.project}.org/w/api.php",
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


def init_interwiki_map(wtp: "Wtp") -> None:
    wtp.db_conn.execute(
        """
    CREATE TABLE IF NOT EXISTS interwiki_maps (
    prefix TEXT PRIMARY KEY,
    url TEXT,
    protorel INTEGER,
    local INTEGER)
    """
    )
    if len(get_interwiki_map(wtp)) == 0:
        for result in get_interwiki_data(wtp):
            wtp.db_conn.execute(
                "INSERT INTO interwiki_maps VALUES(?, ?, ?, ?)",
                (
                    result["prefix"],
                    result["url"],
                    result.get("protorel", False),
                    result.get("local", False),
                ),
            )
        wtp.db_conn.commit()


def get_interwiki_map(wtp: "Wtp") -> dict[str, dict[str, Union[str, bool]]]:
    return {
        prefix: {
            "prefix": prefix,
            "url": url if not protorel else url.removeprefix("https:"),
            "isProtocolRelative": bool(protorel),
            "isLocal": bool(local),
            "isCurrentWiki": url.startswith(
                f"https://{wtp.lang_code}.{wtp.project}.org"
            ),
            "isTranscludable": False,
            "isExtraLanguageLink": False,
        }
        for (prefix, url, protorel, local) in wtp.db_conn.execute(
            "SELECT * FROM interwiki_maps"
        )
    }


def mw_site_interwikiMap(wtp, filter_arg=None):
    # https://www.mediawiki.org/wiki/Manual:Interwiki
    # https://www.mediawiki.org/wiki/Extension:Scribunto/Lua_reference_manual#mw.site.interwikiMap
    interwiki_map = {}
    for key, value in get_interwiki_map(wtp).items():
        if (
            filter_arg is None
            or (filter_arg == "local" and value["isLocal"])
            or (filter_arg == "!local" and not value["isLocal"])
        ):
            interwiki_map[key] = wtp.lua.table_from(value)

    return wtp.lua.table_from(interwiki_map)
