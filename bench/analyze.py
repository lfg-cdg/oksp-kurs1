"""Сводит результаты двух серий в таблицы (Markdown) и графики (PNG).

    python bench/analyze.py      # читает results/small.json и results/work.json
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

RES = Path(__file__).resolve().parent / "results"
BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
# Операции, чья медиана при росте данных выросла меньше чем в 1,5 раза, из
# дальнейшего рассмотрения исключаются (порог выбран по разбросу повторных серий).
GROWTH_THRESHOLD = 1.5


def excluded(small, work):
    return {n for n in small["operations"]
            if work["operations"][n]["p50"] / small["operations"][n]["p50"] < GROWTH_THRESHOLD}


def load():
    small = json.loads((RES / "small.json").read_text(encoding="utf-8"))
    work = json.loads((RES / "work.json").read_text(encoding="utf-8"))
    return small, work


def fmt(x):
    return f"{x:.1f}".replace(".", ",")


def tables(small, work):
    s_ops, w_ops = small["operations"], work["operations"]
    EXCLUDED = excluded(small, work)
    lines = ["| Операция | p50 малое | p95 малое | max малое | p50 рабочее | p95 рабочее | max рабочее | Рост p50 |",
             "|---|---|---|---|---|---|---|---|"]
    for name in s_ops:
        s, w = s_ops[name], w_ops[name]
        lines.append(f"| {name} | {fmt(s['p50'])} | {fmt(s['p95'])} | {fmt(s['max'])} | "
                     f"{fmt(w['p50'])} | {fmt(w['p95'])} | {fmt(w['max'])} | ×{fmt(w['p50'] / s['p50'])} |")
    lines += ["", "| Операция | Время операции, мс | В базе, мс | В коде, мс | Доля базы | Запросов | Мс на запрос |",
              "|---|---|---|---|---|---|---|"]
    for name, w in w_ops.items():
        if name in EXCLUDED:
            continue
        code = w["p50"] - w["db_p50"]
        lines.append(f"| {name} | {fmt(w['p50'])} | {fmt(w['db_p50'])} | {fmt(code)} | "
                     f"{w['db_p50'] / w['p50'] * 100:.0f} % | {w['queries_p50']:g} | "
                     f"{fmt(w['db_p50'] / max(w['queries_p50'], 1))} |")
    text = "\n".join(lines)
    (RES / "tables.md").write_text(text + "\n", encoding="utf-8")
    print(text)


def style(ax):
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=9, length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def chart_response(small, work):
    names = list(small["operations"])[::-1]
    s = [small["operations"][n]["p50"] for n in names]
    w = [work["operations"][n]["p50"] for n in names]
    fig, ax = plt.subplots(figsize=(8.6, 5.4), dpi=200)
    style(ax)
    y = range(len(names))
    for i in y:
        ax.plot([s[i], w[i]], [i, i], color="#c3c2b7", linewidth=2, zorder=1)
    ax.scatter(s, y, s=48, color=BLUE, edgecolor="white", linewidth=1.5, zorder=2,
               label=f"малое наполнение ({small['counts_before']['loan']} выдач)")
    ax.scatter(w, y, s=48, color=ORANGE, edgecolor="white", linewidth=1.5, zorder=3,
               label=f"рабочее наполнение ({work['counts_before']['loan']:,} выдач)".replace(",", " "))
    for i in y:
        ratio = w[i] / s[i]
        ax.text(max(s[i], w[i]) * 1.18, i, f"×{ratio:.1f}".replace(".", ","), va="center",
                fontsize=8.5, color=INK if ratio >= 3 else INK2,
                fontweight="bold" if ratio >= 3 else "normal")
    ax.set_xscale("log")
    ax.set_xlim(2, 3000)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.set_yticks(list(y), names, fontsize=9, color=INK)
    ax.set_xlabel("медиана времени ответа, мс (логарифмическая шкала)", color=INK2, fontsize=9)
    ax.legend(loc="lower right", frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(RES / "response_time.png")
    plt.close(fig)


def chart_split(small, work):
    skip = excluded(small, work)
    ops = {n: v for n, v in work["operations"].items() if n not in skip}
    names = sorted(ops, key=lambda n: ops[n]["p50"])
    db = [ops[n]["db_p50"] for n in names]
    code = [ops[n]["p50"] - ops[n]["db_p50"] for n in names]
    fig, ax = plt.subplots(figsize=(8.6, 4.8), dpi=200)
    style(ax)
    y = range(len(names))
    ax.barh(y, db, height=0.6, color=BLUE, edgecolor="white", linewidth=2, label="в базе данных")
    ax.barh(y, code, left=db, height=0.6, color=ORANGE, edgecolor="white", linewidth=2,
            label="в коде приложения и сети")
    for i, n in enumerate(names):
        total = db[i] + code[i]
        ax.text(total + 8, i, f"{total:.0f} мс · {ops[n]['queries_p50']:g} запр.",
                va="center", fontsize=8.5, color=INK2)
    ax.set_yticks(list(y), names, fontsize=9, color=INK)
    ax.set_xlim(0, max(d + c for d, c in zip(db, code)) * 1.3)
    ax.set_xlabel("медиана, мс (рабочее наполнение)", color=INK2, fontsize=9)
    ax.legend(loc="lower right", frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(RES / "db_split.png")
    plt.close(fig)


if __name__ == "__main__":
    small, work = load()
    tables(small, work)
    chart_response(small, work)
    chart_split(small, work)
    print('Исключены:', sorted(excluded(small, work)))
    print("Графики: results/response_time.png, results/db_split.png")
