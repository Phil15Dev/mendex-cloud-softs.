import csv
import io
from datetime import datetime

from fastapi.responses import Response

from .templating import EAT


def safe(value) -> str:
    """Neutralise spreadsheet formulas typed by customers (= + - @)."""
    v = "" if value is None else str(value)
    return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


def csv_response(prefix: str, header: list, rows) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    stamp = datetime.now(EAT).strftime("%Y-%m-%d")
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",  # BOM so Excel opens it
                    headers={"Content-Disposition": f'attachment; filename="{prefix}-{stamp}.csv"'})
