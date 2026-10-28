"""JP OCR Date Fix: repair Japanese dates broken by OCR (今和6年 -> 令和6年), only when the calendar confirms it."""
__version__ = "0.1.0"
from .fix import fix_text, check_date  # noqa: F401
