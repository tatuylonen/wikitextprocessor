import re
import sys
from datetime import datetime
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from .core import Wtp


def query_wikidata(wtp: "Wtp", query: str) -> dict[str, dict[str, str]]:
    import requests

    r = requests.get(
        "https://query.wikidata.org/sparql",
        params={"query": query, "format": "json"},
        headers={"user-agent": "wikitextprocessor"},
    )
    if r.ok:
        result = r.json()
        for binding in result.get("results", {}).get("bindings", []):
            return binding
    wtp.error("WIKIDATA QUERY failed", f"{query=} {r.text=}", "query_wikidata")
    return {}


def init_wikidata_cache(wtp: "Wtp") -> None:
    wtp.db_conn.executescript(
        """
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS wikidata_items(
    id TEXT PRIMARY KEY,
    label TEXT,
    description TEXT
    );

    CREATE TABLE IF NOT EXISTS wikidata_properties(
    id TEXT UNIQUE,
    label TEXT,
    PRIMARY KEY(id, label)
    );

    CREATE TABLE IF NOT EXISTS wikidata_property_values(
    value TEXT,
    item_id TEXT,
    property_id TEXT,
    PRIMARY KEY(item_id, property_id),
    FOREIGN KEY(item_id) REFERENCES wikidata_items(id),
    FOREIGN KEY(property_id) REFERENCES wikidata_properties(id)
    );
    """
    )


def get_statement_cache(wtp: "Wtp", prop: str, item: str) -> Union[str, None]:
    query = """SELECT value FROM wikidata_property_values
    JOIN wikidata_items ON wikidata_property_values.item_id = wikidata_items.id
    JOIN wikidata_properties
      ON wikidata_property_values.property_id = wikidata_properties.id
    WHERE wikidata_items.id = ? AND """
    if re.fullmatch(r"P\d+", prop):
        query += "wikidata_property_values.property_id = ?"
    else:
        query += "wikidata_properties.label = ?"
    for (value,) in wtp.db_conn.execute(query, (item, prop)):
        return value
    return None


def save_statement_cache(
    wtp: "Wtp",
    item_id: str,
    item_label: str,
    item_desc: str,
    prop_id: str,
    prop_label: str,
    prop_value: str,
):
    with wtp.db_conn:
        wtp.db_conn.execute(
            """
            INSERT OR IGNORE INTO wikidata_items (id, label, description)
            VALUES(?, ?, ?)
            """,
            (item_id, item_label, item_desc),
        )
        wtp.db_conn.execute(
            """
            INSERT OR IGNORE INTO wikidata_properties (id, label)
            VALUES(?, ?)
            """,
            (prop_id, prop_label),
        )
        wtp.db_conn.execute(
            """
            INSERT INTO wikidata_property_values (value, item_id, property_id)
            VALUES(?, ?, ?);
            """,
            (prop_value, item_id, prop_id),
        )


def statement_query(wtp: "Wtp", prop: str, item_id: str, lang_code: str) -> str:
    result = get_statement_cache(wtp, prop, item_id)
    if result is not None:
        return result
    if re.fullmatch(r"P\d+", prop):
        prop_is_id = True
        query = f"""
        SELECT ?valueLabel ?itemLabel ?itemDescription ?propLabel WHERE {{
          VALUES ?item {{ wd:{item_id} }}
          VALUES ?prop {{ wd:{prop} }}
          ?item wdt:{prop} ?value.
          SERVICE wikibase:label {{
            bd:serviceParam wikibase:language "{lang_code},[AUTO_LANGUAGE],en".
          }}
        }}
        """
    else:
        # property label is used
        prop_is_id = False
        query = f"""
        SELECT ?valueLabel ?itemLabel ?itemDescription ?p WHERE {{
          VALUES ?item {{ wd:{item_id} }}
          ?item ?prop ?value.
          ?p wikibase:directClaim ?prop;
            rdfs:label "{prop}"@{lang_code}.
          SERVICE wikibase:label {{
            bd:serviceParam wikibase:language "{lang_code},[AUTO_LANGUAGE],en".
          }}
        }}
        """

    result = query_wikidata(wtp, query)
    value = result.get("valueLabel", {}).get("value", "")
    save_statement_cache(
        wtp,
        item_id,
        result.get("itemLabel", {}).get("value", ""),
        result.get("itemDescription", {}).get("value", ""),
        prop
        if prop_is_id
        else result.get("p", {}).get("value", "").rsplit("/", 1)[-1],
        prop
        if not prop_is_id
        else result.get("propLabel", {}).get("value", ""),
        value,
    )
    if prop in {"P577", "publication date"}:
        if sys.version_info < (3, 11):
            value = value.removesuffix("Z")
        try:
            value = datetime.fromisoformat(value).year
        except ValueError:
            value = ""
    return value


def get_item_cache(wtp: "Wtp", item_id: str) -> Union[tuple[str, str], None]:
    for result in wtp.db_conn.execute(
        "SELECT label, description FROM wikidata_items WHERE id = ?",
        (item_id,),
    ):
        return result
    return None


def save_item_cache(
    wtp: "Wtp", item_id: str, item_label: str, item_desc: str
) -> None:
    with wtp.db_conn:
        wtp.db_conn.execute(
            """
            INSERT INTO wikidata_items (id, label, description)
            VALUES(?, ?, ?)
            """,
            (item_id, item_label, item_desc),
        )


def query_item(wtp: "Wtp", item_id: str, lang_code: str) -> tuple[str, str]:
    result = get_item_cache(wtp, item_id)
    if result is not None:
        return result
    query_result = query_wikidata(
        wtp,
        f"""
        SELECT ?itemLabel ?itemDescription WHERE {{
          VALUES ?item {{ wd:{item_id} }}.
          SERVICE wikibase:label {{
            bd:serviceParam
            wikibase:language "{lang_code},[AUTO_LANGUAGE],en".
          }}
        }}
        """
    )
    label = query_result.get("itemLabel", {}).get("value", "")
    desc = query_result.get("itemDescription", {}).get("value", "")
    save_item_cache(wtp, item_id, label, desc)
    return label, desc


def query_item_label(wtp: "Wtp", item_id: str) -> str:
    return query_item(wtp, item_id, wtp.lang_code)[0]


def query_item_desc(wtp: "Wtp", item_id: str) -> str:
    return query_item(wtp, item_id, wtp.lang_code)[1]
