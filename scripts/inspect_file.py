"""Print the structure of a downloaded POWER file (no values) so a parsing problem can be diagnosed
without sharing the whole file. Safe to paste the output."""
import json
import sys
from pathlib import Path


def main(argv=None):
    argv = argv or sys.argv[1:]
    if len(argv) != 1:
        print("usage: python scripts/inspect_file.py <file.json|file.csv>")
        return 2
    p = Path(argv[0])
    text = p.read_text(encoding="utf-8", errors="replace")
    print(f"file: {p.name}   bytes: {len(text)}")
    if p.suffix.lower() == ".json":
        d = json.loads(text)
        print("top level keys:", list(d))
        print("header:", json.dumps(d.get("header"), indent=1)[:1500])
        print("parameters block:", json.dumps(d.get("parameters"), indent=1)[:2500])
        print("geometry:", d.get("geometry"))
        pr = d.get("properties", {}).get("parameter", {})
        for v, s in pr.items():
            keys = list(s)
            print(f"  {v}: {len(keys)} keys, first {keys[:2]}, last {keys[-2:]}")
    else:
        head = text.split("-END HEADER-")[0] if "-END HEADER-" in text else text[:1500]
        print("CSV header block:\n" + head[:2500])
        body = text.split("-END HEADER-")[-1].strip().splitlines()
        print("table columns:", body[0] if body else "(empty)")
        print("table rows:", max(len(body) - 1, 0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
