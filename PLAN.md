# OJet table-instantiation validator – plan

## Requirement summary (from OJet-Dict-build-Comparison.pdf)
Before the OJet app starts, every table configured in the app (List B) must appear in
Oracle `dba_capture_prepared_tables` (List A). Missing tables cause
`ORA-26696: no OJet data dictionary for object ...`. Report List B − List A.

## Inputs
JSON: `striim_username`, `striim_password`, `ojet_application_name`, `Oracle_username`, `Oracle_tcps_url`.
Extras (not in spec, optional): `striim_url` (default `http://localhost:9080`), `Oracle_password`
(else env `ORACLE_PASSWORD`, else prompt), `sqlplus_path` (default `sqlplus`).

## Steps
1. **Load/validate input** – `--input file.json` (or inline JSON); fail on missing keys.
2. **List A** – run sqlplus with `user/pwd"tcps_url"` (silent, `set pages 200 lines 200`, column
   formats, the spec's query) via stdin; password passed on stdin, never on the command line.
   Parse rows: skip header/dashes/blank; first two tokens = TABLE_NAME, TABLE_OWNER → set of `OWNER.TABLE`.
   Surface `ORA-`/`SP2-` errors.
3. **List B** – Striim REST: `POST /security/authenticate` → token; `POST /api/v2/tungsten`
   with `mon <app>;`. Extract configured tables from the response (JSON-aware, falls back to
   text); entries `OWNER.TABLE`, wildcards (`%`, `*`) supported.
4. **Compare** – normalize to upper case; B entries without match in A are missing
   (wildcards match any A entry with that pattern; a wildcard matching nothing is missing).
5. **Report** – human-readable list + `--json` output; exit code 0 = all covered,
   1 = missing tables, 2 = error. Also `--list-a-file` / `--list-b-file` offline modes for testing.
6. **Tests** – unit tests for the parsers and comparison with the PDF's sample output.

## Assumptions to confirm
- `mon <app>` output contains table names as `OWNER.TABLE`; adjust `extract_tables_from_mon` if the real format differs.
