import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from jpocrdate import check_date, fix_text  # noqa: E402
from jpocrdate.server import handle  # noqa: E402


class TestCheckDate(unittest.TestCase):
    def test_reiwa_misread(self):
        r = check_date("今和6年3月15曰")
        self.assertEqual((r["status"], r["date"], r["iso"]), ("fixed", "令和6年3月15日", "2024-03-15"))

    def test_other_reiwa_lookalikes(self):
        for s in ("合和6年1月1日", "命和6年1月1日", "冷和6年1月1日", "令私6年1月1日", "令利6年1月1日"):
            self.assertEqual(check_date(s)["iso"], "2024-01-01", s)

    def test_heisei_showa(self):
        self.assertEqual(check_date("平戒31年4月30日")["iso"], "2019-04-30")
        self.assertEqual(check_date("半成2年1月1日")["iso"], "1990-01-01")
        self.assertEqual(check_date("照和64年1月7日")["iso"], "1989-01-07")

    def test_gannen(self):
        self.assertEqual(check_date("令和元年5月1日")["status"], "ok")
        r = check_date("今和兀年5月1日")
        self.assertEqual((r["date"], r["iso"]), ("令和元年5月1日", "2019-05-01"))

    def test_era_boundaries_are_not_guessed(self):
        self.assertEqual(check_date("平成31年5月1日")["status"], "invalid")
        self.assertEqual(check_date("照和64年1月8日")["status"], "invalid")
        self.assertEqual(check_date("令和元年4月30日")["status"], "invalid")

    def test_impossible_dates(self):
        self.assertEqual(check_date("今和6年2月30日")["status"], "invalid")
        self.assertEqual(check_date("令和6年13月1日")["status"], "invalid")
        self.assertEqual(check_date("今和6年2月29日")["iso"], "2024-02-29")  # leap year
        self.assertEqual(check_date("今和5年2月29日")["status"], "invalid")

    def test_western_digits(self):
        r = check_date("2O24年l月5日")
        self.assertEqual((r["date"], r["iso"]), ("2024年1月5日", "2024-01-05"))
        self.assertEqual(check_date("２０２５年１２月３日")["iso"], "2025-12-03")

    def test_year_month_only(self):
        self.assertEqual(check_date("今和 6 年 4 月")["iso"], "2024-04")
        self.assertEqual(check_date("令和元年5月")["status"], "ok")
        self.assertEqual(check_date("令和元年4月")["status"], "invalid")

    def test_correct_dates_untouched(self):
        for s in ("令和6年3月15日", "平成元年1月8日", "2024年12月1日"):
            self.assertEqual(check_date(s)["status"], "ok", s)

    def test_not_a_date(self):
        for s in ("今年3月", "R6.3.15", "合計2024年", ""):
            self.assertEqual(check_date(s)["status"], "not_a_date", s)


class TestFixText(unittest.TestCase):
    def test_invoice(self):
        src = "請求日: 今和6年3月15曰\n支払期限: 今和6年4月30日\n発行 2O24年l2月1日"
        r = fix_text(src)
        self.assertEqual(r["text"], "請求日: 令和6年3月15日\n支払期限: 令和6年4月30日\n発行 2024年12月1日")
        self.assertEqual([c["iso"] for c in r["changes"]], ["2024-03-15", "2024-04-30", "2024-12-01"])
        self.assertEqual(r["flags"], [])

    def test_flags_without_change(self):
        r = fix_text("契約日 今和6年2月30日 です")
        self.assertEqual(r["text"], "契約日 今和6年2月30日 です")
        self.assertEqual(len(r["flags"]), 1)
        self.assertEqual(r["flags"][0]["reason"], "day does not exist")

    def test_plain_text_kept(self):
        src = "今年の合計は12345円。今日は晴れ。番号12024年1月"
        r = fix_text(src)
        self.assertEqual(r["text"], src)
        self.assertEqual(r["changes"], [])

    def test_offsets_point_at_source(self):
        src = "xx今和6年3月15曰yy"
        c = fix_text(src)["changes"][0]
        self.assertEqual(src[c["start"]:c["end"]], "今和6年3月15曰")


class TestServer(unittest.TestCase):
    def call(self, method, params=None, mid=1):
        return handle({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})

    def test_initialize_and_list(self):
        r = self.call("initialize", {"protocolVersion": "2025-06-18"})["result"]
        self.assertEqual(r["protocolVersion"], "2025-06-18")
        names = [t["name"] for t in self.call("tools/list")["result"]["tools"]]
        self.assertEqual(names, ["jp_ocr_fix_dates", "jp_ocr_check_date"])

    def test_call(self):
        r = self.call("tools/call", {"name": "jp_ocr_check_date", "arguments": {"date": "今和6年3月15曰"}})["result"]
        self.assertFalse(r["isError"])
        self.assertEqual(r["structuredContent"]["iso"], "2024-03-15")

    def test_bad_args(self):
        r = self.call("tools/call", {"name": "jp_ocr_fix_dates", "arguments": {}})["result"]
        self.assertTrue(r["isError"])
        self.assertIn("error", self.call("tools/call", {"name": "nope"}))
        self.assertIsNone(handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_stdio(self):
        msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                 "params": {"name": "jp_ocr_fix_dates", "arguments": {"text": "平戒31年4月30日"}}}]
        p = subprocess.run([sys.executable, "-m", "jpocrdate.server"], cwd=ROOT, capture_output=True,
                           input="\n".join(json.dumps(m) for m in msgs) + "\n", text=True, encoding="utf-8", timeout=30)
        lines = [json.loads(x) for x in p.stdout.splitlines()]
        self.assertEqual(lines[1]["result"]["structuredContent"]["text"], "平成31年4月30日")


if __name__ == "__main__":
    unittest.main()
