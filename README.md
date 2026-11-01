# adg-birst-automation

Home of ADG's Birst deploy runner and supporting scripts for the Infor Birst REST API via the ION API gateway.

## Scripts

- `birst_list.py` — read-only check: gets an OAuth token (password grant) and lists Birst spaces and workflows.
- `birst_run_workflow.py` — runs one workflow by exact name (default `ADG_BASE-DEM_COMPUTE_20-USERS`) and polls it to a finished state. It stops if the name doesn't match exactly once or if a run is already in progress. It makes one `_runNow` POST with no retry and never cancels.
  - **Known issue:** `_runNow` is not working yet. An empty body without `Content-Type` returns 415; `{}` as JSON returns 400 `DEV-0400 "Workflow run now request is not valid."` The correct request body still needs to be confirmed from Infor's API docs.

Confirmed REST details: `/workflows` and `/workflows/{id}/runs` page with `offset`/`limit` (50 per page). A run's state is the latest entry in its `stateTransitions` map (e.g. `RUNNING`, `COMPLETED`). `GET /workflows/{id}/runs/{runId}` includes per-step and per-task results.

## Configuration

Credentials come from environment variables taken from the `.ionapi` file. Never commit them.

| Variable | .ionapi field |
|---|---|
| `IONAPI_TI` | ti (tenant) |
| `IONAPI_IU` | iu (ION API base URL) |
| `IONAPI_PU` | pu (SSO base URL) |
| `IONAPI_OT` | ot (token endpoint) |
| `IONAPI_CI` | ci (client id) |
| `IONAPI_CS` | cs (client secret) |
| `IONAPI_SAAK` | saak (service account access key) |
| `IONAPI_SASK` | sask (service account secret key) |

Birst REST base: `{iu}/{ti}/BIRST/InforBirstRestAPI` (confirmed: `GET /spaces`, `GET /workflows`).

Output redacts secrets, tokens and URLs.

## Run

```bash
python3 -I birst_list.py
```
