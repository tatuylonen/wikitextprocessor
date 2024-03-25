import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

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
    else:
        wtp.error(
            "WIKIDATA QUERY failed", f"{query=} {r.text=}", "query_wikidata"
        )
    return {}


@dataclass
class WikiDataItem:
    item_id: str = ""
    label: str = ""
    description: str = ""
    entity_data: str = ""


def init_wikidata_cache(wtp: "Wtp") -> None:
    wtp.db_conn.executescript(
        """
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS wikidata_items(
    id TEXT PRIMARY KEY,
    label TEXT,
    description TEXT,
    entity_data TEXT
    );

    CREATE TABLE IF NOT EXISTS wikidata_properties(
    id TEXT UNIQUE,
    label TEXT,
    datatype TEXT,
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

    CREATE TABLE IF NOT EXISTS wiki_articles(
        name TEXT,
        site_id TEXT,
        item_id TEXT,
        PRIMARY KEY(name, site_id, item_id),
        FOREIGN KEY(item_id) REFERENCES wikidata_items(id)
    );
    """
    )


def get_statement_cache(
    wtp: "Wtp", prop: str, item: str
) -> Optional[tuple[str, Optional[str]]]:
    query = """SELECT value, datatype FROM wikidata_property_values
    JOIN wikidata_items ON wikidata_property_values.item_id = wikidata_items.id
    JOIN wikidata_properties
      ON wikidata_property_values.property_id = wikidata_properties.id
    WHERE wikidata_items.id = ? AND """
    if re.fullmatch(r"P\d+", prop):
        query += "wikidata_property_values.property_id = ?"
    else:
        query += "wikidata_properties.label = ?"
    for data in wtp.db_conn.execute(query, (item, prop)):
        return data
    return None


def save_statement_cache(
    wtp: "Wtp",
    item_id: str,
    item_label: str,
    item_desc: str,
    prop_id: str,
    prop_label: str,
    prop_value: str,
    prop_type: Optional[str],
) -> None:
    with wtp.db_conn:
        insert_item(
            wtp,
            WikiDataItem(
                item_id=item_id, label=item_label, description=item_desc
            ),
        )
        wtp.db_conn.execute(
            """
            INSERT OR IGNORE INTO wikidata_properties (id, label, datatype)
            VALUES(?, ?, ?)
            """,
            (prop_id, prop_label, prop_type),
        )
        wtp.db_conn.execute(
            """
            INSERT INTO wikidata_property_values (value, item_id, property_id)
            VALUES(?, ?, ?);
            """,
            (prop_value, item_id, prop_id),
        )


def format_statement_result(
    value: str, datatype: Optional[str], prop: str
) -> str:
    if datatype == "http://www.w3.org/2001/XMLSchema#dateTime":
        # The date value will be formatted in day-month-year format.
        if sys.version_info < (3, 11):
            value = value.removesuffix("Z")
        try:
            date_time = datetime.fromisoformat(value)
            if prop in ("P577", "publication date"):
                value = str(date_time.year)
            else:
                value = date_time.strftime("%d %B %Y")
        except ValueError:
            value = ""
    return value


def statement_query(wtp: "Wtp", prop: str, item_id: str, lang_code: str) -> str:
    cache_value = get_statement_cache(wtp, prop, item_id)
    if cache_value is not None:
        return format_statement_result(cache_value[0], cache_value[1], prop)
    if re.fullmatch(r"P\d+", prop):
        prop_is_id = True
        query = f"""
        SELECT ?value ?itemLabel ?itemDescription ?propLabel
        WHERE {{
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
        SELECT ?value ?itemLabel ?itemDescription ?p WHERE {{
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
    value = result.get("value", {}).get("value", "")
    datatype = result.get("value", {}).get("datatype")
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
        datatype,
    )
    return format_statement_result(value, datatype, prop)


def get_item_cache(wtp: "Wtp", item_id: str) -> Optional[WikiDataItem]:
    for label, desc, entity_data in wtp.db_conn.execute(
        """
        SELECT label, description, entity_data
        FROM wikidata_items WHERE id = ?
        """,
        (item_id,),
    ):
        return WikiDataItem(
            item_id=item_id,
            label=label,
            description=desc,
            entity_data=entity_data,
        )
    return None


def insert_item(wtp: "Wtp", item: WikiDataItem) -> None:
    wtp.db_conn.execute(
        """
        INSERT OR IGNORE INTO wikidata_items
        (id, label, description, entity_data)
        VALUES(?, ?, ?, ?)
        """,
        (item.item_id, item.label, item.description, item.entity_data),
    )


def query_item(wtp: "Wtp", item_id: str, lang_code: str) -> WikiDataItem:
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
        """,
    )
    label = query_result.get("itemLabel", {}).get("value", "")
    desc = query_result.get("itemDescription", {}).get("value", "")
    wikidata_item = WikiDataItem(item_id=item_id, label=label, description=desc)
    with wtp.db_conn:
        insert_item(wtp, wikidata_item)
    return wikidata_item


def query_item_label(wtp: "Wtp", item_id: str) -> str:
    return query_item(wtp, item_id, wtp.lang_code).label


def query_item_desc(wtp: "Wtp", item_id: str) -> str:
    return query_item(wtp, item_id, wtp.lang_code).description


def get_entity_id_cache(wtp: "Wtp", title: str, site_id: str) -> Optional[str]:
    query = "SELECT item_id FROM wiki_articles WHERE name = ? AND site_id = ?"
    for (item_id,) in wtp.db_conn.execute(query, (title, site_id)):
        return item_id
    return "not found"


def save_entity_id_cache(
    wtp: "Wtp",
    title: str,
    site_id: str,
    item_id: Optional[str],
    item_label: str,
    item_desc: str,
) -> None:
    with wtp.db_conn:
        if item_id is not None:
            insert_item(
                wtp,
                WikiDataItem(
                    item_id=item_id, label=item_label, description=item_desc
                ),
            )
        wtp.db_conn.execute(
            """
            INSERT OR IGNORE INTO wiki_articles (name, site_id, item_id)
            VALUES (?, ?, ?)
            """,
            (title, site_id, item_id),
        )


def query_entity_id_for_title(
    wtp: "Wtp", title: str, site_id: str
) -> Optional[str]:
    cache = get_entity_id_cache(wtp, title, site_id)
    if cache != "not found":
        return cache
    if site_id is None or site_id == "":
        site_id = wtp.lang_code + wtp.project
    lang_code = site_id[:2]
    project = site_id[2:]
    if project == "wiki":
        project = "wikipedia"
    wiki_url = f"https://{lang_code}.{project}.org/"
    query_result = query_wikidata(
        wtp,
        f"""
        SELECT ?item ?itemLabel ?itemDescription WHERE {{
          ?url rdf:type schema:Article;
            schema:about ?item;
            schema:isPartOf <{wiki_url}>;
            schema:name "{title}"@{lang_code}.
          SERVICE wikibase:label {{
            bd:serviceParam
            wikibase:language "{lang_code},[AUTO_LANGUAGE],en".
          }}
        }}
        """,
    )
    item_id = query_result.get("item", {}).get("value")
    if item_id is not None:
        item_id = item_id.rsplit("/", 1)[-1]
    save_entity_id_cache(
        wtp,
        title,
        site_id,
        item_id,
        query_result.get("itemLabel", {}).get("value", ""),
        query_result.get("itemDescription", {}).get("value", ""),
    )
    return item_id


def get_entity_data(
    wtp: "Wtp", item_id: Optional[str]
) -> Optional[dict[str, Any]]:
    # https://www.mediawiki.org/wiki/Wikibase/DataModel
    # https://doc.wikimedia.org/Wikibase/master/php/docs_topics_json.html
    import requests

    if item_id is None:
        item_id = query_entity_id_for_title(wtp, wtp.title or "", "")
    if item_id is None:
        return None

    for (entity_data_str,) in wtp.db_conn.execute(
        "SELECT entity_data FROM wikidata_items WHERE id = ?", (item_id,)
    ):
        if entity_data_str is not None and len(entity_data_str) > 0:
            return json.loads(entity_data_str)

    r = requests.get(
        f"https://www.wikidata.org/wiki/Special:EntityData/{item_id}.json",
        headers={"user-agent": "wikitextprocessor"},
    )
    if r.ok:
        result = r.json()
        for _, entity_data in result.get("entities", {}).items():
            entity_data["schemaVersion"] = 2
            insert_item(
                wtp,
                WikiDataItem(
                    item_id=item_id,
                    label=entity_data.get("labels", {})
                    .get(wtp.lang_code, {})
                    .get("value", ""),
                    description=entity_data.get("descriptions", {})
                    .get(wtp.lang_code, {})
                    .get("value", ""),
                    entity_data=json.dumps(entity_data, ensure_ascii=False),
                ),
            )
            return entity_data

    return None


def mw_wikibase_getEntity(wtp: "Wtp", item_id: Optional[str]) -> Any:
    entity_data = get_entity_data(wtp, item_id)
    if entity_data is None or wtp.lua is None:
        return None
    return wtp.lua.table_from(entity_data)
