from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Optional
import json
import traceback

import requests
from sqlalchemy import text
from sqlalchemy import select

from worker.config import get_settings
from worker.db import session_scope, engine
from worker.models import Stream, User, Base


TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_STREAMS_URL = "https://api.twitch.tv/helix/streams"

# --- Global state for health check ---
# Timestamp of the last successfully completed loop.
# This is used by http_app.py to verify the worker is still alive.
LAST_SUCCESSFUL_LOOP_TS = 0


def get_app_access_token() -> Optional[str]:
    settings = get_settings()
    if settings.TWITCH_APP_ACCESS_TOKEN:
        return settings.TWITCH_APP_ACCESS_TOKEN
    if not settings.TWITCH_CLIENT_ID or not settings.TWITCH_CLIENT_SECRET:
        print("[get_app_access_token] Missing TWITCH_CLIENT_ID or TWITCH_CLIENT_SECRET in config.", flush=True)
        return None
    try:
        print("[get_app_access_token] Requesting app access token from Twitch...", flush=True)
        r = requests.post(
            TWITCH_TOKEN_URL,
            data={
                "client_id": settings.TWITCH_CLIENT_ID,
                "client_secret": settings.TWITCH_CLIENT_SECRET,
                "grant_type": "client_credentials",
            },
            timeout=20,
        )
        print(f"[get_app_access_token] Twitch response status={r.status_code}", flush=True)
        r.raise_for_status()
        data = r.json()
        token = data.get("access_token")
        if not token:
            print(f"[get_app_access_token] 'access_token' not found in Twitch response: {data}", flush=True)
        return token
    except requests.exceptions.RequestException as e:
        print(f"[get_app_access_token] Network error while fetching token: {e}", flush=True)
        return None
    except Exception as e:
        print(f"[get_app_access_token] Unexpected error while fetching token: {e}\n{traceback.format_exc()}", flush=True)
        return None


def fetch_viewer_counts_batch(broadcaster_ids: list[str], client_id: str, token: str) -> dict[str, int]:
    """
    Fetches viewer counts for a batch of up to 100 broadcasters in a single API call.
    Returns a dictionary mapping broadcaster_id to viewer_count.
    """
    if not broadcaster_ids:
        return {}

    headers = {"Client-Id": client_id, "Authorization": f"Bearer {token}"}
    # Build query params like: ?user_id=123&user_id=456
    params = [("user_id", bid) for bid in broadcaster_ids]

    try:
        r = requests.get(TWITCH_STREAMS_URL, headers=headers, params=params, timeout=20)
        status = r.status_code
        try:
            data = r.json()
            preview = json.dumps(data)[:500]
        except Exception:
            data = {}
            preview = r.text[:500]
        print(f"[fetch_viewer_counts_batch] streams batch_size={len(broadcaster_ids)} status={status} payload~={preview}", flush=True)
        r.raise_for_status()

        # Create a dict of {broadcaster_id: viewer_count} from the response
        viewer_counts = {}
        if data.get("data"):
            for stream_info in data["data"]:
                user_id = stream_info.get("user_id")
                if user_id:
                    viewer_counts[user_id] = int(stream_info.get("viewer_count", 0))
        return viewer_counts

    except requests.exceptions.RequestException as e:
        print(f"[fetch_viewer_counts_batch] Request error: {e}", flush=True)
        return {}
    except Exception as e:
        print(f"[fetch_viewer_counts_batch] Unexpected error: {e}\n{traceback.format_exc()}", flush=True)
        return {}


def upsert_stream_row(streamer_id: int, viewer_count: int):
    now = datetime.now(timezone.utc)
    with session_scope() as db:
        # Find active stream without ended_at
        active = db.execute(
            select(Stream).where(Stream.streamer_id == streamer_id, Stream.ended_at.is_(None))
        ).scalars().first()

        if viewer_count > 0:
            if active:
                old = active.viewer_count
                active.viewer_count = viewer_count
                print(f"[upsert_stream_row] Updated stream id={active.id} streamer_id={streamer_id} vc {old} -> {viewer_count}", flush=True)
            else:
                new_stream = Stream(streamer_id=streamer_id, started_at=now, viewer_count=viewer_count)
                db.add(new_stream)
                print(f"[upsert_stream_row] Created new stream streamer_id={streamer_id} vc={viewer_count}", flush=True)
        else:
            if active:
                active.ended_at = now
                print(f"[upsert_stream_row] Ended stream id={active.id} streamer_id={streamer_id}", flush=True)


def main_loop():
    global LAST_SUCCESSFUL_LOOP_TS
    settings = get_settings()
    # Ensure DB tables exist (in case API wasn't hit yet)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        Base.metadata.create_all(bind=engine)
        # Ensure optional columns exist on serving_logs
        try:
            with engine.begin() as conn:
                existing = {r[0] for r in conn.execute(text(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='serving_logs'"
                ))}
                if "width" not in existing:
                    conn.execute(text("ALTER TABLE serving_logs ADD COLUMN width INTEGER NULL"))
                if "height" not in existing:
                    conn.execute(text("ALTER TABLE serving_logs ADD COLUMN height INTEGER NULL"))
                if "visible" not in existing:
                    conn.execute(text("ALTER TABLE serving_logs ADD COLUMN visible BOOLEAN NULL"))
                if "viewer_count" not in existing:
                    conn.execute(text("ALTER TABLE serving_logs ADD COLUMN viewer_count INTEGER NULL"))
        except Exception as mig_e:
            print(f"[twitch_worker] Warning: ensure serving_logs optional columns failed: {mig_e}", flush=True)
        print("[twitch_worker] DB ready and tables ensured.", flush=True)
    except Exception as e:
        print(f"[twitch_worker] Warning: could not ensure DB tables at start: {e}", flush=True)
    # Config snapshot (masked)
    cid = settings.TWITCH_CLIENT_ID or ''
    print(f"[twitch_worker] Config: TWITCH_CLIENT_ID len={len(cid)} present={bool(cid)}", flush=True)
    # Do not print DATABASE_URL, but confirm presence
    from worker.config import get_settings as _gs
    try:
        print(f"[twitch_worker] Config: DATABASE_URL present={bool(_gs().DATABASE_URL)}", flush=True)
    except Exception:
        print("[twitch_worker] Config: DATABASE_URL not readable", flush=True)

    while True:
        try:
            print("\n[twitch_worker] --- Starting new loop iteration ---", flush=True)
            token = get_app_access_token()
            if not token:
                print("[twitch_worker] Could not get Twitch token. Retrying in 60s.", flush=True)
                time.sleep(60)
                continue

            # Fetch streamer data inside the session, but process it outside
            # to avoid holding a DB connection open during long network requests.
            streamer_infos = []
            print("[twitch_worker] Opening DB session to fetch streamers...", flush=True)
            with session_scope() as db:
                # Select only the columns we need to avoid holding onto the full User object
                # outside the session. This returns a list of Row objects (like tuples).
                streamer_infos = db.execute(
                    select(User.id, User.twitch_broadcaster_id).where(User.twitch_broadcaster_id.isnot(None))
                ).all()
                print(f"[twitch_worker] Fetched data for {len(streamer_infos)} streamers: {streamer_infos}", flush=True)
            print("[twitch_worker] DB session closed. Starting to process streamers.", flush=True)
            
            # --- Process streamers in batches of 100 (Twitch API limit) ---
            # Create a map of twitch_id -> internal_user_id for efficient lookup
            streamer_id_map = {s.twitch_broadcaster_id: s.id for s in streamer_infos if s.twitch_broadcaster_id}
            all_broadcaster_ids = list(streamer_id_map.keys())
            print(f"[twitch_worker] Found {len(all_broadcaster_ids)} broadcaster IDs to process.", flush=True)
            
            for i in range(0, len(all_broadcaster_ids), 100):
                batch_ids = all_broadcaster_ids[i:i + 100]
                print(f"[twitch_worker] Processing batch of {len(batch_ids)} broadcaster IDs.", flush=True)
                
                live_streams_data = fetch_viewer_counts_batch(batch_ids, settings.TWITCH_CLIENT_ID, token)
                live_broadcaster_ids = set(live_streams_data.keys())

                # Process only the streamers in the current batch
                for twitch_id in batch_ids:
                    internal_user_id = streamer_id_map[twitch_id]
                    viewer_count = live_streams_data.get(twitch_id, 0)
                    upsert_stream_row(internal_user_id, viewer_count)

        except Exception as e:
            print(f"[twitch_worker] !! FATAL loop error: {type(e).__name__} - {str(e)}\n{traceback.format_exc()}", flush=True)

        # At the end of every loop (even if there were errors processing some streamers),
        # update the healthcheck timestamp to show the main thread is alive.
        LAST_SUCCESSFUL_LOOP_TS = time.time()
        print(f"[twitch_worker] Loop finished. Healthcheck timestamp updated to {LAST_SUCCESSFUL_LOOP_TS}", flush=True)
        time.sleep(60)


if __name__ == "__main__":
    main_loop()
