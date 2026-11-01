# adg-birst-automation

Home of ADG's Birst deploy runner and supporting scripts for the Infor Birst REST API via the ION API gateway.

## Scripts

- `birst_list.py` — read-only check: gets an OAuth token (password grant) and lists Birst spaces and workflows.

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
