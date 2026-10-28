# JP OCR Date Fix

**Repair Japanese dates that OCR broke (`今和6年3月15曰` → `令和6年3月15日`), and only when the calendar confirms the result.**

OCR often misreads the era name 令和 as 今和 or 合和, 日 as 曰, and 0/1 as O/l. One public test of a document parser on Japanese PDFs found the 令→今 error on roughly all OCR-processed pages ([source](https://dev.to/elvisyao007/does-a-chinese-document-parser-actually-work-on-japanese-pdfs-i-measured-it-and-the-answer-is-2f5)). An AI that reads that text then extracts a date that does not exist, or guesses.

This tool fixes those spans with fixed rules and checks each result:

- the span must have a full date shape: era + year + 年 + month + 月 (+ day + 日), or YYYY年M月(D日)
- characters are mapped through a fixed look-alike table (`今合命冷→令`, `戒威→成`, `照→昭`, `曰目→日`, `O→0`, `l|→1`, …)
- the repaired date must exist and fall inside its era (平成31年4月30日 is valid, 平成31年5月1日 is not)
- if it cannot be confirmed, the text is left as it is and the span is returned in `flags`

Python standard library only. No network. MIT.

## Use

```bash
python -m jpocrdate scan.txt            # repaired text to stdout, changes to stderr
python -m jpocrdate scan.txt --json     # {"text", "changes", "flags"}
```

```python
from jpocrdate import fix_text, check_date
check_date("平戒31年4月30日")
# {'input': '平戒31年4月30日', 'status': 'fixed', 'date': '平成31年4月30日', 'iso': '2019-04-30'}
check_date("平成31年5月1日")
# {'input': '平成31年5月1日', 'status': 'invalid', 'reason': 'date is outside 平成'}
```

### As an MCP server (for AI agents)

```json
{"mcpServers": {"jp-ocr-date-fix": {"command": "python", "args": ["-m", "jpocrdate.server"], "cwd": "/path/to/jp-ocr-date-fix"}}}
```

Tools (read-only):

| Tool | Input | Returns |
|---|---|---|
| `jp_ocr_fix_dates` | `text` | repaired `text`, `changes` (start/end/before/after/iso), `flags` |
| `jp_ocr_check_date` | `date` | `status`: ok / fixed / invalid / not_a_date, `date`, `iso` |

## Scope and limits

- Eras: 明治, 大正, 昭和, 平成, 令和. Abbreviations such as `R6.3.15` or `H31/4/30` are not handled yet
- Only dates are repaired. Company names and amounts are out of scope (see JaPOC for company-name correction)
- The look-alike table is hand-made from common OCR confusions. It is not learned from data, and it will miss some errors
- Tests: `python -m unittest discover -s tests` (18 tests)

---

## 日本語

OCRで崩れた日本の日付(`今和6年3月15曰` など)を、決まったルールで直します。直した結果が暦に実在し、元号の期間内にあるときだけ直します。確かめられないものは直さずに `flags` で知らせます(推測しません)。

- 対応: 明治・大正・昭和・平成・令和、元年、全角数字、年月だけの日付
- 外部通信なし・Python標準ライブラリのみ・MIT
- AIエージェントからは MCP サーバー(`python -m jpocrdate.server`)として使えます
