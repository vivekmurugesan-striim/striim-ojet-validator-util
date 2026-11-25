#!/usr/bin/env python3
"""Validate that every table configured in an OJet application has completed
table instantiation in Oracle (dba_capture_prepared_tables).

List A = tables instantiated in Oracle; List B = tables configured in the OJet app.
Reports List B tables missing from List A. Exit code: 0 ok, 1 missing, 2 error.
"""
import argparse
import fnmatch
import getpass
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

REQUIRED_KEYS = ["striim_username", "striim_password", "ojet_application_name",
                 "Oracle_username", "Oracle_tcps_url"]

SQL_SCRIPT = """set pages 200 lines 200
set feedback off
col table_name for A40
col table_owner for A25
col scn for A30
col timestamp for A30
select table_name,table_owner,to_char(scn),timestamp from dba_capture_prepared_tables;
exit
"""

TABLE_RE = re.compile(r"[A-Za-z0-9_$#\"%*]+\.[A-Za-z0-9_$#\"%*]+")


class ValidationError(Exception):
    pass


# ---------------------------------------------------------------- input
def load_input(arg):
    text = arg
    if os.path.isfile(arg):
        with open(arg) as f:
            text = f.read()
    try:
        cfg = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValidationError(f"Invalid input JSON: {e}")
    missing = [k for k in REQUIRED_KEYS if not cfg.get(k)]
    if missing:
        raise ValidationError(f"Missing input parameter(s): {', '.join(missing)}")
    return cfg


# ---------------------------------------------------------------- List A
def parse_sqlplus_output(output):
    """Parse the sqlplus output into a set of OWNER.TABLE names."""
    errors = [l for l in output.splitlines() if re.match(r"\s*(ORA|SP2)-\d+", l)]
    if errors:
        raise ValidationError("sqlplus reported errors:\n" + "\n".join(errors))
    tables = set()
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        name, owner = parts[0], parts[1]
        if name.upper() == "TABLE_NAME" or set(line.strip()) <= {"-", " "}:
            continue
        # SCN column is numeric; guards against stray text lines
        if not parts[2].isdigit():
            continue
        tables.add(f"{owner}.{name}".upper())
    return tables


def fetch_list_a(cfg):
    password = cfg.get("Oracle_password") or os.environ.get("ORACLE_PASSWORD")
    if not password:
        password = getpass.getpass(f"Oracle password for {cfg['Oracle_username']}: ")
    sqlplus = cfg.get("sqlplus_path", "sqlplus")
    connect = f'{cfg["Oracle_username"]}/{password}"{cfg["Oracle_tcps_url"]}"'
    # Credentials go via stdin ("-S /nolog" + CONNECT) so they never appear in `ps`.
    script = f"connect {connect}\n{SQL_SCRIPT}"
    try:
        proc = subprocess.run([sqlplus, "-S", "/nolog"], input=script, text=True,
                              capture_output=True, timeout=120)
    except FileNotFoundError:
        raise ValidationError(f"sqlplus not found ({sqlplus}); set sqlplus_path")
    except subprocess.TimeoutExpired:
        raise ValidationError("sqlplus timed out")
    return parse_sqlplus_output(proc.stdout + proc.stderr)


# ---------------------------------------------------------------- List B
def _request(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read().decode()
    except urllib.error.HTTPError as e:
        raise ValidationError(f"Striim REST {url} failed: HTTP {e.code} {e.reason}")
    except urllib.error.URLError as e:
        raise ValidationError(f"Striim REST {url} unreachable: {e.reason}")


def run_mon(cfg):
    base = cfg.get("striim_url", "http://localhost:9080").rstrip("/")
    body = urllib.parse.urlencode({"username": cfg["striim_username"],
                                   "password": cfg["striim_password"]}).encode()
    auth = _request(f"{base}/security/authenticate", body,
                    {"Content-Type": "application/x-www-form-urlencoded"})
    try:
        token = json.loads(auth)["token"]
    except (ValueError, KeyError):
        raise ValidationError("Striim authentication did not return a token")
    cmd = f"mon {cfg['ojet_application_name']};"
    return _request(f"{base}/api/v2/tungsten", cmd.encode(),
                    {"Authorization": f"STRIIM-TOKEN {token}", "Content-Type": "text/plain"})


def _walk(obj, key_hint=False):
    """Yield strings found under keys that mention 'table' (any depth)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk(v, key_hint or "table" in str(k).lower())
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v, key_hint)
    elif isinstance(obj, str) and key_hint:
        yield obj


def extract_tables_from_mon(text):
    """Extract OWNER.TABLE entries (wildcards allowed) from `mon <app>` output."""
    chunks = None
    try:
        chunks = list(_walk(json.loads(text)))
    except ValueError:
        pass
    if not chunks:  # plain text or no table-keyed fields: scan everything
        chunks = [text]
    tables = set()
    for chunk in chunks:
        for m in TABLE_RE.findall(chunk):
            tables.add(m.replace('"', "").upper())
    return tables


# ---------------------------------------------------------------- compare
def find_missing(list_a, list_b):
    a = {t.upper() for t in list_a}
    missing = []
    for entry in sorted(list_b):
        pat = entry.upper().replace("%", "*")
        if "*" in pat:
            ok = any(fnmatch.fnmatchcase(t, pat) for t in a)
        else:
            ok = pat in a
        if not ok:
            missing.append(entry)
    return missing


# ---------------------------------------------------------------- main
def read_lines(path):
    with open(path) as f:
        return f.read()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="JSON file or inline JSON with the parameters")
    ap.add_argument("--json", action="store_true", help="emit JSON result")
    ap.add_argument("--list-a-file", help="offline: file holding sqlplus output (skips Oracle)")
    ap.add_argument("--list-b-file", help="offline: file holding mon output (skips Striim)")
    args = ap.parse_args(argv)
    try:
        cfg = load_input(args.input)
        list_a = (parse_sqlplus_output(read_lines(args.list_a_file))
                  if args.list_a_file else fetch_list_a(cfg))
        list_b = (extract_tables_from_mon(read_lines(args.list_b_file))
                  if args.list_b_file else extract_tables_from_mon(run_mon(cfg)))
    except (ValidationError, OSError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    if not list_b:
        print("ERROR: no tables found in OJet application output; check the app name "
              "or adjust extract_tables_from_mon", file=sys.stderr)
        return 2
    missing = find_missing(list_a, list_b)
    if args.json:
        print(json.dumps({"instantiated_count": len(list_a), "configured_count": len(list_b),
                          "missing": missing}, indent=2))
    else:
        print(f"Instantiated in Oracle (List A): {len(list_a)}")
        print(f"Configured in OJet app (List B): {len(list_b)}")
        if missing:
            print(f"\n{len(missing)} table(s) MISSING table instantiation:")
            for t in missing:
                print(f"  {t}")
        else:
            print("\nOK: all configured tables have completed table instantiation.")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
