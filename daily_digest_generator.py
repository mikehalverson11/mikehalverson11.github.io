"""
Daily digest -> Notion page.

Sections: last night's scores, upcoming games, market snapshot, random dish.

Outputs (each is optional; set the env vars for the ones you want):
  Notion page   - NOTION_TOKEN + NOTION_PAGE_ID
  Website JSON  - DIGEST_JSON_PATH (e.g. digest.json); rendered by digest.html on the site.
                  Contains the same content as the Notion page.

Other env vars:
  FINNHUB_API_KEY     - free key from finnhub.io
"""
import json
import os
import random
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

# ----------------------------- CONFIG ---------------------------------
TZ = ZoneInfo("America/New_York")
UPCOMING_DAYS = 7
ARCHIVE_RETENTION_DAYS = 30  # archived digests older than this get moved to Notion trash

# league key -> (ESPN sport, ESPN league, [team names as ESPN displays them])
TEAMS = {
    "NBA": ("basketball", "nba", ["Sacramento Kings"]),
    "MLB": ("baseball", "mlb", ["Cleveland Guardians"]),
    "NFL": ("football", "nfl", ["San Francisco 49ers"]),
    "NHL": ("hockey", "nhl", ["San Jose Sharks"]),
}

# Weather location (Open-Meteo uses lat/lon). Change to your own.
WEATHER_LOCATION = {"name": "Cleveland Heights, OH", "lat": 41.52, "lon": -81.56}

# Weekly reminders: 0=Monday ... 6=Sunday. Edit freely.
REMINDERS = {
    0: ["Set Fantasy Basketball Lineup"],
    1: ["Fantasy Football Waivers Day"],
    3: ["Set Fantasy Football Lineup","Rec League Basketball"],
    6: ["Set Fantasy Football Lineup"],
}

# Days of the Month Reminder
DOM_REMINDERS= {
  1: ["Pay Rent"],
  2: ["Pay Rent"],
  3: ["Pay Rent"],
}

ON_THIS_DAY_COUNT = 3

# New music from artists you scrobble on Last.fm (needs LASTFM_API_KEY + LASTFM_USER secrets)
LASTFM_LOOKBACK_DAYS = 730     # build your artist list from the last N days of listening (730 = 2 years)
LASTFM_TOP_ARTISTS = 200       # ...and watch your top N artists from that window
LASTFM_FALLBACK_PERIOD = "12month"  # used only if the date-range lookup fails
NEW_MUSIC_LOOKBACK_DAYS = 14   # show releases from the last N days...
NEW_MUSIC_AHEAD_DAYS = 14      # ...and announced ones coming in the next N days
NEW_MUSIC_NOTIFY_DAYS = 2      # phone alert for releases this recent
NEW_MUSIC_MAX_NAME_LOOKUPS = 60  # cap on slow by-name artist lookups (1 per ~second each)

# Book you're currently reading -> used to find a related scholarly article.
# Update these when you start a new book. extra_keywords are optional topics.
CURRENT_BOOK = {
    "title": "Prisoner of Love",
    "author": "Jean Genet",
    "extra_keywords": "",
}

INDEXES = {"S&P 500 (SPY)": "SPY", "Nasdaq 100 (QQQ)": "QQQ", "Dow (DIA)": "DIA"}
WATCHLIST = ["AAPL", "VOO", "NVDA"]

DISH_CATEGORIES = [
    "Category:Soups", "Category:Stews", "Category:Salads",
    "Category:Street_food", "Category:Casseroles", "Category:Sandwiches",
    "Category:Pasta_dishes", "Category:Rice_dishes", "Category:Noodle_dishes",
    "Category:Dumplings", "Category:Curries", "Category:Main_courses",
]

HEADERS = {"User-Agent": "daily-digest/0.1 (personal project)"}


def _require(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(
            f"Missing secret/env var {name}. In GitHub: Settings > Secrets and variables > "
            f"Actions > New repository secret (the name must match exactly)."
        )
    return value


def _clean_page_id(raw):
    """Accept a bare ID, a dashed ID, or a full Notion URL; return the 32-char ID."""
    raw = raw.split("?")[0]
    match = re.search(r"([0-9a-fA-F]{32})(?!.*[0-9a-fA-F]{32})", raw.replace("-", ""))
    if not match:
        raise SystemExit("NOTION_PAGE_ID doesn't contain a valid 32-character page ID.")
    return match.group(1)


NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "").strip()          # optional: Notion output
_raw_page_id = os.environ.get("NOTION_PAGE_ID", "").strip()
NOTION_PAGE_ID = _clean_page_id(_raw_page_id) if _raw_page_id else ""
DIGEST_JSON_PATH = os.environ.get("DIGEST_JSON_PATH", "").strip()  # optional: website output
FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "")
LASTFM_KEY = os.environ.get("LASTFM_API_KEY", "")      # optional: new-music section
LASTFM_USER = os.environ.get("LASTFM_USER", "")
MUSICBRAINZ_CONTACT = os.environ.get("MUSICBRAINZ_CONTACT", "personal project")  # an email is polite
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")        # optional: phone push via ntfy.sh
NOTION_USER_ID = os.environ.get("NOTION_USER_ID", "")  # optional: @-mention yourself on the page


# ------------------------- NOTION BLOCK HELPERS -----------------------
def _rich(text):
    return [{"type": "text", "text": {"content": text[:2000]}}]


def heading(text):
    return {"object": "block", "type": "heading_2", "heading_2": {"rich_text": _rich(text)}}


def paragraph(text):
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": _rich(text)}}


def bullet(text):
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": _rich(text)},
    }


def divider():
    return {"object": "block", "type": "divider", "divider": {}}


def image(url):
    return {
        "object": "block",
        "type": "image",
        "image": {"type": "external", "external": {"url": url}},
    }


def linked_paragraph(label, url):
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {"content": label[:2000], "link": {"url": url}}}]},
    }


def todo(text):
    return {"object": "block", "type": "to_do", "to_do": {"rich_text": _rich(text), "checked": False}}


# ------------------------------ SPORTS --------------------------------
def espn_events(sport, league, dates):
    url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard"
    r = requests.get(url, params={"dates": dates, "limit": 300}, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json().get("events", [])


def involves_team(event, names):
    comp = event["competitions"][0]["competitors"]
    return any(c["team"]["displayName"] in names for c in comp)


def sports_blocks():
    now = datetime.now(TZ)
    yesterday = (now - timedelta(days=1)).strftime("%Y%m%d")

    results, notes = [], []
    upcoming, seen = [], set()
    for label, (sport, league, names) in TEAMS.items():
        # Last night's finals
        try:
            for e in espn_events(sport, league, yesterday):
                if involves_team(e, names) and e["status"]["type"]["state"] == "post":
                    comps = e["competitions"][0]["competitors"]
                    away = next(c for c in comps if c["homeAway"] == "away")
                    home = next(c for c in comps if c["homeAway"] == "home")
                    results.append(
                        f"[{label}] {away['team']['displayName']} {away['score']} @ "
                        f"{home['team']['displayName']} {home['score']}  ({e['status']['type']['shortDetail']})"
                    )
        except Exception as exc:
            notes.append(f"[{label}] results unavailable ({exc})")

        # Upcoming games: one request per day (ESPN rejected the multi-day range form)
        failures, last_exc = 0, None
        for offset in range(UPCOMING_DAYS + 1):
            day = (now + timedelta(days=offset)).strftime("%Y%m%d")
            try:
                events = espn_events(sport, league, day)
            except Exception as exc:
                failures, last_exc = failures + 1, exc
                continue
            for e in events:
                if (
                    involves_team(e, names)
                    and e["status"]["type"]["state"] == "pre"
                    and e["id"] not in seen
                ):
                    seen.add(e["id"])
                    when = datetime.fromisoformat(e["date"].replace("Z", "+00:00")).astimezone(TZ)
                    upcoming.append((when, f"[{label}] {e['name']}  - {when:%a %b %d, %I:%M %p}"))
        if failures == UPCOMING_DAYS + 1:
            notes.append(f"[{label}] schedule unavailable ({last_exc})")

    upcoming.sort(key=lambda x: x[0])
    blocks = [heading("Last night")]
    blocks += [bullet(r) for r in results] or [paragraph("No games for your teams last night.")]
    blocks += [heading("Coming up")]
    blocks += [bullet(t) for _, t in upcoming[:12]] or [paragraph("Nothing scheduled this week.")]
    blocks += [paragraph(n) for n in notes]
    return blocks


# ------------------------------ MARKETS -------------------------------
def finnhub(path, **params):
    params["token"] = FINNHUB_KEY
    r = requests.get(f"https://finnhub.io/api/v1/{path}", params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def quote_line(name, symbol):
    q = finnhub("quote", symbol=symbol)
    if not q.get("c"):
        return f"{name}: no data"
    arrow = "▲" if q["d"] >= 0 else "▼"
    return f"{name}: {q['c']:.2f}  {arrow} {q['d']:+.2f} ({q['dp']:+.2f}%)"


def market_blocks():
    blocks = [heading("Markets")]
    try:
        for name, sym in INDEXES.items():
            blocks.append(bullet(quote_line(name, sym)))
        blocks.append(paragraph("Watchlist"))
        for sym in WATCHLIST:
            blocks.append(bullet(quote_line(sym, sym)))

        today = datetime.now(TZ).date()
        cal = finnhub(
            "calendar/earnings",
            **{"from": today.isoformat(), "to": (today + timedelta(days=7)).isoformat()},
        )
        mine = [e for e in cal.get("earningsCalendar", []) if e.get("symbol") in WATCHLIST]
        if mine:
            blocks.append(paragraph("Upcoming earnings"))
            for e in sorted(mine, key=lambda x: x["date"]):
                blocks.append(bullet(f"{e['symbol']} reports {e['date']}"))
    except Exception as exc:
        blocks.append(paragraph(f"Market data unavailable ({exc})"))
    return blocks


# ------------------------------ WIKIPEDIA -----------------------------
def wiki_members(category, member_type):
    r = requests.get(
        "https://en.wikipedia.org/w/api.php",
        params={
            "action": "query", "list": "categorymembers", "cmtitle": category,
            "cmtype": member_type, "cmlimit": 500, "format": "json",
        },
        headers=HEADERS, timeout=20,
    )
    r.raise_for_status()
    return [m["title"] for m in r.json().get("query", {}).get("categorymembers", [])]


# Wikipedia categories / summaries containing these words are not dishes
# (companies, brands, restaurants, people, media, etc.).
NOT_DISH = re.compile(
    r"compan|brand|restaurant|business|establishment|manufactur|chain|cookbook|festival|"
    r"museum|people|births|deaths|chefs?\b|films?\b|television|album|magazine|organi[sz]ation|"
    r"stores?\b|retail|caf[eé]s|bakeries|supermarket|cookware|utensil|appliance|equipment|"
    r"lists?\b|awards?|competition|surname|given name|disambiguation|"
    r"brewer|distiller|winer|\bwines?\b|beer|spirits|liqueur|cocktail",
    re.IGNORECASE,
)
NOT_DISH_SUMMARY = re.compile(
    r"\b(company|brand|manufacturer|corporation|restaurant chain|chain of|franchise|"
    r"headquartered|founded in|enterprise|retailer|supermarket|village|town|surname)\b",
    re.IGNORECASE,
)


def find_dish_title(max_depth=3, attempts=10):
    """Walk down a food category tree until we land on a page."""
    for _ in range(attempts):
        category = random.choice(DISH_CATEGORIES)
        for _depth in range(max_depth + 1):
            pages = [t for t in wiki_members(category, "page")
                     if not NOT_DISH.search(t) and not t.startswith(("Index of",))]
            subcats = [c for c in wiki_members(category, "subcat") if not NOT_DISH.search(c)]
            if pages and (not subcats or random.random() < 0.6):
                return random.choice(pages)
            if not subcats:
                break
            category = random.choice(subcats)
    raise RuntimeError("no dish pages found after several tries")


def looks_like_dish(title, summary):
    """Reject companies, brands, people, etc. using the page's own categories and summary."""
    text = f"{summary.get('description', '')} {summary.get('extract', '')[:300]}"
    if NOT_DISH_SUMMARY.search(text):
        return False
    r = requests.get(
        "https://en.wikipedia.org/w/api.php",
        params={
            "action": "query", "prop": "categories", "titles": title,
            "cllimit": "max", "clshow": "!hidden", "format": "json",
        },
        headers=HEADERS, timeout=20,
    )
    r.raise_for_status()
    for page in r.json().get("query", {}).get("pages", {}).values():
        for cat in page.get("categories", []):
            if NOT_DISH.search(cat["title"]):
                return False
    return True


def dish_blocks():
    blocks = [heading("Random dish")]
    try:
        data = None
        for _ in range(8):  # keep trying until a candidate passes the dish check
            title = find_dish_title()
            s = requests.get(
                "https://en.wikipedia.org/api/rest_v1/page/summary/"
                + requests.utils.quote(title.replace(" ", "_"), safe=""),
                headers=HEADERS, timeout=20,
            )
            s.raise_for_status()
            candidate = s.json()
            if candidate.get("type") == "disambiguation":
                continue
            if looks_like_dish(title, candidate):
                data = candidate
                break
        if data is None:
            raise RuntimeError("couldn't find a dish page that passed the filters")
        if data.get("thumbnail", {}).get("source"):
            blocks.append(image(data["thumbnail"]["source"]))
        blocks.append(paragraph(data["title"]))
        blocks.append(paragraph(data.get("extract", "")))
        blocks.append(paragraph(data["content_urls"]["desktop"]["page"]))
    except Exception as exc:
        blocks.append(paragraph(f"Couldn't fetch a dish today ({exc})"))
    return blocks


# ------------------------------ REMINDERS -----------------------------
def todays_tasks(now):
    """Weekday + day-of-month reminders, as a fresh list (never mutates the config)."""
    return list(REMINDERS.get(now.weekday(), [])) + list(DOM_REMINDERS.get(now.day, []))


def reminder_blocks(now):
    tasks = todays_tasks(now)
    if not tasks:
        return []
    return [heading("Today's reminders")] + [todo(t) for t in tasks] + [divider()]


# ------------------------------ WEATHER -------------------------------
WMO = {
    0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Freezing fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    56: "Freezing drizzle", 57: "Heavy freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain",
    66: "Freezing rain", 67: "Heavy freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Light showers", 81: "Showers", 82: "Heavy showers",
    85: "Snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Severe thunderstorm with hail",
}


def weather_blocks():
    blocks = [heading(f"Weather - {WEATHER_LOCATION['name']}")]
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": WEATHER_LOCATION["lat"],
                "longitude": WEATHER_LOCATION["lon"],
                "current": "temperature_2m,apparent_temperature,weather_code",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                         "precipitation_probability_max,wind_speed_10m_max",
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
                "timezone": str(TZ),
                "forecast_days": 1,
            },
            headers=HEADERS, timeout=20,
        )
        r.raise_for_status()
        d = r.json()
        cur, day = d["current"], d["daily"]
        blocks.append(paragraph(
            f"Now: {cur['temperature_2m']:.0f}F (feels {cur['apparent_temperature']:.0f}F), "
            f"{WMO.get(cur['weather_code'], 'n/a')}"
        ))
        blocks.append(paragraph(
            f"Today: {WMO.get(day['weather_code'][0], 'n/a')}, "
            f"high {day['temperature_2m_max'][0]:.0f}F / low {day['temperature_2m_min'][0]:.0f}F, "
            f"{day['precipitation_probability_max'][0]}% chance of precipitation, "
            f"wind up to {day['wind_speed_10m_max'][0]:.0f} mph"
        ))
    except Exception as exc:
        blocks.append(paragraph(f"Weather unavailable ({exc})"))
    return blocks


# ------------------------------ ON THIS DAY ---------------------------
def history_blocks(now):
    blocks = [heading("This day in history")]
    try:
        r = requests.get(
            f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{now:%m}/{now:%d}",
            headers=HEADERS, timeout=20,
        )
        r.raise_for_status()
        events = r.json()["events"]
        for e in sorted(random.sample(events, min(ON_THIS_DAY_COUNT, len(events))), key=lambda x: x["year"]):
            blocks.append(bullet(f"{e['year']}: {e['text']}"))
    except Exception as exc:
        blocks.append(paragraph(f"History unavailable ({exc})"))
    return blocks


# ------------------------------ BOOK ARTICLE --------------------------
def _crossref(query, extra_filter=""):
    r = requests.get(
        "https://api.crossref.org/works",
        params={
            "query.bibliographic": query,
            "filter": "type:journal-article,has-abstract:true" + extra_filter,
            "rows": 10,
            "select": "title,author,container-title,issued,DOI,URL,abstract",
        },
        headers=HEADERS, timeout=25,
    )
    r.raise_for_status()
    return r.json()["message"]["items"]


def article_blocks():
    blocks = [heading("Reading: related article")]
    book = CURRENT_BOOK
    if book["title"] == "Your Book Title":
        return blocks + [paragraph("Set CURRENT_BOOK in the script to get a related article.")]
    try:
        query = f"{book['title']} {book['author']} {book['extra_keywords']}".strip()
        # Prefer items with JSTOR DOIs (prefix 10.2307); fall back to any journal article.
        items = _crossref(query, ",prefix:10.2307") or _crossref(query)
        items = [i for i in items if i.get("title")]
        if not items:
            return blocks + [paragraph(f"No related article found for {book['title']}.")]
        item = random.choice(items[:5])

        title = item["title"][0]
        authors = ", ".join(
            f"{a.get('given', '')} {a.get('family', '')}".strip() for a in item.get("author", [])[:3]
        ) or "Unknown author"
        journal = (item.get("container-title") or [""])[0]
        year = (item.get("issued", {}).get("date-parts") or [[None]])[0][0]
        abstract = re.sub(r"<[^>]+>", "", item.get("abstract", "")).strip()
        doi = item["DOI"]
        url = (
            "https://www.jstor.org/stable/" + doi.split("/", 1)[1]
            if doi.startswith("10.2307/")
            else f"https://doi.org/{doi}"
        )

        blocks.append(paragraph(f"Because you're reading {book['title']} by {book['author']}:"))
        blocks.append(linked_paragraph(title, url))
        blocks.append(paragraph(f"{authors} - {journal} ({year})"))
        if abstract:
            blocks.append(paragraph(abstract[:600] + ("..." if len(abstract) > 600 else "")))
    except Exception as exc:
        blocks.append(paragraph(f"Article lookup unavailable ({exc})"))
    return blocks


# ------------------------------ NEW MUSIC -----------------------------
SKIP_SECONDARY = {"compilation", "live", "remix", "dj-mix", "demo", "interview", "spokenword"}
MB_BATCH = 15  # artists per MusicBrainz query


def _mb_get(path, **params):
    """MusicBrainz GET with ~1 req/sec pacing and retries on 429/502/503/504."""
    last = None
    for attempt in range(4):
        time.sleep(1.1)  # MusicBrainz allows ~1 request/second
        r = requests.get(
            f"https://musicbrainz.org/ws/2/{path}",
            params={**params, "fmt": "json"},
            headers={"User-Agent": f"daily-digest/0.1 ({MUSICBRAINZ_CONTACT})"},
            timeout=30,
        )
        if r.status_code in (429, 502, 503, 504):
            last = r
            try:
                wait = int(r.headers.get("Retry-After", 0))
            except (TypeError, ValueError):
                wait = 0
            time.sleep(min(wait or 4 * 2 ** attempt, 30))  # 4s, 8s, 16s, 32s (capped at 30)
            continue
        r.raise_for_status()
        return r.json()
    last.raise_for_status()


def _lastfm(method, **params):
    r = requests.get(
        "https://ws.audioscrobbler.com/2.0/",
        params={"method": method, "user": LASTFM_USER, "api_key": LASTFM_KEY, "format": "json", **params},
        headers=HEADERS, timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(data.get("message", "Last.fm error"))
    return data


def lastfm_top_artists():
    """Top artists by plays over the last LASTFM_LOOKBACK_DAYS, as [(name, mbid)]."""
    try:
        end = int(time.time())
        start = end - LASTFM_LOOKBACK_DAYS * 86400
        chart = _lastfm("user.getweeklyartistchart", **{"from": start, "to": end})
        artists = chart.get("weeklyartistchart", {}).get("artist", [])
        if isinstance(artists, dict):  # a single result comes back as an object, not a list
            artists = [artists]
        if artists:
            artists.sort(key=lambda a: int(a.get("playcount", 0)), reverse=True)
            return [(a["name"], a.get("mbid", "")) for a in artists[:LASTFM_TOP_ARTISTS]]
    except Exception as exc:
        print(f"Last.fm date-range lookup failed ({exc}); falling back to period={LASTFM_FALLBACK_PERIOD}")
    data = _lastfm("user.gettopartists", period=LASTFM_FALLBACK_PERIOD, limit=LASTFM_TOP_ARTISTS)
    return [(a["name"], a.get("mbid", "")) for a in data["topartists"]["artist"]]


def new_music_blocks(now):
    """Returns (blocks, fresh) where fresh = very recent releases worth a phone alert."""
    blocks = [heading("New music from your artists")]
    fresh = []
    if not (LASTFM_KEY and LASTFM_USER):
        return blocks + [paragraph("Add LASTFM_API_KEY and LASTFM_USER secrets to enable this section.")], fresh
    try:
        id_to_name, lookups, skipped, lookup_failures = {}, 0, 0, 0
        for name, mbid in lastfm_top_artists():  # already ordered most-played first
            if not mbid:  # Last.fm doesn't always know the MusicBrainz ID; look it up by name
                if lookups >= NEW_MUSIC_MAX_NAME_LOOKUPS:
                    skipped += 1
                    continue
                lookups += 1
                try:
                    hits = _mb_get("artist", query=f'artist:"{name}"', limit=1).get("artists", [])
                except Exception:
                    lookup_failures += 1
                    skipped += 1
                    if lookup_failures >= 3:  # MusicBrainz is struggling; stop making slow lookups
                        lookups = NEW_MUSIC_MAX_NAME_LOOKUPS
                    continue
                if hits and hits[0].get("score", 0) >= 95 and hits[0]["name"].lower() == name.lower():
                    mbid = hits[0]["id"]
            if mbid:
                id_to_name[mbid] = name

        today = now.date()
        start = (today - timedelta(days=NEW_MUSIC_LOOKBACK_DAYS)).isoformat()
        end = (today + timedelta(days=NEW_MUSIC_AHEAD_DAYS)).isoformat()
        notify_from = (today - timedelta(days=NEW_MUSIC_NOTIFY_DAYS)).isoformat()

        found = {}
        ids = list(id_to_name)
        batches = failed_batches = 0
        for i in range(0, len(ids), MB_BATCH):
            artist_clause = " OR ".join(f"arid:{m}" for m in ids[i:i + MB_BATCH])
            query = (
                f"({artist_clause}) AND firstreleasedate:[{start} TO {end}] "
                "AND (primarytype:album OR primarytype:ep OR primarytype:single)"
            )
            batches += 1
            try:
                groups = _mb_get("release-group", query=query, limit=100).get("release-groups", [])
            except Exception:
                failed_batches += 1
                continue
            for rg in groups:
                secondary = {t.lower() for t in rg.get("secondary-types", [])}
                date = rg.get("first-release-date", "")
                if secondary & SKIP_SECONDARY or len(date) != 10:
                    continue
                artist = "".join(c.get("name", "") + c.get("joinphrase", "") for c in rg.get("artist-credit", []))
                found[rg["id"]] = (date, artist, rg["title"], rg.get("primary-type", ""))

        releases = sorted(found.items(), key=lambda kv: kv[1][0], reverse=True)
        for rg_id, (date, artist, title, kind) in releases:
            upcoming = date > today.isoformat()
            label = f"{artist} - {title}"
            tag = f" ({kind}{', out ' + date if upcoming else ''})" if kind else ""
            blocks.append({
                "object": "block", "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [
                    {"type": "text", "text": {"content": f"{date}  "}},
                    {"type": "text", "text": {"content": label[:1800], "link": {"url": f"https://musicbrainz.org/release-group/{rg_id}"}}},
                    {"type": "text", "text": {"content": tag}},
                ]},
            })
            if notify_from <= date <= today.isoformat():
                fresh.append(label)
        if not releases and not failed_batches:
            blocks.append(paragraph(f"Nothing new from the {len(id_to_name)} artists being watched lately."))
        if failed_batches:
            blocks.append(paragraph(
                f"(MusicBrainz was unavailable for {failed_batches} of {batches} checks, so some artists were not covered today.)"
            ))
        if skipped:
            blocks.append(paragraph(f"({skipped} lower-ranked artists skipped; couldn't be matched without a slow lookup.)"))
    except Exception as exc:
        blocks.append(paragraph(f"New music lookup unavailable ({exc})"))
    return blocks, fresh


# ------------------------------ WEBSITE JSON --------------------------
_KIND = {"heading_2": "heading", "paragraph": "paragraph", "bulleted_list_item": "bullet", "to_do": "todo"}


def blocks_to_json(blocks):
    """Flatten the Notion-style blocks into simple JSON the website can render."""
    out = []
    for b in blocks:
        t = b["type"]
        if t == "divider":
            out.append({"type": "divider"})
        elif t == "image":
            out.append({"type": "image", "url": b["image"]["external"]["url"]})
        elif t in _KIND:
            parts = []
            for rt in b[t]["rich_text"]:
                if rt.get("type") != "text":
                    continue
                part = {"text": rt["text"]["content"]}
                if rt["text"].get("link"):
                    part["url"] = rt["text"]["link"]["url"]
                parts.append(part)
            out.append({"type": _KIND[t], "parts": parts})
    return out


def write_site_json(path, blocks, now):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    payload = {"generated": now.isoformat(timespec="seconds"), "blocks": blocks_to_json(blocks)}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"Wrote {path}")


# ------------------------------ NOTION --------------------------------
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}


ARCHIVE_TITLE = "Digest Archive"


def list_children(block_id):
    out, cursor = [], None
    while True:
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        r = requests.get(
            f"https://api.notion.com/v1/blocks/{block_id}/children",
            headers=NOTION_HEADERS, params=params, timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        out += data["results"]
        if not data.get("has_more"):
            return out
        cursor = data["next_cursor"]


def clear_page(page_id):
    """Delete the old digest blocks, but never child pages (that's your archive)."""
    for b in list_children(page_id):
        if b["type"] == "child_page":
            continue
        requests.delete(
            f"https://api.notion.com/v1/blocks/{b['id']}", headers=NOTION_HEADERS, timeout=20
        ).raise_for_status()


def write_page(page_id, blocks):
    for i in range(0, len(blocks), 100):  # Notion caps at 100 blocks per request
        r = requests.patch(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            headers=NOTION_HEADERS, json={"children": blocks[i:i + 100]}, timeout=30,
        )
        r.raise_for_status()


def create_subpage(parent_id, title, blocks=None):
    """Create a child page (first 100 blocks inline, the rest appended). Returns its id."""
    blocks = blocks or []
    r = requests.post(
        "https://api.notion.com/v1/pages",
        headers=NOTION_HEADERS, timeout=30,
        json={
            "parent": {"page_id": parent_id},
            "properties": {"title": {"title": _rich(title)}},
            "children": blocks[:100],
        },
    )
    r.raise_for_status()
    page_id = r.json()["id"]
    if len(blocks) > 100:
        write_page(page_id, blocks[100:])
    return page_id


def ensure_archive_page(page_id):
    """Find (or create) the 'Digest Archive' container page under the digest page."""
    for b in list_children(page_id):
        if b["type"] == "child_page" and b["child_page"]["title"] == ARCHIVE_TITLE:
            return b["id"]
    return create_subpage(page_id, ARCHIVE_TITLE)


def archive_digest(archive_id, blocks, date_label):
    """Save today's digest as a dated subpage; replace it if re-run the same day."""
    title = f"Digest - {date_label}"
    for b in list_children(archive_id):
        if b["type"] == "child_page" and b["child_page"]["title"] == title:
            requests.patch(
                f"https://api.notion.com/v1/pages/{b['id']}",
                headers=NOTION_HEADERS, json={"archived": True}, timeout=20,
            ).raise_for_status()
    create_subpage(archive_id, title, blocks)


def prune_archive(archive_id):
    """Move archived digests older than ARCHIVE_RETENTION_DAYS to Notion's trash."""
    cutoff = datetime.now(TZ) - timedelta(days=ARCHIVE_RETENTION_DAYS)
    removed = 0
    for b in list_children(archive_id):
        if b["type"] != "child_page":
            continue
        created = datetime.fromisoformat(b["created_time"].replace("Z", "+00:00"))
        if created < cutoff:
            requests.patch(
                f"https://api.notion.com/v1/pages/{b['id']}",
                headers=NOTION_HEADERS, json={"archived": True}, timeout=20,
            ).raise_for_status()
            removed += 1
    return removed


# ------------------------------ NOTIFICATIONS -------------------------
def notify(now, page_id, fresh=()):
    """Optional alerts. Each channel is skipped unless its env var is set."""
    tasks = todays_tasks(now)
    message = f"Your digest for {now:%a %b %d} is ready."
    if tasks:
        message += " Today: " + "; ".join(tasks)
    if fresh:
        message += " New music: " + "; ".join(list(fresh)[:5])
    page_url = "https://www.notion.so/" + page_id.replace("-", "")

    if NTFY_TOPIC:
        try:
            requests.post(
                f"https://ntfy.sh/{NTFY_TOPIC}",
                data=message.encode("utf-8"),
                headers={"Title": "Daily digest updated", "Click": page_url},
                timeout=15,
            ).raise_for_status()
        except Exception as exc:
            print(f"ntfy notification failed: {exc}")

    if NOTION_USER_ID:
        try:
            requests.post(
                "https://api.notion.com/v1/comments",
                headers=NOTION_HEADERS, timeout=20,
                json={
                    "parent": {"page_id": page_id},
                    "rich_text": [
                        {"type": "mention", "mention": {"user": {"id": NOTION_USER_ID}}},
                        {"type": "text", "text": {"content": f" {message}"}},
                    ],
                },
            ).raise_for_status()
        except Exception as exc:
            print(f"Notion mention failed: {exc}")


def diagnose_access():
    """On a 404, print the pages this integration can actually see."""
    print("\nNotion returned 404 for NOTION_PAGE_ID.")
    print("Most likely the page isn't shared with your integration: open the page in Notion,")
    print("click the ... menu > Connections, and add your integration.\n")
    try:
        r = requests.post(
            "https://api.notion.com/v1/search",
            headers=NOTION_HEADERS, timeout=20,
            json={"filter": {"property": "object", "value": "page"}, "page_size": 20},
        )
        r.raise_for_status()
        pages = r.json()["results"]
        if not pages:
            print("The integration can't see ANY pages yet, so nothing has been shared with it.")
            return
        print("Pages this integration can access (id  |  title):")
        for pg in pages:
            title = "(untitled)"
            for prop in pg.get("properties", {}).values():
                if prop.get("type") == "title" and prop.get("title"):
                    title = prop["title"][0]["plain_text"]
            print(f"  {pg['id'].replace('-', '')}  |  {title}")
        print("\nUse the id of your digest page as NOTION_PAGE_ID.")
    except Exception as exc:
        print(f"(Could not list accessible pages: {exc})")


def main():
    if not DIGEST_JSON_PATH and not (NOTION_TOKEN and NOTION_PAGE_ID):
        raise SystemExit(
            "Nothing to write to. Set DIGEST_JSON_PATH (website) and/or NOTION_TOKEN + NOTION_PAGE_ID (Notion)."
        )

    now = datetime.now(TZ)
    header = [paragraph(f"Daily digest for {now:%A, %B %d, %Y}"), divider()]
    reminders = reminder_blocks(now)
    body = weather_blocks() + [divider()]
    body += sports_blocks() + [divider()]
    body += market_blocks() + [divider()]
    body += history_blocks(now) + [divider()]
    music_blocks, fresh_music = new_music_blocks(now)
    body += music_blocks + [divider()]
    body += article_blocks() + [divider()]
    body += dish_blocks()

    blocks = header + reminders + body  # identical content for Notion and the website

    if DIGEST_JSON_PATH:
        write_site_json(DIGEST_JSON_PATH, blocks, now)

    if NOTION_TOKEN and NOTION_PAGE_ID:
        # Create the archive container first so it stays at the top of the page
        # (new content is appended below it).
        try:
            archive_id = ensure_archive_page(NOTION_PAGE_ID)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                diagnose_access()
                raise SystemExit(1)
            raise

        clear_page(NOTION_PAGE_ID)
        write_page(NOTION_PAGE_ID, blocks)
        archive_digest(archive_id, blocks, now.strftime("%Y-%m-%d"))
        try:
            removed = prune_archive(archive_id)
        except Exception as exc:  # pruning is housekeeping; don't fail the run
            removed = f"failed ({exc})"
        print(f"Digest updated and archived. Pruned: {removed}")
        notify(now, NOTION_PAGE_ID, fresh_music)


if __name__ == "__main__":
    main()
