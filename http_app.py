from __future__ import annotations

import threading
import time
from fastapi import FastAPI, Response, status

from worker.twitch_worker import LAST_SUCCESSFUL_LOOP_TS, main_loop
APP_START_TS = time.time()

app = FastAPI(title="NanoHero Worker")


@app.on_event("startup")
def start_worker_thread():
    # Run the Twitch worker in background
    t = threading.Thread(target=main_loop, daemon=True)
    t.start()


@app.get("/healthz", include_in_schema=False)
def healthz():
    """
    Health check that also verifies if the background worker thread is alive.
    If the last successful loop was more than 180 seconds ago, it returns an error,
    prompting Cloud Run to restart the instance.
    """
  # Grâce de démarrage: tolère jusqu'à 3 min le temps que la 1ʳᵉ boucle s’exécute
    if LAST_SUCCESSFUL_LOOP_TS == 0 and (time.time() - APP_START_TS) < 180:
         return {"status": "ok", "detail": "worker booting"}

    seconds_since_last_loop = time.time() - LAST_SUCCESSFUL_LOOP_TS
    if seconds_since_last_loop > 180:  # 3 minutes
        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=f"Worker thread is unhealthy. Last loop was {seconds_since_last_loop:.0f} seconds ago.")

    return {"status": "ok"}
