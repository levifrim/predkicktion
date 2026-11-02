"""Fills kickbase.db from the Kickbase API.

    python gettrainingdata.py               # player performances, then match events
    python gettrainingdata.py --full        # same, but refetch every player's performances
    python gettrainingdata.py --events-only # only the match events that are still missing
    python gettrainingdata.py --events-only --sample 600  # a random sample, stratified by season and position

Performances are only fetched for players that are new or have a past fixture that is not finished
in the DB yet. Match events are resumable: (player, match) pairs already in player_match_fetches are
skipped, and a failed request is not saved, so the next run retries it.
"""
import argparse
import random
import time
import os
from datetime import datetime, timezone
import requests
import kickbaseService
from db import get_connection, init_db
from dotenv import load_dotenv

FIRST_KICKOFF = "2023-01-01"  # the player center has no events before the 2022/23 winter break
BUNDESLIGA_ID = "1"  # works for 2. and 3. Liga matches as well
PAUSE = 0.3
MAX_CONSECUTIVE_FAILURES = 20

# players whose performances are complete: upcoming fixtures are known and every past fixture of the
# latest season is finished. Old seasons are ignored, some of their games were never marked finished.
UP_TO_DATE_QUERY = """
SELECT player_id
FROM player_matchdays
GROUP BY player_id
HAVING SUM(kickoff >= :now) > 0
   AND SUM(kickoff < :now AND COALESCE(match_status, 0) != 2
           AND season = (SELECT MAX(season) FROM player_matchdays WHERE season LIKE '%/%')) = 0
"""

TODO_QUERY = """
SELECT pm.player_id, pm.match_id, pm.season, p.position
FROM player_matchdays pm
JOIN players p ON p.player_id = pm.player_id
LEFT JOIN player_match_fetches f ON f.player_id = pm.player_id AND f.match_id = pm.match_id
WHERE pm.kickoff >= ? AND pm.season LIKE '%/%' AND pm.minutes > 0 AND pm.match_status = 2 AND f.player_id IS NULL
"""


def bundesligaPlayerPerformances(service: kickbaseService.KickbaseService, full: bool = False):
    bundesliga_id = service.get_bundesliga_id()
    teams = service.get_all_teams(bundesliga_id)

    with get_connection() as connection:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        up_to_date = set() if full else {row[0] for row in connection.execute(UP_TO_DATE_QUERY, {"now": now})}
        skipped = 0

        for team in teams:
            connection.execute("INSERT OR REPLACE INTO teams (team_id, name) VALUES (?, ?)",
                               (team["tid"], team["tn"]))
            players = service.get_players_from_team(team["tid"], bundesliga_id)
            print(players)
            for player in players["it"]:
                connection.execute(
                    "INSERT OR REPLACE INTO players (player_id, name, team_id, position) VALUES (?, ?, ?, ?)",
                    (player["i"], player["n"], player["tid"], player["pos"]))
                if player["i"] in up_to_date:
                    skipped += 1
                    continue
                performances = service.get_performances(player["i"], bundesliga_id)
                for season in performances["it"]:
                    for match in season["ph"]:
                        minutes = int(match["mp"].rstrip("'")) if "mp" in match else None
                        connection.execute("""
                                INSERT OR REPLACE INTO player_matchdays
                                (player_id, season, day, match_id, kickoff,
                                home_team, away_team, home_goals, away_goals,
                                player_team, points, minutes, status, match_status)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                              (
                                  player["i"], season["ti"], match["day"], match.get("mi"),
                                  match.get("md"), match.get("t1"), match.get("t2"),
                                  match.get("t1g"), match.get("t2g"), match.get("pt"),
                                  match.get("p"), minutes, match.get("st"), match.get("mdst"),
                              ),
                        )
                time.sleep(0.3)
            connection.commit()
        print(f"skipped {skipped} players that were already up to date")


def store_event_types(service, connection):
    types = service.get_event_types()["it"]
    connection.executemany("INSERT OR REPLACE INTO event_types (type_id, name) VALUES (?, ?)",
                           [(t["i"], t["ti"]) for t in types])


def todo(connection, sample: int | None):
    rows = connection.execute(TODO_QUERY, (FIRST_KICKOFF,)).fetchall()
    if sample is None:
        return rows
    # same number per (season, position), random within each
    strata = {}
    for row in rows:
        strata.setdefault((row[2], row[3]), []).append(row)
    per_stratum = max(1, sample // len(strata))
    picked = []
    rng = random.Random(0)
    for group in strata.values():
        picked += rng.sample(group, min(per_stratum, len(group)))
    return picked


def fetch_match_events(service, player_id, match_id):
    """The player center response, or None if the request failed. A failure is retried once after
    logging in again, in case the token expired."""
    for attempt in range(2):
        try:
            data = service.get_match_events(player_id, match_id, BUNDESLIGA_ID)
            if "p" in data:  # every successful response carries the points total
                return data
        except (requests.RequestException, ValueError):
            pass
        if attempt == 0:
            try:
                service.authenticate()
            except Exception:
                return None
    return None


def crawl(service, connection, pairs):
    failed = consecutive = 0
    for n, (player_id, match_id, _, _) in enumerate(pairs, 1):
        data = fetch_match_events(service, player_id, match_id)
        if data is None:
            failed += 1
            consecutive += 1
            if consecutive >= MAX_CONSECUTIVE_FAILURES:
                print(f"stopping: {consecutive} requests in a row failed")
                break
            continue
        consecutive = 0
        events = data.get("events", [])
        connection.executemany("""
            INSERT OR REPLACE INTO player_match_events
            (event_id, player_id, match_id, type_id, points, minute, att, corrects)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [(e["ei"], player_id, match_id, e["eti"], e["p"], e.get("mt"), e.get("att"), e.get("cei"))
             for e in events])
        connection.execute(
            "INSERT OR REPLACE INTO player_match_fetches (player_id, match_id, points, events) VALUES (?, ?, ?, ?)",
            (player_id, match_id, data.get("p"), len(events)))
        if n % 50 == 0:
            connection.commit()
            print(f"{n}/{len(pairs)}")
        time.sleep(PAUSE)
    connection.commit()
    print(f"done, {failed} failed requests were not saved and will be retried on the next run")


def bundesligaMatchEvents(service: kickbaseService.KickbaseService, sample: int | None = None):
    """The per-event breakdown of every played match since January 2023 into player_match_events."""
    with get_connection() as connection:
        store_event_types(service, connection)
        pairs = todo(connection, sample)
        print(f"fetching {len(pairs)} player matches")
        crawl(service, connection, pairs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--events-only", action="store_true", help="skip the player performances")
    parser.add_argument("--full", action="store_true", help="refetch every player's performances")
    parser.add_argument("--sample", type=int, help="fetch only this many (player, match) pairs of match events")
    args = parser.parse_args()

    load_dotenv()
    service = kickbaseService.KickbaseService(
        "https://api.kickbase.com", os.getenv("KICKBASE_EMAIL"), os.getenv("KICKBASE_PASSWORD")
    )
    service.authenticate()
    init_db()
    if not args.events_only:
        bundesligaPlayerPerformances(service, args.full)
    bundesligaMatchEvents(service, args.sample)
