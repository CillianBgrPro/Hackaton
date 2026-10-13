"""Assemble une page autonome à partir d'un dossier web (index.html, styles.css, app.js).

Intègre les feuilles de style Leaflet (cache/), styles.css, app.js, les données et le fond de carte
(build/basemap.json). Seuls Leaflet et les polices restent chargés depuis un CDN.

  python src/assemble.py                     # carte des signalements → dist/carte-signalements-tao.html
  python src/assemble.py --web src/safe_places/web --data build/safe_places.json \\
                         --out dist/safe-places/carte-safe-places-tao.html
  --fragment [chemin]                        # produit aussi la page sans <html>/<head>/<body>,
                                             # au format attendu pour une publication en Artifact claude.ai
"""
import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE, BUILD = ROOT / "cache", ROOT / "build"


def read(p):
    return Path(p).read_text(encoding="utf-8")


def json_for_script(text):
    # Empêche une séquence « </script> » éventuelle dans les données de fermer la balise.
    return text.replace("</", "<\\/")


def replace_once(html, old, new):
    assert html.count(old) == 1, f"Marqueur introuvable ou en double : {old}"
    return html.replace(old, new)


def build(web, data):
    html = read(web / "index.html")
    vendor = read(CACHE / "leaflet.css") + "\n" + read(CACHE / "markercluster.css")
    vendor = vendor.replace("url(images/", "url(data:,")   # icônes Leaflet par défaut, inutilisées
    vendor = re.sub(r"/\*# sourceMappingURL=.*?\*/", "", vendor)
    html = replace_once(html, "<!-- build:vendor-css -->", f"<style>{vendor}</style>")
    html = replace_once(html, '<link rel="stylesheet" href="styles.css">', f"<style>\n{read(web / 'styles.css')}</style>")
    html = replace_once(html, '<script src="app.js"></script>', f"<script>\n{read(web / 'app.js')}</script>")
    html = replace_once(html, "/*__DATA__*/", json_for_script(read(data)))
    html = replace_once(html, "/*__BASEMAP__*/", json_for_script(read(BUILD / "basemap.json")))
    return html


def to_fragment(html):
    head = re.search(r"<head>(.*)</head>", html, re.S).group(1)
    body = re.search(r"<body>(.*)</body>", html, re.S).group(1)
    head = re.sub(r"<meta [^>]*>\n?", "", head)
    return head.strip() + "\n\n" + body.strip() + "\n"


def main():
    ap = argparse.ArgumentParser(description="Assemble une page HTML autonome.")
    ap.add_argument("--web", default=str(ROOT / "src" / "web"), help="dossier contenant index.html, styles.css et app.js")
    ap.add_argument("--data", default=str(BUILD / "data.json"), help="données JSON à intégrer")
    ap.add_argument("--out", default=str(ROOT / "dist" / "carte-signalements-tao.html"), help="page produite")
    ap.add_argument("--fragment", nargs="?", const=str(BUILD / "artifact.html"), help="produire aussi la version Artifact")
    args = ap.parse_args()
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    html = build(Path(args.web), Path(args.data))
    out.write_text(html, encoding="utf-8")
    print(f"Page : {out.relative_to(ROOT)} ({len(html.encode()) / 1024:.0f} Ko)")
    if args.fragment:
        frag = Path(args.fragment).resolve()
        frag.write_text(to_fragment(html), encoding="utf-8")
        print(f"Fragment Artifact : {frag.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
