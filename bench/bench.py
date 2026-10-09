"""Замер времени ответа операций контракта.

    python bench/bench.py --label small        # после: manage.py seed --size small
    python bench/bench.py --label work         # после: manage.py seed --size work

Свойства замера:
* все запросы — под учётной записью demo, после входа через POST /api/login;
* перед каждой серией — прогрев (--warmup запросов), в расчёт не входит;
* серия — --reps запросов подряд, по одному, без параллелизма;
* время — time.perf_counter() вокруг запроса на стороне клиента;
* из заголовков ответа берутся X-DB-Queries и X-DB-Time-ms (число запросов
  к базе и их суммарное время) и X-App-Time-ms (время внутри сервиса).

Результат: bench/results/<label>.json с сырыми значениями по каждому повтору.
"""
import argparse
import json
import platform
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

import psycopg
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import Config  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"


def percentile(values, p):
    """Процентиль с линейной интерполяцией (как numpy.percentile по умолчанию)."""
    data = sorted(values)
    k = (len(data) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(data) - 1)
    return data[lo] + (data[hi] - data[lo]) * (k - lo)


def pick_params(conn, n_write):
    """Параметры операций выбираются по данным одинаковым правилом на любом объёме."""
    total = conn.execute("SELECT count(*) FROM loan").fetchone()[0]
    loan_id, reader_id, book_id = conn.execute(
        "SELECT l.id, l.reader_id, c.book_id FROM loan l JOIN copy c ON c.id = l.copy_id "
        "ORDER BY l.id OFFSET %s LIMIT 1", (total // 2,)).fetchone()
    today = Config.APP_TODAY or datetime.now().date().isoformat()
    readers = [r[0] for r in conn.execute(
        """SELECT r.id FROM reader r
           WHERE NOT EXISTS (SELECT 1 FROM loan l WHERE l.reader_id = r.id
                             AND l.returned_at IS NULL AND l.due_at < %s)
             AND (SELECT count(*) FROM loan l WHERE l.reader_id = r.id
                  AND l.returned_at IS NULL) < 4
           ORDER BY r.id LIMIT %s""", (today, n_write))]
    copies = [r[0] for r in conn.execute(
        """SELECT c.id FROM copy c
           WHERE NOT EXISTS (SELECT 1 FROM loan l WHERE l.copy_id = c.id AND l.returned_at IS NULL)
           ORDER BY c.id LIMIT %s""", (n_write,))]
    if len(readers) < n_write or len(copies) < n_write:
        raise SystemExit("Недостаточно свободных экземпляров или читателей для операций записи")
    return {"loan_id": loan_id, "reader_id": reader_id, "book_id": book_id,
            "write_pairs": list(zip(readers, copies))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--label", required=True)
    parser.add_argument("--reps", type=int, default=30)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--login", default="demo")
    parser.add_argument("--password", default="demo")
    args = parser.parse_args()

    n_write = args.reps + args.warmup
    with psycopg.connect(Config.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://"),
                         options=f"-csearch_path={Config.DB_SCHEMA}") as conn:
        params = pick_params(conn, n_write)
        counts = {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                  for t in ("reader", "book", "copy", "loan")}

    base = args.base_url
    credentials = {"login": args.login, "password": args.password}
    http = requests.Session()
    assert http.post(f"{base}/api/login", json=credentials).status_code == 200

    created = []
    pairs = iter(params["write_pairs"])

    def login_op():
        return requests.post(f"{base}/api/login", json=credentials)

    def logout_prepare():
        s = requests.Session()
        s.post(f"{base}/api/login", json=credentials)
        return s

    def issue():
        reader_id, copy_id = next(pairs)
        r = http.post(f"{base}/api/loans", json={"reader_id": reader_id, "copy_id": copy_id})
        if r.status_code == 201:
            created.append(r.json()["id"])
        return r

    returns = iter(created)  # итератор читает список по мере наполнения

    def give_back():
        return http.post(f"{base}/api/loans/{next(returns)}/return", json={})

    p = params
    operations = [
        ("POST /api/login", 200, login_op, None),
        ("GET /api/loans", 200, lambda: http.get(f"{base}/api/loans?page=1&size=20"), None),
        ("GET /api/loans?status=overdue", 200,
         lambda: http.get(f"{base}/api/loans?status=overdue&page=1&size=20"), None),
        ("GET /api/loans?q=…", 200, lambda: http.get(f"{base}/api/loans?q=Тихий&page=1&size=20"), None),
        ("GET /api/loans/{id}", 200, lambda: http.get(f"{base}/api/loans/{p['loan_id']}"), None),
        ("GET /api/readers?q=…", 200, lambda: http.get(f"{base}/api/readers?q=Орлов&page=1&size=20"), None),
        ("GET /api/readers/{id}", 200, lambda: http.get(f"{base}/api/readers/{p['reader_id']}"), None),
        ("GET /api/books", 200, lambda: http.get(f"{base}/api/books?page=1&size=20"), None),
        ("GET /api/books/{id}", 200, lambda: http.get(f"{base}/api/books/{p['book_id']}"), None),
        ("GET /api/summary", 200, lambda: http.get(f"{base}/api/summary"), None),
        ("POST /api/loans", 201, issue, None),
        ("POST /api/loans/{id}/return", 200, give_back, None),
        ("POST /api/logout", 204, None, logout_prepare),
    ]

    results = {}
    for name, expected, call, prepare in operations:
        rows = []
        for i in range(args.warmup + args.reps):
            if prepare is not None:  # подготовка вне замера (вход перед выходом)
                session = prepare()
                start = time.perf_counter()
                r = session.post(f"{base}/api/logout")
            else:
                start = time.perf_counter()
                r = call()
            elapsed = (time.perf_counter() - start) * 1000
            if r.status_code != expected:
                raise SystemExit(f"{name}: ожидался {expected}, получен {r.status_code}: {r.text[:200]}")
            if i < args.warmup:
                continue
            rows.append({
                "ms": elapsed,
                "app_ms": float(r.headers.get("X-App-Time-ms", "nan")),
                "db_ms": float(r.headers.get("X-DB-Time-ms", "nan")),
                "queries": int(r.headers.get("X-DB-Queries", "0")),
                "bytes": len(r.content),
            })
        ms = [x["ms"] for x in rows]
        results[name] = {
            "p50": statistics.median(ms), "p95": percentile(ms, 95), "max": max(ms),
            "mean": statistics.fmean(ms),
            "app_p50": statistics.median(x["app_ms"] for x in rows),
            "db_p50": statistics.median(x["db_ms"] for x in rows),
            "queries_p50": statistics.median(x["queries"] for x in rows),
            "bytes_p50": statistics.median(x["bytes"] for x in rows),
            "runs": rows,
        }
        print(f"{name:<32} p50 {results[name]['p50']:9.2f}  p95 {results[name]['p95']:9.2f}  "
              f"max {results[name]['max']:9.2f}  БД {results[name]['db_p50']:8.2f} мс  "
              f"запросов {results[name]['queries_p50']:g}")

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{args.label}.json"
    out.write_text(json.dumps({
        "label": args.label,
        "started": datetime.now().isoformat(timespec="seconds"),
        "reps": args.reps, "warmup": args.warmup, "login": args.login,
        "counts_before": counts, "added_loans": len(created),
        "params": {k: v for k, v in params.items() if k != "write_pairs"},
        "machine": {"python": platform.python_version(), "platform": platform.platform()},
        "operations": results,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Сохранено: {out}")


if __name__ == "__main__":
    main()
