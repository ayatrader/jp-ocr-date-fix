"""CLI: python -m jpocrdate input.txt [--json]  (reads stdin when no file is given)."""
import argparse
import json
import sys

from .fix import fix_text


def main(argv=None):
    ap = argparse.ArgumentParser(prog="jpocrdate", description="Repair Japanese dates broken by OCR")
    ap.add_argument("file", nargs="?")
    ap.add_argument("--json", action="store_true", help="print changes and flags as JSON")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    text = open(a.file, encoding="utf-8").read() if a.file else sys.stdin.read()
    r = fix_text(text)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        sys.stdout.write(r["text"])
        for c in r["changes"]:
            print(f"# fixed {c['before']} -> {c['after']} ({c['iso']})", file=sys.stderr)
        for f in r["flags"]:
            print(f"# check {f['text']}: {f['reason']}", file=sys.stderr)


if __name__ == "__main__":
    main()
