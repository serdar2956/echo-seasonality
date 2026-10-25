"""Build the static page: index.html loads data/*.json at runtime, so the daily bot never has to rebuild it.
Usage: python scripts/build_site.py OUT_DIR"""
import shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT, OUT = HERE.parent, Path(sys.argv[1]).resolve()
SITE_URL = "https://example.com/"   # set to your domain before launch

HEAD = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Seasonality for 66 markets, every pattern tested for statistical significance. Seasonal charts, screener, event impact, COT positioning, interest rates, inflation and market hours.">
<meta name="theme-color" content="#0B5FA5">
<link rel="icon" href="assets/favicon.svg" type="image/svg+xml">
<link rel="icon" href="assets/favicon-32.png" sizes="32x32">
<link rel="apple-touch-icon" href="assets/apple-touch-icon.png">
<meta property="og:title" content="ECHO · Seasonality, tested">
<meta property="og:description" content="Seasonal patterns for 66 markets, checked for statistical significance.">
<meta property="og:type" content="website">
<meta property="og:url" content="{SITE_URL}">
<meta property="og:image" content="{SITE_URL}assets/og-image.png">
<meta name="twitter:card" content="summary_large_image">
"""

LOADER_OLD = """<script type="application/json" id="data">__DATA__</script>
<script type="application/json" id="tools">__TOOLS__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const T = JSON.parse(document.getElementById('tools').textContent);"""
LOADER_NEW = """<script>
(async () => {
let D, T;
try {
  [D, T] = await Promise.all(['data/site.json', 'data/tools.json'].map(u => fetch(u, {cache: 'no-cache'}).then(r => { if (!r.ok) throw new Error(u); return r.json(); })));
} catch (e) {
  document.querySelector('.intro h1').textContent = 'Data is updating. Please refresh in a minute.';
  return;
}"""


def main():
    t = (HERE / "template.html").read_text(encoding="utf-8")
    t = t.replace('<meta name="claude:viewport-fit-sides" content="cover">\n', "")
    assert LOADER_OLD in t
    t = t.replace(LOADER_OLD, LOADER_NEW)
    i = t.rindex("</script>")
    t = t[:i] + "})();\n" + t[i:]
    head_end = t.index("</style>") + len("</style>")
    page = HEAD + t[:head_end] + "\n</head>\n<body>\n" + t[head_end:] + "\n</body>\n</html>\n"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "index.html").write_text(page, encoding="utf-8")
    for f in ("404.html", "robots.txt", ".nojekyll"):
        if (ROOT / f).exists():
            shutil.copy(ROOT / f, OUT / f)
    if OUT != ROOT:
        shutil.copytree(ROOT / "assets", OUT / "assets", dirs_exist_ok=True)
    print("built", OUT / "index.html")


if __name__ == "__main__":
    main()
