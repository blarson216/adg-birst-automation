#!/usr/bin/env python3
"""Run exactly one Birst workflow via the ION API gateway and watch it finish.

Usage:  python3 -I birst_run_workflow.py ["WORKFLOW NAME"]
        (default: ADG_BASE-DEM_COMPUTE_20-USERS)

Credentials come from IONAPI_TI/IU/PU/OT/CI/CS/SAAK/SASK.
The only write is a single POST /workflows/{id}/_runNow. It never retries
that call and never calls _cancelNow. Output is limited to status codes,
names, ids, states, timings and error messages; secrets, tokens and URLs
are redacted.
"""
import json, os, re, ssl, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

WORKFLOW_NAME = sys.argv[1] if len(sys.argv) > 1 else "ADG_BASE-DEM_COMPUTE_20-USERS"
POLL_SECONDS = 60
MAX_WAIT_SECONDS = 60 * 60
PAGE_SIZE = 50
TERMINAL_RE = re.compile(r"COMPLET|SUCCE|FAIL|CANCEL|ABORT|ERROR|STOPPED|TERMINAT|KILLED", re.I)

ctx = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or "/root/.ccr/ca-bundle.crt") \
    if os.path.exists("/root/.ccr/ca-bundle.crt") else ssl.create_default_context()
opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))

FIELDS = ["ti", "iu", "pu", "ot", "ci", "cs", "saak", "sask"]
cfg = {f: os.environ.get("IONAPI_" + f.upper()) for f in FIELDS}
missing = [f for f, v in cfg.items() if not v]
if missing:
    sys.exit(f"missing IONAPI_* fields: {missing}")
SECRETS = [v for v in cfg.values() if v and len(v) > 3]
BASE = cfg["iu"].rstrip("/") + "/" + cfg["ti"].strip("/") + "/BIRST/InforBirstRestAPI"


def scrub(s):
    s = str(s)
    for v in SECRETS:
        s = s.replace(v, "[REDACTED]")
    s = re.sub(r"https?://\S+", "[URL]", s)
    s = re.sub(r"eyJ[\w-]+\.[\w-]+\.[\w-]*", "[JWT]", s)
    return s[:500]


def log(msg):
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%SZ')}] {msg}", flush=True)


def http(url, data=None, headers=None, method="GET"):
    r = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        resp = opener.open(r, timeout=120)
        return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return None, scrub(f"{type(e).__name__}: {e}").encode()


class Token:
    def __init__(self):
        self.value, self.expires = None, 0

    def fetch(self):
        body = urllib.parse.urlencode({
            "grant_type": "password", "client_id": cfg["ci"], "client_secret": cfg["cs"],
            "username": cfg["saak"], "password": cfg["sask"]}).encode()
        st, b = http(cfg["pu"] + cfg["ot"], body,
                     {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}, "POST")
        try:
            j = json.loads(b)
        except Exception:
            j = {}
        if not j.get("access_token"):
            sys.exit(f"token request failed: HTTP {st} | {scrub(j.get('error'))} | {scrub(j.get('error_description'))}")
        self.value = j["access_token"]
        self.expires = time.time() + int(j.get("expires_in") or 3600) - 120
        log(f"token request HTTP {st} | access_token: True | expires_in: {j.get('expires_in')}")

    def get(self):
        if not self.value or time.time() >= self.expires:
            self.fetch()
        return self.value


TOKEN = Token()


def birst(path, method="GET", body=None):
    """GET (or the single POST) against Birst; refreshes the token once on 401 for GETs only."""
    for attempt in (1, 2):
        h = {"Authorization": "Bearer " + TOKEN.get(), "Accept": "application/json"}
        data = None
        if method == "POST":
            h["Content-Type"] = "application/json"
            data = json.dumps(body if body is not None else {}).encode()
        st, b = http(BASE + path, data, h, method)
        if st == 401 and method == "GET" and attempt == 1:
            log("GET returned 401; refreshing token")
            TOKEN.value = None
            continue
        try:
            return st, json.loads(b) if b else None
        except Exception:
            return st, b.decode(errors="replace")


def get_all(path):
    items, seen = [], set()
    for page in range(200):
        sep = "&" if "?" in path else "?"
        st, j = birst(f"{path}{sep}offset={page * PAGE_SIZE}&limit={PAGE_SIZE}")
        if st != 200 or not isinstance(j, list):
            sys.exit(f"GET {path} failed: HTTP {st} | {scrub(j)}")
        key = tuple(json.dumps(x, sort_keys=True)[:200] for x in j[:3])
        if j and key in seen:  # server ignored paging and repeated a page
            break
        seen.add(key)
        items.extend(j)
        if len(j) < PAGE_SIZE:
            break
    return items


def parse_ts(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def current_state(obj):
    """Latest state from a stateTransitions map {STATE: timestamp}."""
    st = (obj or {}).get("stateTransitions") or {}
    if not st:
        return None, None
    state, ts = max(st.items(), key=lambda kv: parse_ts(kv[1]) or datetime.min.replace(tzinfo=timezone.utc))
    return state, ts


def is_terminal(state):
    return bool(state and TERMINAL_RE.search(state))


def fmt_dur(a, b):
    if not (a and b):
        return "n/a"
    s = int((b - a).total_seconds())
    return f"{s // 3600}h {s % 3600 // 60}m {s % 60}s" if s >= 3600 else f"{s // 60}m {s % 60}s"


def main():
    TOKEN.get()

    # 2. find the workflow
    wfs = get_all("/workflows")
    matches = [w for w in wfs if w.get("name") == WORKFLOW_NAME]
    log(f"GET /workflows: {len(wfs)} workflows | exact matches for '{WORKFLOW_NAME}': {len(matches)}")
    if len(matches) != 1:
        near = [w.get("name") for w in wfs if WORKFLOW_NAME.lower() in str(w.get("name")).lower()]
        for w in matches:
            log(f"  match: {w.get('workflowId')}")
        log(f"STOP: need exactly one match. Similar names: {[scrub(n) for n in near]}")
        return 2
    wf = matches[0]
    wid = wf["workflowId"]
    log(f"workflowId: {wid}")

    # Build the WorkflowCustomRun body from the workflow definition: every step, every task, execute=true.
    sc, detail = birst(f"/workflows/{wid}")
    if sc != 200 or not isinstance(detail, dict):
        log(f"STOP: GET /workflows/{{id}} failed: HTTP {sc} | {scrub(detail)}")
        return 2
    run_body = {"steps": []}
    for s in detail.get("steps") or []:
        tasks = [{"taskId": t.get("taskId"), "execute": True} for t in s.get("tasks") or []]
        if not s.get("stepId") or any(not t["taskId"] for t in tasks):
            log("STOP: workflow definition has a step or task without an id")
            return 2
        run_body["steps"].append({"stepId": s["stepId"], "tasks": tasks})
    n_tasks = sum(len(s["tasks"]) for s in run_body["steps"])
    log(f"GET /workflows/{{id}}: HTTP {sc} | run body: {len(run_body['steps'])} steps, {n_tasks} tasks (all execute=true)")
    if not run_body["steps"] or not n_tasks:
        log("STOP: workflow has no steps or tasks to run")
        return 2

    # 3. check for an in-progress run
    runs = get_all(f"/workflows/{wid}/runs")
    active = []
    for r in runs:
        state, ts = current_state(r)
        if not is_terminal(state):
            active.append((r.get("runId"), state, ts))
    log(f"GET /runs: {len(runs)} existing runs | not finished: {len(active)}")
    if active:
        for rid, state, ts in active:
            log(f"  in progress: runId {rid} | state {state} since {ts}")
        log("STOP: a run is already in progress; not starting another.")
        return 3
    prior_ids = {r.get("runId") for r in runs}

    # 4. the single write
    st, j = birst(f"/workflows/{wid}/_runNow", method="POST", body=run_body)
    log(f"POST _runNow: HTTP {st}")
    if isinstance(j, dict):
        for k, v in j.items():
            if re.search(r"id$|state|status", k, re.I) and not isinstance(v, (dict, list)):
                log(f"  {k}: {scrub(v)}")
    if st is None or st >= 300:
        log(f"STOP: _runNow failed (not retrying): {scrub(j)}")
        return 4
    run_id = (j.get("id") or j.get("runId")) if isinstance(j, dict) else None
    log(f"runId: {run_id}")

    # 5. poll
    start_wall = time.time()
    run = None
    while True:
        time.sleep(POLL_SECONDS)
        if run_id:
            sc, run = birst(f"/workflows/{wid}/runs/{run_id}")
            if sc != 200:
                log(f"poll: HTTP {sc} | {scrub(run)}")
                run = None
        else:
            new = [r for r in get_all(f"/workflows/{wid}/runs") if r.get("runId") not in prior_ids]
            new.sort(key=lambda r: parse_ts(r.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc))
            run = new[-1] if new else None
            if run:
                run_id = run.get("runId")
                log(f"found new runId {run_id} in /runs")
        elapsed = int(time.time() - start_wall)
        state, ts = current_state(run)
        log(f"poll {elapsed // 60:>2}m: state={state} (since {ts})" if run else f"poll {elapsed // 60:>2}m: run not visible yet")
        if is_terminal(state):
            break
        if elapsed >= MAX_WAIT_SECONDS:
            log("STOP: 60-minute limit reached; run is still not finished (not cancelling).")
            break

    # 6. report
    if not run:
        log("no run details available")
        return 5
    trans = run.get("stateTransitions") or {}
    times = [parse_ts(v) for v in trans.values() if parse_ts(v)]
    start = parse_ts(trans.get("RUNNING")) or (min(times) if times else None)
    state, end_ts = current_state(run)
    end = parse_ts(end_ts) if is_terminal(state) else None
    print("\n===== RESULT =====")
    print(f"workflow:  {scrub(run.get('name'))} ({wid})")
    print(f"runId:     {run.get('runId')}")
    print(f"state:     {state}")
    print(f"start:     {start.isoformat() if start else 'n/a'}")
    print(f"end:       {end.isoformat() if end else 'n/a'}")
    print(f"duration:  {fmt_dur(start, end)}")
    print(f"transitions: {trans}")
    if run.get("errorMessage"):
        print(f"error:     {scrub(run['errorMessage'])}")
    for i, s in enumerate(run.get("steps") or [], 1):
        ss, _ = current_state(s)
        st_t = s.get("stateTransitions") or {}
        print(f"step {i}: {s.get('stepId')} | state {ss} | {fmt_dur(parse_ts(st_t.get('RUNNING')), parse_ts(_))}"
              + (f" | error: {scrub(s['errorMessage'])}" if s.get("errorMessage") else ""))
        for t in s.get("tasks") or []:
            ts_, tend = current_state(t)
            tt = t.get("stateTransitions") or {}
            print(f"    task {t.get('type')} {t.get('taskId')} | state {ts_} | {fmt_dur(parse_ts(tt.get('RUNNING')), parse_ts(tend))}"
                  + (f" | error: {scrub(t['errorMessage'])}" if t.get("errorMessage") else ""))
    return 0 if state and re.search(r"COMPLET|SUCCE", state, re.I) else 1


if __name__ == "__main__":
    sys.exit(main())
