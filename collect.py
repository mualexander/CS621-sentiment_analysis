"""YouTube Data API v3 collection for the CFP expansion sentiment study.

Usage
-----
    export YOUTUBE_API_KEY=...        # or put YOUTUBE_API_KEY=... in a .env file
    python collect.py verify          # check both channels exist and are active
    python collect.py candidates      # list uploads in the window -> data/candidates.csv
    python collect.py comments        # collect every video in data/videos.csv
    python collect.py comments --only VIDEO_ID [--force]
    python collect.py countries       # commenter snippet.country -> data/commenter_channels.json

Quota (default limit is 10,000 units a day; each call below costs 1 unit)
    channels.list / playlistItems.list / videos.list : 1 per call (up to 50 items)
    commentThreads.list : 1 per page of up to 100 threads
    comments.list       : 1 per page of up to 100 replies (only for threads with >5 replies)

Design notes
------------
* We collect *all* comments on each video instead of stopping at about 1,000.
  The API returns newest comments first, so a cap would mostly drop the oldest
  comments, which are the pre-announcement ones the main analysis depends on.
  Sampling, if any, happens later and is documented there.
* Raw API responses are saved unchanged (one JSON file per video) so the
  ingestion step can be redone from the files without calling the API again.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

import config

API = "https://www.googleapis.com/youtube/v3"


# ---------------------------------------------------------------------------
# API client with quota tracking
# ---------------------------------------------------------------------------
class QuotaExceeded(RuntimeError):
    pass


class YouTube:
    def __init__(self, key: str):
        self.key = key
        self.units = 0
        self.session = requests.Session()

    def get(self, endpoint: str, **params) -> dict:
        params["key"] = self.key
        for attempt in range(4):
            r = self.session.get(f"{API}/{endpoint}", params=params, timeout=30)
            self.units += 1
            if r.status_code == 200:
                return r.json()
            reason = _error_reason(r)
            if reason in ("quotaExceeded", "dailyLimitExceeded"):
                raise QuotaExceeded(f"Quota exhausted after {self.units} units this run")
            if r.status_code >= 500 or reason in ("rateLimitExceeded", "userRateLimitExceeded"):
                time.sleep(2 ** attempt)
                continue
            shown = {k: v for k, v in params.items() if k != "key"}
            raise requests.HTTPError(f"{endpoint} {r.status_code} {reason} params={shown}")
        raise requests.HTTPError(f"{endpoint}: gave up after retries")


def _error_reason(r: requests.Response) -> str:
    try:
        return r.json()["error"]["errors"][0]["reason"]
    except Exception:
        return ""


def load_key() -> str:
    key = os.environ.get("YOUTUBE_API_KEY")
    env_file = config.ROOT / ".env"
    if not key and env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.strip().startswith("YOUTUBE_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("'\"")
    if not key:
        sys.exit("YOUTUBE_API_KEY is not set (export it or add it to .env).")
    return key


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def iso_duration_seconds(d: str) -> int:
    """Convert an ISO-8601 duration such as 'PT1H2M3S' to seconds."""
    total, num = 0, ""
    for ch in d.removeprefix("P").replace("T", ""):
        if ch.isdigit():
            num += ch
        else:
            total += int(num or 0) * {"D": 86400, "H": 3600, "M": 60, "S": 1}[ch]
            num = ""
    return total


# ---------------------------------------------------------------------------
# Step 0: verify channels
# ---------------------------------------------------------------------------
def cmd_verify(yt: YouTube, _args) -> None:
    ids = ",".join(c["id"] for c in config.CHANNELS.values())
    resp = yt.get("channels", part="snippet,statistics,contentDetails", id=ids)
    found = {item["id"]: item for item in resp.get("items", [])}
    for key, ch in config.CHANNELS.items():
        item = found.get(ch["id"])
        if not item:
            print(f"[{key}] NOT FOUND: {ch['id']}")
            continue
        uploads = item["contentDetails"]["relatedPlaylists"]["uploads"]
        try:
            latest = yt.get("playlistItems", part="contentDetails", playlistId=uploads, maxResults=1)
            last = latest["items"][0]["contentDetails"].get("videoPublishedAt", "?") if latest["items"] else "none"
        except requests.HTTPError as e:
            if "playlistNotFound" not in str(e):
                raise
            last = "UPLOADS PLAYLIST NOT FOUND (no public uploads?)"
        st = item["statistics"]
        print(f"[{key}] {item['snippet']['title']}")
        print(f"    subscribers={st.get('subscriberCount', 'hidden')}  videos={st['videoCount']}  "
              f"latest upload={last}")
    print(f"quota used: {yt.units} units")


# ---------------------------------------------------------------------------
# Step 1: candidate videos around the announcement
# ---------------------------------------------------------------------------
def uploads_in_window(yt: YouTube, channel_id: str) -> list[str]:
    uploads = "UU" + channel_id[2:]   # the uploads playlist ID is the channel ID with UC changed to UU
    video_ids, page = [], None
    while True:
        resp = yt.get("playlistItems", part="contentDetails", playlistId=uploads,
                      maxResults=50, pageToken=page or "")
        stop = False
        for it in resp["items"]:
            published = parse_ts(it["contentDetails"]["videoPublishedAt"])
            if published < config.CANDIDATE_START:
                stop = True   # the playlist is newest-first
                break
            if published <= config.CANDIDATE_END:
                video_ids.append(it["contentDetails"]["videoId"])
        page = resp.get("nextPageToken")
        if stop or not page:
            return video_ids


def cmd_candidates(yt: YouTube, _args) -> None:
    rows = []
    for key, ch in config.CHANNELS.items():
        ids = uploads_in_window(yt, ch["id"])
        for i in range(0, len(ids), 50):
            resp = yt.get("videos", part="snippet,statistics,contentDetails", id=",".join(ids[i:i + 50]))
            for v in resp["items"]:
                filt = ch.get("title_filter")
                if filt and not any(f in v["snippet"]["title"].lower() for f in filt):
                    continue   # shared channel (ESPN), so keep only this creator's show
                pub = parse_ts(v["snippet"]["publishedAt"])
                hours = (pub - config.ANNOUNCE_UTC).total_seconds() / 3600
                rows.append({
                    "creator": key,
                    "video_id": v["id"],
                    "published_utc": v["snippet"]["publishedAt"],
                    "hours_vs_announce": round(hours, 1),
                    "period": "before" if hours < -12 else ("day_of" if hours < 36 else "after"),
                    "duration_s": iso_duration_seconds(v["contentDetails"]["duration"]),
                    "comments": int(v["statistics"].get("commentCount", 0)),  # missing = comments disabled
                    "views": int(v["statistics"].get("viewCount", 0)),
                    "title": v["snippet"]["title"],
                })
    rows.sort(key=lambda r: (r["creator"], r["published_utc"]))
    config.DATA_DIR.mkdir(exist_ok=True)
    with open(config.CANDIDATES_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        short = " SHORT" if r["duration_s"] <= 180 else ""
        print(f"{r['creator']:8} {r['published_utc']} {r['hours_vs_announce']:>7}h {r['period']:6} "
              f"{r['comments']:>6}c{short}  {r['title'][:70]}")
    print(f"\n{len(rows)} candidates -> {config.CANDIDATES_CSV}   quota used: {yt.units} units")


# ---------------------------------------------------------------------------
# Step 2: comments (threads and full reply chains), raw JSON per video
# ---------------------------------------------------------------------------
def collect_video(yt: YouTube, video_id: str, meta: dict) -> dict:
    thread_pages, reply_pages, page = [], {}, None
    while True:
        resp = yt.get("commentThreads", part="snippet,replies", videoId=video_id,
                      maxResults=100, order="time", textFormat="plainText", pageToken=page or "")
        thread_pages.append(resp)
        page = resp.get("nextPageToken")
        n = sum(len(p["items"]) for p in thread_pages)
        print(f"\r  {video_id}: {n} threads", end="", flush=True)
        if not page:
            break
    print()

    # commentThreads embeds at most 5 replies, so fetch the rest with comments.list(parentId=...)
    for p in thread_pages:
        for th in p["items"]:
            total = th["snippet"]["totalReplyCount"]
            embedded = len(th.get("replies", {}).get("comments", []))
            if total > embedded:
                pages, rp = [], None
                while True:
                    r = yt.get("comments", part="snippet", parentId=th["id"], maxResults=100,
                               textFormat="plainText", pageToken=rp or "")
                    pages.append(r)
                    rp = r.get("nextPageToken")
                    if not rp:
                        break
                reply_pages[th["id"]] = pages

    return {
        "video": meta,
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "comment_threads_pages": thread_pages,   # raw commentThreads.list responses
        "reply_pages": reply_pages,              # parentId -> raw comments.list responses
    }


def cmd_comments(yt: YouTube, args) -> None:
    if not config.VIDEOS_CSV.exists():
        sys.exit(f"{config.VIDEOS_CSV} not found. Run `candidates` first and choose the 10 videos.")
    with open(config.VIDEOS_CSV, newline="", encoding="utf-8") as f:
        videos = list(csv.DictReader(f))
    if args.only:
        videos = [v for v in videos if v["video_id"] in args.only]
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)

    for v in videos:
        out = config.RAW_DIR / f"{v['video_id']}.json"
        if out.exists() and not args.force:
            print(f"skip {v['video_id']} (already collected; use --force to refetch)")
            continue
        print(f"[{v['creator']}/{v['period']}] {v.get('title', '')[:70]}")
        try:
            data = collect_video(yt, v["video_id"], v)
        except QuotaExceeded as e:
            print(f"\n{e}. Run again tomorrow; videos already saved are skipped.")
            break
        except requests.HTTPError as e:
            if "commentsDisabled" in str(e):
                print(f"  comments disabled on {v['video_id']}; skipping")
                continue
            raise
        tmp = out.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(out)   # write atomically so an interrupted run leaves no half-written file
        n_top = sum(len(p["items"]) for p in data["comment_threads_pages"])
        n_rep = sum(th["snippet"]["totalReplyCount"] for p in data["comment_threads_pages"] for th in p["items"])
        print(f"  saved {out.name}: {n_top} top-level + {n_rep} replies   (quota so far: {yt.units})")
    print(f"done. quota used this run: {yt.units} units")


# ---------------------------------------------------------------------------
# Step 3 (extra): commenter channel country (optional, often left blank)
# ---------------------------------------------------------------------------
def iter_raw_comments():
    """Yield every comment snippet (top-level and reply) from the raw files."""
    for f in sorted(config.RAW_DIR.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        for p in d["comment_threads_pages"]:
            for th in p["items"]:
                yield th["snippet"]["topLevelComment"]["snippet"]
                for c in th.get("replies", {}).get("comments", []):
                    yield c["snippet"]
        for pages in d["reply_pages"].values():
            for p in pages:
                for c in p["items"]:
                    yield c["snippet"]


def cmd_countries(yt: YouTube, _args) -> None:
    ids = sorted({s["authorChannelId"]["value"] for s in iter_raw_comments() if s.get("authorChannelId")})
    print(f"{len(ids)} unique commenter channels -> about {-(-len(ids) // 50)} units")
    pages = []
    for i in range(0, len(ids), 50):
        pages.append(yt.get("channels", part="snippet", id=",".join(ids[i:i + 50]), maxResults=50))
        print(f"\r  {min(i + 50, len(ids))}/{len(ids)}", end="", flush=True)
    print()
    out = config.DATA_DIR / "commenter_channels.json"
    out.write_text(json.dumps({"collected_at_utc": datetime.now(timezone.utc).isoformat(),
                               "requested_ids": ids, "pages": pages}, ensure_ascii=False), encoding="utf-8")

    items = [it for p in pages for it in p.get("items", [])]
    countries = [it["snippet"].get("country") for it in items]
    filled = [c for c in countries if c]
    print(f"returned {len(items)}/{len(ids)} channels (the rest are deleted or hidden)")
    print(f"country filled: {len(filled)}/{len(items)} = {len(filled) / max(len(items), 1):.1%}")
    from collections import Counter
    for c, n in Counter(filled).most_common(10):
        print(f"  {c}: {n}")
    print(f"saved {out.name}   quota used: {yt.units} units")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("verify")
    sub.add_parser("candidates")
    c = sub.add_parser("comments")
    c.add_argument("--only", nargs="+", help="collect only these video IDs")
    c.add_argument("--force", action="store_true", help="refetch even if the raw file exists")
    sub.add_parser("countries", help="look up snippet.country for every commenter channel")
    args = ap.parse_args()

    yt = YouTube(load_key())
    {"verify": cmd_verify, "candidates": cmd_candidates, "comments": cmd_comments,
     "countries": cmd_countries}[args.cmd](yt, args)


if __name__ == "__main__":
    main()
