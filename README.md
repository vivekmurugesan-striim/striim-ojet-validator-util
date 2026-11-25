# OJet Table Instantiation Validator

Checks, before an OJet application is started, that every table configured in the
application has completed table instantiation in Oracle. A table missing from
instantiation makes the application fail with:

```
ORA-26696: no OJet data dictionary for object with number: <> and source version number <> from source database
```

## How it works

| List | Source | How |
|------|--------|-----|
| **A** – instantiated tables | Oracle primary | `select table_name,table_owner,to_char(scn),timestamp from dba_capture_prepared_tables;` run through `sqlplus` |
| **B** – configured tables | Striim OJet application | `mon <app>;` run through the Striim REST API |

The script reports every table in **B** that is not in **A**. Those tables must be
instantiated before the application is started.

Entries with wildcards (`%` or `*`) in B count as covered if at least one table in A matches them.

## Requirements

- Python 3.8+ (standard library only, no packages to install)
- `sqlplus` (Oracle Instant Client) with the wallet configured for TCPS
- Network access to the Striim REST endpoint

## Input parameters

Provided as a JSON file (or an inline JSON string) via `--input`. See [params.sample.json](params.sample.json).

| Key | Required | Description |
|-----|----------|-------------|
| `striim_username` | yes | Striim user |
| `striim_password` | yes | Striim password |
| `ojet_application_name` | yes | OJet application, e.g. `admin.OJetApp` |
| `Oracle_username` | yes | Oracle user, e.g. `<user_name>` |
| `Oracle_tcps_url` | yes | TCPS connect string, including `SSL_SERVER_CERT_DN` and `WALLET_LOCATION` |
| `striim_url` | no | Striim base URL, default `http://localhost:9080` |
| `Oracle_password` | no | If absent, uses env var `ORACLE_PASSWORD`, otherwise prompts |
| `sqlplus_path` | no | Path to `sqlplus`, default `sqlplus` from `PATH` |

## Usage

```bash
python3 ojet_table_validator.py --input params.json
python3 ojet_table_validator.py --input params.json --json    # machine-readable output
```

Offline mode (no Oracle or Striim needed), useful for testing:

```bash
python3 ojet_table_validator.py --input params.json \
    --list-a-file sqlplus_output.txt --list-b-file mon_output.txt
```

### Example output

```
Instantiated in Oracle (List A): 2
Configured in OJet app (List B): 2

1 table(s) MISSING table instantiation:
  MFDSP_ARC.MISSING_ONE
```

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | All configured tables are instantiated |
| 1 | One or more tables are missing |
| 2 | Error (bad input, `sqlplus` or Striim failure, no tables found) |

This makes the script usable as a pre-start gate:

```bash
python3 ojet_table_validator.py --input params.json && start_ojet_app
```

## Security notes

- The Oracle password is sent to `sqlplus` on stdin, so it never appears in the process list.
- Prefer `ORACLE_PASSWORD` or the prompt over storing `Oracle_password` in the JSON file.
- Restrict permissions on any file holding real credentials (`chmod 600 params.json`).

## Tests

```bash
python3 -m unittest -v
```

## Known assumptions

- The Striim login is `POST /security/authenticate` and the command goes to `POST /api/v2/tungsten`.
- The `mon` output is assumed to contain table names as `OWNER.TABLE`. The script looks under
  any field with "table" in its name, and otherwise scans the whole response. If your output
  differs, adjust `extract_tables_from_mon` in [ojet_table_validator.py](ojet_table_validator.py).

## Files

- [ojet_table_validator.py](ojet_table_validator.py) – the script
- [test_ojet_table_validator.py](test_ojet_table_validator.py) – unit tests
- [params.sample.json](params.sample.json) – sample input
- [PLAN.md](PLAN.md) – implementation plan
