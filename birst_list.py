import os, json, ssl, urllib.request, urllib.parse, urllib.error, re
ctx = ssl.create_default_context(cafile="/root/.ccr/ca-bundle.crt")
opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
cfg = {f: os.environ.get("IONAPI_" + f.upper()) for f in ["ti","iu","pu","ot","ci","cs","saak","sask"]}
SECRETS = [v for v in cfg.values() if v and len(v) > 3]
def scrub(s):
    s = str(s)
    for v in SECRETS: s = s.replace(v, "[REDACTED]")
    s = re.sub(r"https?://\S+", "[URL]", s)
    s = re.sub(r"eyJ[\w-]+\.[\w-]+\.[\w-]*", "[JWT]", s)
    return s[:400]
def req(url, data=None, headers=None, method="GET"):
    r = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        resp = opener.open(r, timeout=60); return resp.status, resp.read()
    except urllib.error.HTTPError as e: return e.code, e.read()
    except Exception as e: return None, scrub(f"{type(e).__name__}: {e}").encode()
print("missing fields:", [k for k,v in cfg.items() if not v])
data = urllib.parse.urlencode({"grant_type":"password","client_id":cfg["ci"],"client_secret":cfg["cs"],
    "username":cfg["saak"],"password":cfg["sask"]}).encode()
st, body = req(cfg["pu"] + cfg["ot"], data, {"Content-Type":"application/x-www-form-urlencoded","Accept":"application/json"}, "POST")
token = None
try:
    j = json.loads(body); token = j.get("access_token")
except Exception: j = {}
print("token request HTTP", st, "| access_token:", bool(token))
if not token:
    print("error:", scrub(j.get("error")), "|", scrub(j.get("error_description"))); raise SystemExit
base = cfg["iu"].rstrip("/") + "/" + cfg["ti"].strip("/") + "/BIRST/InforBirstRestAPI"
NAMEKEYS = ["name","spaceName","workflowName","Name","SpaceName","WorkflowName","displayName","label"]
for p in ["/spaces", "/workflows"]:
    st, body = req(base + p, headers={"Authorization":"Bearer " + token, "Accept":"application/json"})
    print(f"\n== GET {p}: HTTP {st} ==")
    try: j = json.loads(body)
    except Exception:
        print("non-JSON body:", scrub(body.decode(errors="replace"))); continue
    items = None
    if isinstance(j, list): items = j
    elif isinstance(j, dict):
        for k, v in j.items():
            if isinstance(v, list): items = v; print("(list under key:", k + ")"); break
    if items is None:
        print("no list in response; top-level keys:", list(j.keys()) if isinstance(j, dict) else type(j).__name__)
        if st and st >= 400: print("body:", scrub(json.dumps(j)))
        continue
    print("count:", len(items))
    if items and isinstance(items[0], dict): print("item keys:", sorted(items[0].keys()))
    for it in items:
        n = next((it[k] for k in NAMEKEYS if isinstance(it, dict) and it.get(k)), None) if isinstance(it, dict) else it
        print("  -", scrub(n if n is not None else "(no name field)"))
