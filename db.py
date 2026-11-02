import _sqlite3
import sqlite3

DB_PATH = "kickbase.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    team_id   TEXT PRIMARY KEY,
    name      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS players (
    player_id TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    team_id   TEXT REFERENCES teams(team_id),
    position  INTEGER              -- 1=GK 2=DEF 3=MID 4=FWD (I think)
);

CREATE TABLE IF NOT EXISTS player_matchdays (
    player_id    TEXT NOT NULL REFERENCES players(player_id),
    season       TEXT NOT NULL,  
    day          INTEGER NOT NULL,
    match_id     TEXT,
    kickoff      TEXT,        
    home_team    TEXT,
    away_team    TEXT,
    home_goals   INTEGER,
    away_goals   INTEGER,
    player_team  TEXT,
    points       INTEGER,       
    minutes      INTEGER,       
    status       INTEGER,
    match_status INTEGER,          
    PRIMARY KEY (player_id, season, day)
);

CREATE TABLE IF NOT EXISTS event_types (
    type_id   INTEGER PRIMARY KEY,
    name      TEXT NOT NULL      -- ids change between seasons, names stay the same
);

-- every scoring event of a player in a match (player center, available from January 2023)
CREATE TABLE IF NOT EXISTS player_match_events (
    event_id   TEXT PRIMARY KEY,
    player_id  TEXT NOT NULL REFERENCES players(player_id),
    match_id   TEXT NOT NULL,
    type_id    INTEGER NOT NULL,
    points     INTEGER NOT NULL,
    minute     INTEGER,
    att        INTEGER,          -- unknown meaning
    corrects   TEXT              -- event_id this one corrects (reverses or re-applies)
);

-- one row per fetched (player, match), also when it returned no events
CREATE TABLE IF NOT EXISTS player_match_fetches (
    player_id  TEXT NOT NULL,
    match_id   TEXT NOT NULL,
    points     INTEGER,          -- total according to the player center
    events     INTEGER NOT NULL,
    PRIMARY KEY (player_id, match_id)
);
"""

def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection

def init_db():
    with get_connection() as connection:
        connection.executescript(SCHEMA)

if __name__ == "__main__":
    init_db()
    print(DB_PATH)