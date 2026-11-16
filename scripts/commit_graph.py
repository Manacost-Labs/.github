"""Render a yearly commit heatmap for all public repositories of the organization.

Data source: GET /repos/{org}/{repo}/stats/commit_activity (daily counts for the
last 52 weeks, default branch). Output: profile/assets/commit-activity.svg.
"""

import datetime as dt
import json
import os
import sys
import time
import urllib.request
from html import escape
from pathlib import Path

ORG = os.environ.get("ORG", "Manacost-Labs")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN", "")
OUT = Path(__file__).resolve().parent.parent / "profile" / "assets" / "commit-activity.svg"
SKIP = {".github"}

MONTHS = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
LEVELS = ["#172126", "#124146", "#196a6d", "#2aa29f", "#6fe0d6"]


def api(path):
    req = urllib.request.Request(f"https://api.github.com{path}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "commit-graph")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read()
        return resp.status, (json.loads(body) if body else None)


def public_repos():
    repos, page = [], 1
    while True:
        _, data = api(f"/orgs/{ORG}/repos?type=public&per_page=100&page={page}")
        if not data:
            return repos
        repos += [r["name"] for r in data if not r["archived"] and not r["fork"] and r["name"] not in SKIP]
        page += 1


def commit_activity(repo):
    for _ in range(8):
        status, data = api(f"/repos/{ORG}/{repo}/stats/commit_activity")
        if status == 200 and isinstance(data, list):
            return data
        if status == 204:
            return []
        time.sleep(3)  # 202: GitHub is computing the statistics
    print(f"warning: no stats for {repo}", file=sys.stderr)
    return []


def collect():
    daily, per_repo = {}, {}
    for repo in public_repos():
        total = 0
        for week in commit_activity(repo):
            start = dt.datetime.fromtimestamp(week["week"], dt.timezone.utc).date()
            for i, n in enumerate(week["days"]):
                if n:
                    day = start + dt.timedelta(days=i)
                    daily[day] = daily.get(day, 0) + n
                    total += n
        if total:
            per_repo[repo] = total
    return daily, per_repo


def level(n, thresholds):
    if n == 0:
        return 0
    return 1 + sum(n > t for t in thresholds)


def render(daily, per_repo, today):
    first = today - dt.timedelta(days=today.weekday() + 52 * 7)  # Monday, 53 columns
    days = [first + dt.timedelta(days=i) for i in range((today - first).days + 1)]
    counts = [daily.get(d, 0) for d in days]

    nonzero = sorted(c for c in counts if c)
    if nonzero:
        thresholds = [nonzero[int(len(nonzero) * q)] for q in (0.25, 0.5, 0.75)]
    else:
        thresholds = [0, 0, 0]

    total = sum(counts)
    active = sum(1 for c in counts if c)
    streak = best = 0
    for c in counts:
        streak = streak + 1 if c else 0
        best = max(best, streak)

    x0, y0, step, cell = 92, 118, 16, 12
    out = []
    for i, (d, c) in enumerate(zip(days, counts)):
        col, row = divmod(i, 7)
        x, y = x0 + col * step, y0 + row * step
        tip = f"{d.strftime('%d.%m.%Y')}: {c}"
        out.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="3" fill="{LEVELS[level(c, thresholds)]}"><title>{tip}</title></rect>')

    labels, last_month = [], None
    for col in range(len(days) // 7 + 1):
        d = first + dt.timedelta(days=col * 7)
        nxt = first + dt.timedelta(days=(col + 3) * 7)
        if d.month != last_month and col < 51 and not (col == 0 and nxt.month != d.month):
            labels.append(f'<text x="{x0 + col * step}" y="{y0 - 12}">{MONTHS[d.month - 1]}</text>')
        last_month = d.month
    for row, name in ((0, "пн"), (2, "ср"), (4, "пт")):
        labels.append(f'<text x="{x0 - 12}" y="{y0 + row * step + 10}" text-anchor="end">{name}</text>')

    legend_x = x0 + 48
    legend = [f'<text x="{x0}" y="{y0 + 7 * step + 25}">меньше</text>']
    legend += [f'<rect x="{legend_x + i * step}" y="{y0 + 7 * step + 15}" width="{cell}" height="{cell}" rx="3" fill="{c}"/>' for i, c in enumerate(LEVELS)]
    legend.append(f'<text x="{legend_x + 5 * step + 6}" y="{y0 + 7 * step + 25}">больше</text>')

    top = sorted(per_repo.items(), key=lambda kv: -kv[1])[:4]
    peak = top[0][1] if top else 1
    bars = []
    for i, (name, n) in enumerate(top):
        y = 186 + i * 26
        w = max(4, round(150 * n / peak))
        bars.append(
            f'<text x="990" y="{y}" fill="#c9d8da">{escape(name if len(name) <= 26 else name[:25] + '…')}</text>'
            f'<text x="1232" y="{y}" text-anchor="end" fill="#8ba6ab">{n}</text>'
            f'<rect x="990" y="{y + 6}" width="242" height="3" rx="1.5" fill="#1b2a30"/>'
            f'<rect x="990" y="{y + 6}" width="{round(242 * w / 150)}" height="3" rx="1.5" fill="#2aa29f"/>'
        )

    stats = [(f"{total:,}".replace(",", " "), "коммитов"), (str(active), "активных дней"), (str(best), "дней подряд")]
    stat_svg = "".join(
        f'<text x="{990 + (0, 90, 172)[i]}" y="118" font-size="24" font-weight="700" fill="#f3f7f6">{v}</text>'
        f'<text x="{990 + (0, 90, 172)[i]}" y="138" font-size="11" fill="#8ba6ab">{l}</text>'
        for i, (v, l) in enumerate(stats)
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="300" viewBox="0 0 1280 300" role="img" aria-labelledby="t d">
<title id="t">Активность Manacost Labs</title>
<desc id="d">Коммиты во всех открытых репозиториях за 12 месяцев: {total}, активных дней: {active}.</desc>
<defs><linearGradient id="bg" x2="1" y2=".6"><stop stop-color="#101719"/><stop offset="1" stop-color="#070b0e"/></linearGradient></defs>
<rect width="1280" height="300" rx="22" fill="url(#bg)"/>
<rect x=".5" y=".5" width="1279" height="299" rx="21.5" fill="none" stroke="#91d8ce" stroke-opacity=".18"/>
<g font-family="'Segoe UI', Inter, 'Helvetica Neue', Arial, sans-serif">
<path d="M54 47H102" stroke="#65d9cb" stroke-width="3"/>
<text x="116" y="53" font-size="14" letter-spacing="3" fill="#90b4b5" font-weight="600">АКТИВНОСТЬ КОМАНДЫ ЗА ГОД</text>
<text x="1232" y="53" font-size="12" fill="#5f7a7e" text-anchor="end">коммиты в открытых репозиториях · обновлено {today.strftime('%d.%m.%Y')}</text>
<g font-size="11" fill="#6f8a8e">{''.join(labels)}{''.join(legend)}</g>
{''.join(out)}
<line x1="964" y1="96" x2="964" y2="262" stroke="#91d8ce" stroke-opacity=".12"/>
{stat_svg}
<text x="990" y="166" font-size="11" letter-spacing="2" fill="#90b4b5" font-weight="600">ТОП РЕПОЗИТОРИЕВ</text>
<g font-size="13">{''.join(bars)}</g>
</g>
</svg>
"""


def main():
    daily, per_repo = collect()
    today = dt.datetime.now(dt.timezone.utc).date()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(daily, per_repo, today), encoding="utf-8", newline="\n")
    print(f"{OUT}: {sum(daily.values())} commits, {len(per_repo)} repos")


if __name__ == "__main__":
    main()
