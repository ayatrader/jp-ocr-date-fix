"""MCP server (stdio, JSON-RPC 2.0). Python standard library only, no network.

Start: python -m jpocrdate.server
"""
import json
import sys

from . import __version__
from .fix import check_date, fix_text

PROTOCOLS = ["2025-06-18", "2025-03-26", "2024-11-05"]
RO = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}

TOOLS = [
    {
        "name": "jp_ocr_fix_dates",
        "title": "Repair Japanese dates in OCR text",
        "annotations": RO,
        "description": ("Find Japanese dates in OCR output (e.g. '今和6年3月15曰', '2O24年l月5日') and repair OCR look-alike "
                        "characters. A fix is applied only when the repaired date exists on the calendar and inside the era "
                        "(令和/平成/昭和/大正/明治). Returns the repaired text, every change with its ISO date, and flags for "
                        "spans that look like dates but cannot be confirmed. Use it before extracting dates from scanned "
                        "Japanese invoices, forms or PDFs. OCRで崩れた和暦・日付を暦で確かめて直す。"),
        "inputSchema": {"type": "object", "properties": {
            "text": {"type": "string", "description": "OCR text (Japanese)"}}, "required": ["text"]},
    },
    {
        "name": "jp_ocr_check_date",
        "title": "Check one Japanese date",
        "annotations": RO,
        "description": ("Check one date string. status: ok (already correct), fixed (OCR look-alikes repaired; see date/iso), "
                        "invalid (the date does not exist, e.g. 平成31年5月1日; nothing is guessed), not_a_date."),
        "inputSchema": {"type": "object", "properties": {
            "date": {"type": "string"}}, "required": ["date"]},
    },
]


def _str_arg(args, key):
    v = args.get(key)
    if not isinstance(v, str):
        raise ValueError(f"'{key}' must be a string")
    return v


HANDLERS = {
    "jp_ocr_fix_dates": lambda a: fix_text(_str_arg(a, "text")),
    "jp_ocr_check_date": lambda a: check_date(_str_arg(a, "date")),
}


def handle(msg):
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if mid is None:
        return None
    try:
        if method == "initialize":
            want = params.get("protocolVersion")
            result = {"protocolVersion": want if want in PROTOCOLS else PROTOCOLS[0],
                      "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": "jp-ocr-date-fix", "version": __version__},
                      "instructions": "When Japanese OCR text contains dates, run jp_ocr_fix_dates before reading them. It never guesses: unconfirmed spans come back in flags."}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            name = params.get("name")
            if name not in HANDLERS:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"Unknown tool: {name}"}}
            try:
                out = HANDLERS[name](params.get("arguments") or {})
                result = {"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False)}],
                          "structuredContent": out, "isError": False}
            except ValueError as e:
                result = {"content": [{"type": "text", "text": str(e)}], "isError": True}
        else:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}}
        return {"jsonrpc": "2.0", "id": mid, "result": result}
    except Exception as e:  # keep the server alive
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": f"Internal error: {e}"}}


def main():
    for s in (sys.stdin, sys.stdout):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}) + "\n")
            sys.stdout.flush()
            continue
        resp = handle(msg) if isinstance(msg, dict) else None
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
