"""Kanallar statistikasini YouTube Data API (o'qish kaliti) orqali yig'adi -> data/stats/YYYY-MM-DD.json.

Ofis agentlari (analytics-lead, strategist, script-writer) shu fayldan o'qiydi, kalitga muhtoj bo'lmaydi.
Kvota: har kanal uchun ~3 birlik (channels + playlistItems + videos). search.list ishlatilmaydi.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()
CHANNELS = {"bilarmidingiz": "UCEOuVToygrPdmisnqM93Sgw", "apex_wealths": "UCdZ4u7ugyM_2hGCKbCSJ7fA"}
API = "https://www.googleapis.com/youtube/v3/"


def get(path: str, **params) -> dict:
    params["key"] = KEY
    with urllib.request.urlopen(API + path + "?" + urllib.parse.urlencode(params), timeout=30) as r:
        return json.load(r)


def channel(cid: str) -> dict:
    ch = get("channels", part="statistics,contentDetails", id=cid)["items"][0]
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    ids = [i["contentDetails"]["videoId"] for i in
           get("playlistItems", part="contentDetails", playlistId=uploads, maxResults=50).get("items", [])]
    vids = []
    if ids:
        for v in get("videos", part="snippet,statistics,contentDetails", id=",".join(ids)).get("items", []):
            s = v.get("statistics", {})
            vids.append({"id": v["id"], "title": v["snippet"]["title"], "published": v["snippet"]["publishedAt"],
                         "duration": v["contentDetails"]["duration"], "views": int(s.get("viewCount", 0)),
                         "likes": int(s.get("likeCount", 0)), "comments": int(s.get("commentCount", 0))})
    st = ch["statistics"]
    return {"subscribers": int(st.get("subscriberCount", 0)), "views": int(st.get("viewCount", 0)),
            "videos": int(st.get("videoCount", 0)), "recent": vids}


def main():
    if not KEY:
        sys.exit("YOUTUBE_API_KEY yo'q (GitHub Secrets)")
    now = datetime.now(timezone.utc)
    out = {"fetched_at": now.isoformat(timespec="seconds"), "channels": {n: channel(c) for n, c in CHANNELS.items()}}
    p = Path("data/stats") / f"{now:%Y-%m-%d}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for n, c in out["channels"].items():
        print(f"{n}: {c['subscribers']} obunachi, {c['views']} ko'rish, {len(c['recent'])} video")


if __name__ == "__main__":
    main()
