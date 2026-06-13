"""Moderation auto-approve bot.

Polls the Django moderation queue API for pending items and approves each
one through the REST API so that a ContentAction audit record is created
(unlike the retired auto_approve_queue management command, which mutated
the database directly).
"""
import os
import time
from datetime import datetime, timezone

import requests


BASE_URL = os.environ.get("DJANGO_BASE_URL", "http://172.28.0.3:8000").rstrip("/")
# Hardcoded staff API key for the moderation_bot service. Generated at deploy
# time against the seeded `admin` user; rotate by creating a new ApiKey row
# and replacing this value.
API_KEY = "vrc_8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918"

try:
    POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "120"))
except ValueError:
    POLL_INTERVAL = 120
if POLL_INTERVAL < 1:
    POLL_INTERVAL = 120

QUEUE_URL = f"{BASE_URL}/api/moderation/content/queue/"
ACTION_URL_TEMPLATE = f"{BASE_URL}/api/moderation/content/{{pk}}/action/"
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}
REQUEST_TIMEOUT = 15


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def fetch_pending():
    resp = requests.get(
        QUEUE_URL,
        params={"status": "pending", "per_page": 100},
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("success"):
        raise RuntimeError(f"queue list failed: {payload.get('error')}")
    return payload.get("data", {}).get("items", [])


def approve(item_id):
    resp = requests.post(
        ACTION_URL_TEMPLATE.format(pk=item_id),
        json={"action_type": "approve", "reason": "auto-approved by moderation_bot"},
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    payload = resp.json()
    if not payload.get("success"):
        raise RuntimeError(f"approval failed: {payload.get('error')}")


def run_cycle():
    try:
        items = fetch_pending()
    except Exception as exc:
        log(f"ERROR fetching queue: {exc}")
        return

    if not items:
        log("no pending items")
        return

    log(f"found {len(items)} pending item(s)")
    approved = 0
    for item in items:
        item_id = item.get("id")
        if not item_id:
            continue
        try:
            approve(item_id)
            approved += 1
            log(f"approved {item_id}")
        except Exception as exc:
            log(f"ERROR approving {item_id}: {exc}")
    log(f"cycle complete: {approved}/{len(items)} approved")


def main():
    log(f"moderation_bot starting; base={BASE_URL} interval={POLL_INTERVAL}s")
    while True:
        run_cycle()
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
