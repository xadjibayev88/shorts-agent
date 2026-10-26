"""YouTube Data API v3 orqali videoni joylash (OAuth refresh token bilan)."""
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from .utils import env, log, retry

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _client():
    creds = Credentials(
        token=None,
        refresh_token=env("YT_REFRESH_TOKEN"),
        client_id=env("YT_CLIENT_ID"),
        client_secret=env("YT_CLIENT_SECRET"),
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def build_metadata(story: dict, cfg: dict) -> dict:
    y = cfg["youtube"]
    title = story["title"]
    if "#shorts" not in title.lower() and len(title) <= 90:
        title = f"{title} #shorts"
    title = title[:100]
    hashtags = list(dict.fromkeys(story.get("hashtags", []) + y["hashtags"]))[:8]
    description = (
        f"{story.get('description', '')}\n\n"
        f"{' '.join(hashtags)}\n\n"
        "Hikoya to'qima, barcha qahramonlar xayoliy. "
        "Kadrlar: Pexels. Ovoz: sun'iy intellekt."
    )[:4900]
    tags, total = [], 0
    for t in story.get("tags", []) + y["extra_tags"]:
        t = t.strip()
        if t and t.lower() not in {x.lower() for x in tags} and total + len(t) < 450:
            tags.append(t)
            total += len(t) + 2
    return {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": y["category_id"],
            "defaultLanguage": cfg["channel"]["language"],
            "defaultAudioLanguage": cfg["channel"]["language"],
        },
        "status": {
            "privacyStatus": y["privacy"],
            "selfDeclaredMadeForKids": y["made_for_kids"],
            "containsSyntheticMedia": y["synthetic_media"],
            "embeddable": True,
        },
    }


@retry(times=3, delay=10)
def upload(video: Path, story: dict, cfg: dict) -> str:
    yt = _client()
    body = build_metadata(story, cfg)
    log.info("YouTube'ga yuklanmoqda: %s", body["snippet"]["title"])
    req = yt.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(str(video), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True),
    )
    resp = None
    try:
        while resp is None:
            status, resp = req.next_chunk()
            if status:
                log.info("  yuklandi: %d%%", int(status.progress() * 100))
    except HttpError as e:
        if e.resp.status == 403 and b"quotaExceeded" in e.content:
            raise RuntimeError("YouTube API kunlik kvotasi tugadi (10 000 birlik ≈ 6 video/kun)") from e
        raise
    vid = resp["id"]
    log.info("✅ Joylandi: https://youtube.com/shorts/%s", vid)
    return vid
