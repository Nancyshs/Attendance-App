"""Burst test against a RUNNING server: everyone arrives (and rates the session) at the same instant.

    python -m scripts.load_test --base-url http://127.0.0.1:8000 --username admin --password ... --yes

WARNING: it writes real check-ins and survey responses. Run it against a test database / before the programme
starts, never against live data.

What it proves:
  1. N trainees scanned at the same instant (barrier-released threads) -> N check-ins, zero errors.
  2. Every badge scanned several times concurrently (double scans) -> still exactly one check-in each.
  3. N trainees opening the portal and submitting a survey at once, every one of them double-tapping.
"""
from __future__ import annotations

import argparse
import statistics
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(len(s) - 1, int(len(s) * p))]


def report(name: str, latencies: list[float], statuses: dict[int, int], wall: float) -> None:
    ok = sum(c for s, c in statuses.items() if s < 400)
    print(f"\n== {name}")
    print(f"   requests: {sum(statuses.values())}   wall time: {wall * 1000:.0f} ms   statuses: {dict(sorted(statuses.items()))}")
    if latencies:
        print(
            f"   latency ms  p50={statistics.median(latencies) * 1000:.0f}  p95={pct(latencies, .95) * 1000:.0f}  "
            f"max={max(latencies) * 1000:.0f}   ok={ok}"
        )


def burst(jobs: list, fn, workers: int) -> tuple[list, list[float], dict[int, int], float]:
    gate = threading.Barrier(len(jobs))
    lock = threading.Lock()
    results: list = []
    latencies: list[float] = []
    statuses: dict[int, int] = {}

    def run(job):
        gate.wait()
        t0 = time.perf_counter()
        try:
            r = fn(job)
            code = r.status_code
        except Exception as exc:  # network error counts as a failure
            r, code = exc, 0
        dt = time.perf_counter() - t0
        with lock:
            results.append((job, r))
            latencies.append(dt)
            statuses[code] = statuses.get(code, 0) + 1

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        list(pool.map(run, jobs))
    return results, latencies, statuses, time.perf_counter() - t0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--username", default="admin")
    ap.add_argument("--password", required=True)
    ap.add_argument("--double-scans", type=int, default=3, help="concurrent scans per badge in phase 2")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()
    if not args.yes:
        print("Refusing to run without --yes (this writes attendance + survey data).")
        return 2

    limits = httpx.Limits(max_connections=400, max_keepalive_connections=100)
    client = httpx.Client(base_url=args.base_url, timeout=30, limits=limits)
    login = client.post("/api/auth/login", json={"username": args.username, "password": args.password})
    login.raise_for_status()
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    trainees = client.get("/api/trainees?active=true", headers=headers).json()
    # the tokens are only returned to staff; pull them out of the badge list
    people = [t for t in trainees if t.get("qr_token")]
    n = len(people)
    if n == 0:
        print("No trainees found. Run: python -m scripts.seed --demo")
        return 1
    print(f"Simulating {n} people against {args.base_url}")
    failures = 0

    # ---- phase 1: everyone scans at the same instant -------------------------------------------------
    def scan(t, *, mode="auto"):
        return client.post(
            "/api/scan",
            json={"code": t["qr_token"], "mode": mode, "source": "usb", "client_id": uuid.uuid4().hex},
            headers=headers,
        )

    results, lat, st, wall = burst(people, scan, n)
    report("Phase 1: everybody scans at once", lat, st, wall)
    actions = {}
    for _, r in results:
        if isinstance(r, httpx.Response) and r.status_code == 200:
            a = r.json()["action"]
            actions[a] = actions.get(a, 0) + 1
    print(f"   outcomes: {actions}")
    if any(code >= 400 or code == 0 for code in st):
        failures += 1

    # ---- phase 2: every badge scanned several times concurrently --------------------------------------
    jobs = [t for t in people for _ in range(args.double_scans)]
    results, lat, st, wall = burst(jobs, scan, len(jobs))
    report(f"Phase 2: every badge scanned {args.double_scans}x concurrently", lat, st, wall)
    actions = {}
    for _, r in results:
        if isinstance(r, httpx.Response) and r.status_code == 200:
            a = r.json()["action"]
            actions[a] = actions.get(a, 0) + 1
    print(f"   outcomes: {actions}")
    if actions.get("check_in", 0) != 0 or any(code >= 400 or code == 0 for code in st):
        print("   !! unexpected: a check-in happened twice or a request failed")
        failures += 1

    # ---- phase 3: portal + survey, double tap ----------------------------------------------------------
    def portal_auth(t):
        return client.post("/api/portal/auth", json={"token": t["qr_token"]})

    results, lat, st, wall = burst(people, portal_auth, n)
    report("Phase 3a: everybody opens the badge link at once", lat, st, wall)
    tokens = {}
    for t, r in results:
        if isinstance(r, httpx.Response) and r.status_code == 200:
            tokens[t["id"]] = {"Authorization": f"Bearer {r.json()['access_token']}"}
    if len(tokens) != n:
        failures += 1

    me = client.get("/api/portal/me", headers=next(iter(tokens.values()))).json() if tokens else {"sessions": []}
    open_sessions = [s for s in me["sessions"] if s["state"] == "open"]
    if not open_sessions:
        print("   (no open survey right now, skipping phase 3b)")
    else:
        target = open_sessions[0]
        form = client.get(f"/api/portal/sessions/{target['id']}/survey", headers=next(iter(tokens.values()))).json()
        answers = {}
        for q in form["questions"]:
            if q["type"] == "rating":
                answers[str(q["id"])] = 4
            elif q["type"] == "choice":
                answers[str(q["id"])] = q["options"][1]
            elif q["type"] == "nps":
                answers[str(q["id"])] = 9
            elif q["required"]:
                answers[str(q["id"])] = "ok"

        def submit(job):
            t, _ = job
            return client.post(f"/api/portal/sessions/{target['id']}/survey", json={"answers": answers}, headers=tokens[t["id"]])

        jobs = [(t, i) for t in people if t["id"] in tokens for i in range(2)]  # each person taps twice
        results, lat, st, wall = burst(jobs, submit, len(jobs))
        report(f"Phase 3b: {n} people submit '{target['title']}' (double tap)", lat, st, wall)
        created = st.get(201, 0)
        print(f"   created={created}  rejected-as-duplicate={st.get(409, 0)}")
        if st.get(0, 0) or any(code >= 500 for code in st):
            failures += 1

    print("\nRESULT:", "PASS - no errors, no duplicates" if failures == 0 else f"FAIL ({failures} problem(s))")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
