"""
BIR MARTA o'z kompyuteringizda ishga tushiring — YouTube refresh token olish uchun.

  pip install google-auth-oauthlib
  python get_token.py client_secret.json

Brauzer ochiladi -> kanalingiz bor Google akkauntni tanlang -> ruxsat bering.
Chiqqan 3 ta qiymatni GitHub Secrets'ga qo'shing.
"""
import json
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

path = sys.argv[1] if len(sys.argv) > 1 else "client_secret.json"
flow = InstalledAppFlow.from_client_secrets_file(path, SCOPES)
creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

info = json.load(open(path, encoding="utf-8"))
info = info.get("installed") or info.get("web")
print("\n=== GitHub Secrets'ga qo'shing ===")
print("YT_CLIENT_ID     =", info["client_id"])
print("YT_CLIENT_SECRET =", info["client_secret"])
print("YT_REFRESH_TOKEN =", creds.refresh_token)
