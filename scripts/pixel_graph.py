#!/usr/bin/env python3
"""
Pixel-art GitHub contribution dashboard generator.

Builds ONE self-contained SVG (animated snake, live stats, pixel scene) from your
real contribution data and writes it to dist/pixel-graph.svg.

Usage (in GitHub Actions):  GH_TOKEN=... GH_USER=mobin-119 python scripts/pixel_graph.py
Local preview with fake data:  python pixel_graph.py --demo
"""
import argparse, base64, datetime as dt, json, math, os, random, sys, urllib.request

W, SCENE_H = 1536, 384
SCENE_Y = 588
H = SCENE_Y + SCENE_H

# ---- palette (teal theme) --------------------------------------------------
LEVELS = ["#0c1f33", "#00574D", "#009B77", "#1EBDA4", "#8BE5D2"]
LEVEL_NAMES = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2,
               "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}
FONT = "'JetBrains Mono','Fira Code','DejaVu Sans Mono',Consolas,Menlo,monospace"

# ---- grid geometry -----------------------------------------------------------
GX0, GY0 = 148, 312          # top-left of first cell
PX, PY = 25.0, 32.0          # pitch
CW, CH = 20, 22              # cell size
FRAME = (40, 235, 1456, 315)  # x, y, w, h


def cx(c): return GX0 + c * PX + CW / 2
def cy(r): return GY0 + r * PY + CH / 2


# ---- data --------------------------------------------------------------------
QUERY = """
query($login:String!){
  user(login:$login){
    contributionsCollection{
      totalCommitContributions
      restrictedContributionsCount
      contributionCalendar{
        totalContributions
        weeks{ firstDay contributionDays{ date contributionCount contributionLevel weekday } }
      }
    }
    repositories(first:100, ownerAffiliations:OWNER, isFork:false){
      nodes{ stargazerCount forkCount }
    }
  }
}"""


def fetch(user, token):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": user}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json",
                 "User-Agent": "pixel-graph"})
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    if "errors" in payload or not payload.get("data", {}).get("user"):
        raise SystemExit("GitHub API error: " + json.dumps(payload)[:500])
    u = payload["data"]["user"]
    cc = u["contributionsCollection"]
    cal = cc["contributionCalendar"]
    weeks = []
    for w in cal["weeks"]:
        days = {d["weekday"]: (LEVEL_NAMES.get(d["contributionLevel"], 0),
                               d["contributionCount"], d["date"]) for d in w["contributionDays"]}
        weeks.append((w["firstDay"], days))
    repos = u["repositories"]["nodes"]
    return dict(weeks=weeks, total=cal["totalContributions"],
                commits=cc["totalCommitContributions"] + cc.get("restrictedContributionsCount", 0),  # public + private
                stars=sum(n["stargazerCount"] for n in repos),
                forks=sum(n["forkCount"] for n in repos))


def demo_data():
    rnd = random.Random(7)
    today = dt.date.today()
    start = today - dt.timedelta(days=today.weekday() + 1 + 52 * 7)  # a Sunday
    weeks, total = [], 0
    for w in range(53):
        first = start + dt.timedelta(days=7 * w)
        days = {}
        for d in range(7):
            date = first + dt.timedelta(days=d)
            if date > today:
                continue
            n = 0 if rnd.random() < 0.38 else int(rnd.random() ** 2 * 14)
            lvl = 0 if n == 0 else 1 if n < 3 else 2 if n < 6 else 3 if n < 10 else 4
            days[d] = (lvl, n, date.isoformat())
            total += n
        weeks.append((first.isoformat(), days))
    return dict(weeks=weeks, total=total, commits=int(total * 0.82), stars=12, forks=3)


def current_streak(weeks):
    flat = sorted((d[2], d[1]) for _, days in weeks for d in days.values())
    i = len(flat) - 1
    if i >= 0 and flat[i][1] == 0:
        i -= 1                      # today may not have contributions yet
    s = 0
    while i >= 0 and flat[i][1] > 0:
        s += 1
        i -= 1
    return s


# ---- svg pieces ----------------------------------------------------------------
def fmt(n): return f"{int(n):,}"


def sprite_python(x, y):
    return (f'<g transform="translate({x:.1f},{y:.1f})"><rect x="-16" y="-16" width="20" height="20" rx="4" fill="#3776ab"/>'
            f'<rect x="-4" y="-4" width="20" height="20" rx="4" fill="#ffd43b"/>'
            f'<rect x="-11" y="-11" width="4" height="4" fill="#fff"/><rect x="7" y="7" width="4" height="4" fill="#0b2a4a"/></g>')


def sprite_git(x, y):
    return (f'<g transform="translate({x:.1f},{y:.1f})"><rect x="-12" y="-12" width="24" height="24" rx="3" fill="#f05033" transform="rotate(45)"/>'
            '<path d="M-4 6 L0 -6 L5 3" stroke="#fff" stroke-width="2.4" fill="none"/>'
            '<circle cx="0" cy="-6" r="2.6" fill="#fff"/><circle cx="-4" cy="6" r="2.6" fill="#fff"/><circle cx="5" cy="3" r="2.6" fill="#fff"/></g>')


def sprite_terminal(x, y):
    return (f'<g transform="translate({x:.1f},{y:.1f})"><rect x="-18" y="-14" width="36" height="28" rx="3" fill="#161659" stroke="#6d6dff" stroke-width="2.5"/>'
            f'<text x="0" y="5" text-anchor="middle" font-family="{FONT}" font-size="15" font-weight="700" fill="#cfd8ff">&gt;_</text></g>')


def sprite_dj(x, y):
    return (f'<g transform="translate({x:.1f},{y:.1f})"><rect x="-14" y="-14" width="28" height="28" rx="5" fill="#0c4b33" stroke="#1EBDA4" stroke-width="2"/>'
            f'<text x="0" y="5" text-anchor="middle" font-family="{FONT}" font-size="15" font-weight="700" fill="#4ED3C3">dj</text></g>')


def sprite_code(x, y):
    return (f'<text x="{x:.1f}" y="{y + 7:.1f}" text-anchor="middle" font-family="{FONT}" font-size="22" font-weight="700" '
            f'fill="#b44cff" filter="url(#glow)">&lt;/&gt;</text>')


def sprite_github(x, y):
    return (f'<g transform="translate({x:.1f},{y:.1f})"><circle r="15" fill="#2b2f6b" stroke="#8a8fff" stroke-width="2.5"/>'
            '<path d="M-7 -3 L-7 -10 L-3 -6 L3 -6 L7 -10 L7 -3 Q7 8 0 8 Q-7 8 -7 -3Z" fill="#fff"/></g>')


def sprite_coin(x, y):
    return (f'<g transform="translate({x:.1f},{y:.1f})"><circle r="11" fill="#ffc107" stroke="#ff9800" stroke-width="3"/>'
            '<rect x="-3" y="-6" width="6" height="12" fill="#ffe082"/></g>')


def sprite_flag(x, y):
    sq = "".join(f'<rect x="{2 + i * 6}" y="{-14 + j * 6}" width="6" height="6" fill="{"#fff" if (i + j) % 2 == 0 else "#10243a"}"/>'
                 for i in range(3) for j in range(2))
    return f'<g transform="translate({x:.1f},{y:.1f})"><rect x="-1.5" y="-14" width="3" height="30" fill="#cfd8dc"/>{sq}</g>'


def snake_path():
    pts, prev_r = [], None
    for c in range(-3, 57):
        r = int(round(3 + 2.3 * math.sin(c / 5.2) + 0.9 * math.sin(c / 2.1)))
        r = max(0, min(6, r))
        if prev_r is None:
            pts.append((cx(c), cy(r)))
        else:
            pts.append((cx(c), cy(prev_r)))
            if r != prev_r:
                pts.append((cx(c), cy(r)))
        prev_r = r
    length = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    return d, length


def snake_svg():
    d, length = snake_path()
    speed = 150.0                          # px / second
    dur = length / speed
    n, spacing = 20, 15.0
    delay = spacing / speed
    k = n * delay + 1
    out = []
    for i in range(n - 1, -1, -1):
        begin = -(k) + i * delay
        if i == 0:
            body = ('<rect x="-14" y="-14" width="28" height="28" rx="5" fill="#00f0ff" filter="url(#glow)"/>'
                    '<rect x="2" y="-9" width="7" height="7" fill="#fff"/><rect x="2" y="3" width="7" height="7" fill="#fff"/>'
                    '<rect x="6" y="-7" width="3" height="3" fill="#06223a"/><rect x="6" y="5" width="3" height="3" fill="#06223a"/>')
        else:
            t = i / n
            size = 22 - 8 * t
            r, g, b = int(0 + 0 * t), int(229 - 74 * t), int(255 - 136 * t)   # cyan -> teal
            op = 1 - 0.45 * t
            body = (f'<rect x="{-size / 2:.1f}" y="{-size / 2:.1f}" width="{size:.1f}" height="{size:.1f}" rx="3" '
                    f'fill="rgb({r},{g},{b})" opacity="{op:.2f}"/>')
        out.append(f'<g>{body}<animateMotion dur="{dur:.2f}s" begin="{begin:.3f}s" repeatCount="indefinite" path="{d}"/></g>')
    return '<g clip-path="url(#gridClip)" filter="url(#glowSoft)">' + "".join(out) + "</g>"


def build_svg(data, scene_b64, user):
    streak = current_streak(data["weeks"])
    fx, fy, fw, fh = FRAME
    o = []
    a = o.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{W}" height="{H}" '
      f'viewBox="0 0 {W} {H}" role="img" aria-label="GitHub contribution dashboard for {user}">')
    a(f'<title>GitHub contributions of {user}</title>')
    a('<defs>'
      '<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#010412"/><stop offset="1" stop-color="#00081c"/></linearGradient>'
      f'<linearGradient id="fadeG" gradientUnits="userSpaceOnUse" x1="0" y1="{SCENE_Y}" x2="0" y2="{SCENE_Y + 46}"><stop offset="0" stop-color="#000"/><stop offset="1" stop-color="#fff"/></linearGradient>'
      f'<mask id="fade"><rect x="0" y="{SCENE_Y}" width="{W}" height="{SCENE_H}" fill="url(#fadeG)"/></mask>'
      '<filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
      '<filter id="glowSoft" x="-5%" y="-20%" width="110%" height="140%"><feGaussianBlur stdDeviation="2.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
      f'<clipPath id="gridClip"><rect x="{fx + 6}" y="{fy + 6}" width="{fw - 12}" height="{fh - 12}"/></clipPath>'
      '</defs>')
    a('<style>' + "".join(f'.l{i}{{fill:{c}}}' for i, c in enumerate(LEVELS)) +
      f'.t{{font-family:{FONT}}}</style>')
    a(f'<rect width="{W}" height="{H}" fill="url(#bg)"/>')
    # a few static stars
    rnd = random.Random(3)
    for _ in range(40):
        a(f'<rect x="{rnd.randint(10, W - 10)}" y="{rnd.randint(8, 205)}" width="2" height="2" fill="#4ED3C3" opacity="{rnd.choice([.25, .4, .6])}"/>')
    a(f'<image xlink:href="data:image/png;base64,{scene_b64}" x="0" y="{SCENE_Y}" width="{W}" height="{SCENE_H}" '
      f'mask="url(#fade)" style="image-rendering:pixelated"/>')

    # header
    a('<g transform="translate(78,150)"><circle r="17" fill="none" stroke="#1EBDA4" stroke-width="3.5"/>'
      '<rect x="-3" y="-9" width="6" height="18" fill="#1EBDA4"/><rect x="-9" y="-3" width="18" height="6" fill="#1EBDA4"/></g>')
    a(f'<text class="t" x="116" y="160" font-size="31" letter-spacing="3" fill="#d7f3ee">GitHub Contribution Graph</text>')
    a(f'<text class="t" x="116" y="194" font-size="21" fill="#1EBDA4">&gt; Keep coding ...</text>')
    a('<rect x="336" y="178" width="12" height="20" fill="#1EBDA4"><animate attributeName="opacity" values="1;1;0;0" dur="1s" repeatCount="indefinite"/></rect>')
    a(f'<text class="t" x="{fx + fw}" y="160" text-anchor="end" font-size="17" fill="#8BE5D2" opacity=".8">{fmt(data["total"])} contributions in the last year</text>')

    # frame
    a(f'<rect x="{fx}" y="{fy}" width="{fw}" height="{fh}" rx="8" fill="#02112b" fill-opacity=".55" stroke="#1d5fa8" stroke-width="3"/>')
    for px_, py_ in ((fx, fy), (fx + fw - 8, fy), (fx, fy + fh - 8), (fx + fw - 8, fy + fh - 8)):
        a(f'<rect x="{px_ - 1}" y="{py_ - 1}" width="10" height="10" fill="#38a0ff"/>')

    # labels
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    last_m, last_w = None, -9
    for w_i, (first, _) in enumerate(data["weeks"]):
        m = int(first[5:7]) - 1
        if m != last_m and w_i - last_w >= 3:
            a(f'<text class="t" x="{GX0 + w_i * PX:.1f}" y="{fy + 40}" font-size="15" fill="#6fa8c9">{months[m]}</text>')
            last_w = w_i
        last_m = m
    for r, name in enumerate(["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]):
        a(f'<text class="t" x="{fx + 20}" y="{GY0 + r * PY + 16}" font-size="14" fill="#6fa8c9">{name}</text>')

    # cells
    for w_i, (_, days) in enumerate(data["weeks"]):
        for r, (lvl, n, date) in days.items():
            a(f'<rect class="l{lvl}" x="{GX0 + w_i * PX:.1f}" y="{GY0 + r * PY:.1f}" width="{CW}" height="{CH}" rx="3"><title>{n} contributions on {date}</title></rect>')

    # sprites (decor)
    a(sprite_python(cx(3.2), cy(0.9)) + sprite_git(cx(14), cy(0.8)) + sprite_terminal(cx(23), cy(0.9)) +
      sprite_dj(cx(16.5), cy(5.9)) + sprite_code(cx(35), cy(6)) + sprite_coin(cx(37.3), cy(1.2)) +
      sprite_github(cx(46), cy(2.2)) + sprite_flag(cx(52.3), cy(5.6)))
    a(snake_svg())
    a(f'<text class="t" x="{fx + fw - 22}" y="{fy + fh - 10}" text-anchor="end" font-size="14" fill="#2e6f93">Keep going...</text>')

    # stats row (over the inpainted part of the scene)
    sy = SCENE_Y
    stats = [
        (64, 118, "Streak", f'{streak}d',
         '<path d="M0 -17 C8 -8 12 -2 8 8 C6 14 -6 14 -8 8 C-12 -2 -4 -6 0 -17Z" fill="#ff9f1c"/><path d="M0 -4 C4 1 5 5 2 9 C-2 9 -4 5 0 -4Z" fill="#ffe082"/>'),
        (247, 281, "Commits", fmt(data["commits"]),
         '<circle r="14" fill="#ffc107" stroke="#ff9800" stroke-width="3.5"/><rect x="-3" y="-8" width="6" height="16" fill="#ffe082"/>'),
        (411, 447, "Stars", fmt(data["stars"]),
         '<path d="M0 -17 L5 -6 L17 -5 L8 3 L11 15 L0 9 L-11 15 L-8 3 L-17 -5 L-5 -6Z" fill="#38bdf8"/>'),
        (570, 604, "Forks", fmt(data["forks"]),
         '<g stroke="#38bdf8" stroke-width="3" fill="none"><path d="M-8 -12 L-8 -4 Q-8 2 0 2 Q8 2 8 -4 L8 -12 M0 2 L0 14"/></g>'
         '<g fill="#02112b" stroke="#38bdf8" stroke-width="3"><circle cx="-8" cy="-13" r="4"/><circle cx="8" cy="-13" r="4"/><circle cx="0" cy="15" r="4"/></g>'),
    ]
    for icx, tx, label, val, icon in stats:
        a(f'<g transform="translate({icx},{sy + 54})">{icon}</g>')
        a(f'<text class="t" x="{tx}" y="{sy + 46}" font-size="16" fill="#8BE5D2" opacity=".8">{label}</text>')
        a(f'<text class="t" x="{tx}" y="{sy + 76}" font-size="22" font-weight="700" fill="#4ED3C3">{val}</text>')
    for sx in (207, 370, 533, 735):
        a(f'<rect x="{sx}" y="{sy + 30}" width="2" height="50" fill="#123a66"/>')
    a(f'<text class="t" x="765" y="{sy + 52}" font-size="17" fill="#1EBDA4">Small steps...</text>')
    a(f'<text class="t" x="765" y="{sy + 78}" font-size="17" fill="#1EBDA4">Big projects!</text>')
    a(f'<text class="t" x="765" y="{sy + 118}" font-size="17" fill="#1EBDA4">&gt;_<animate attributeName="opacity" values="1;1;0;0" dur="1s" repeatCount="indefinite"/></text>')
    a('</svg>')
    return "\n".join(o)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--user", default=os.environ.get("GH_USER", "mobin-119"))
    ap.add_argument("--scene", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "scene.png"))
    ap.add_argument("--out", default="dist/pixel-graph.svg")
    args = ap.parse_args()

    if args.demo:
        data = demo_data()
    else:
        token = os.environ.get("GH_TOKEN")
        if not token:
            sys.exit("GH_TOKEN is not set")
        data = fetch(args.user, token)

    scene = args.scene if os.path.exists(args.scene) else "assets/scene.png"
    with open(scene, "rb") as f:
        scene_b64 = base64.b64encode(f.read()).decode()

    svg = build_svg(data, scene_b64, args.user)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"wrote {args.out} ({len(svg) / 1024:.0f} KB), total={data['total']}")


if __name__ == "__main__":
    main()
