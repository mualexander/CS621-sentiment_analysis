"""Project-wide constants for the CFP 24-team expansion sentiment study.

Every timestamp is timezone-aware UTC. YouTube's API returns UTC ("...Z") too.
"""
from datetime import datetime, timezone
from pathlib import Path

# --- Event -----------------------------------------------------------------
# The official CFP release is stamped "11/9/2026 10:30:00 AM" with no timezone:
# https://collegefootballplayoff.com/news/2026/11/9/24-team-expansion
# We use 10:30 ET (15:30 UTC), the earliest time it could have been.
# ANNOUNCE_UTC_ALT (10:30 CT) is there for a sensitivity check.
ANNOUNCE_UTC = datetime(2026, 11, 9, 15, 30, tzinfo=timezone.utc)
ANNOUNCE_UTC_ALT = datetime(2026, 11, 9, 16, 30, tzinfo=timezone.utc)

# Earlier leak (ESPN/Thamel "handshake agreement" reports). This is context
# only, so the pre-period is not news-free.
LEAK_UTC = datetime(2026, 10, 15, 0, 0, tzinfo=timezone.utc)

# --- Channels --------------------------------------------------------------
CHANNELS = {
    "pate": {
        "id": "UCg-q_MDeWQrjizr1VPLEpYg",
        "name": "Josh Pate's College Football Show",
    },
    # Replaced Greg McElroy on 2026-11-14. His @alwayscollegefootball channel
    # (UCHBNQtblfF6g79oJG7xgz3A) is an empty placeholder. His show is posted on
    # ESPN College Football's channel (UCzRWWsFjqHk1an4OnVPsl9g) with only about
    # 20-300 comments per video, and it made no expansion reaction video Nov 9-11.
    "crain_cone": {
        "id": "UC-LeIYApj-NTHYGAzU4cPBQ",
        "name": "Crain & Cone",
    },
}

# Window searched for candidate videos
CANDIDATE_START = datetime(2026, 11, 1, tzinfo=timezone.utc)
CANDIDATE_END = datetime(2026, 11, 14, 23, 59, tzinfo=timezone.utc)

# --- Paths -----------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"              # one JSON file per video
CANDIDATES_CSV = DATA_DIR / "candidates.csv"
VIDEOS_CSV = DATA_DIR / "videos.csv"    # the 10 selected videos (curated by hand)

# College-football slang added to VADER's lexicon (VADER scale, -4 to +4).
# Values are the project's own judgement of how the words are used in these comments;
# they were checked against the hand labels in notebook 04, section 4.
SPORTS_LEXICON = {
    # negative slang VADER doesn't know
    "trash": -2.0, "garbage": -2.0, "overrated": -1.5, "delusional": -1.8, "clown": -1.8, "clowns": -1.8,
    "robbed": -2.0, "cope": -1.2, "coping": -1.2, "mid": -1.0, "cooked": -1.5, "washed": -1.5,
    "bum": -1.8, "bums": -1.8, "glazing": -1.0, "glaze": -1.0, "esecn": -1.5, "frauds": -2.5,
    # words VADER scores the wrong way in sports talk
    "l": -1.5,       # "L" = a loss (VADER has +2.0)
    "joke": -1.5,    # "the rankings are a joke" (VADER has +1.2)
    # positive slang
    "w": 1.5, "goated": 2.0, "underrated": 1.0,
}
