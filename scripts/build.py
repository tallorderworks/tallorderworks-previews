#!/usr/bin/env python3
"""Build Tall Order Works prospect previews.

For every prospects/<slug>/ folder (folders starting with "_" are skipped):
  1. Download the images listed in prospect.json into prospects/<slug>/img/
  2. Render screenshots into prospects/<slug>/out/
       mockup: current-desktop.jpg, desktop.jpg, phone.jpg, email-compare.jpg
       audit:  current-phone.jpg
  3. Write prospects/<slug>/out/build.json with checks for the outreach task
  4. Assemble site/ (published mockups only) for GitHub Pages

A prospect is rebuilt only when its files changed since its last build
(or when FORCE_ALL=1). The site is always assembled from every published prospect.
"""
import datetime as dt
import html
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PROSPECTS = ROOT / "prospects"
SITE = ROOT / "site"
TEMPLATE = ROOT / "templates" / "preview.html"
# Intro paragraph on every preview page. A prospect can pin its own with "intro" in prospect.json.
DEFAULT_INTRO = ("Most customers check a business's website on their phone before they call. Tall Order Works "
                 "is a Houston studio that builds websites designed to turn those visits into calls and quote "
                 "requests, then keeps everything running so you never have to think about your website again. "
                 "We put this homepage concept together for {{BUSINESS}} using details and photos from your "
                 "current site. Scroll to see the full page.")
PREVIEW_BASE = "https://preview.tallorderworks.com"
CALENDLY = "https://calendly.com/tallorderworks/mockup-walkthrough?a1="
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
DESKTOP = {"width": 1440, "height": 900}
PHONE = {"width": 390, "height": 844}
DASHES = re.compile(r"[‒–—―]")
# a hyphen between letters, or a spaced hyphen used as a dash
HYPHEN_WORD = re.compile(r"[A-Za-z]-[A-Za-z]")
SPACED_HYPHEN = re.compile(r"\s-\s")


def now_iso():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def git(*args):
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return ""


def needs_build(folder: Path) -> bool:
    if os.environ.get("FORCE_ALL") == "1":
        return True
    build = folder / "out" / "build.json"
    if not build.exists():
        return True
    try:
        last = json.loads(build.read_text()).get("source_commit", "")
    except Exception:
        return True
    rel = folder.relative_to(ROOT).as_posix()
    latest = git("log", "-1", "--format=%H", "--", f"{rel}/prospect.json", f"{rel}/mockup.html")
    return latest != "" and latest != last


def download_images(folder: Path, images: dict) -> list:
    errors = []
    img_dir = folder / "img"
    img_dir.mkdir(exist_ok=True)
    for name, url in (images or {}).items():
        if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
            errors.append({"name": name, "error": "file name may only use letters, digits, dot, dash, underscore"})
            continue
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
            ctype = r.headers.get("content-type", "")
            if r.status_code != 200:
                errors.append({"name": name, "url": url, "error": f"HTTP {r.status_code}"})
                continue
            if not ctype.startswith("image/"):
                errors.append({"name": name, "url": url, "error": f"not an image ({ctype})"})
                continue
            (img_dir / name).write_bytes(r.content)
        except Exception as e:  # network errors, timeouts
            errors.append({"name": name, "url": url, "error": str(e)[:200]})
    return errors


def visible_text(page) -> str:
    return page.evaluate("() => document.body ? document.body.innerText : ''")


def copy_warnings(text: str) -> list:
    warnings = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        # phone numbers like 713-555-0100 are allowed
        cleaned = re.sub(r"\(?\d{3}\)?[\s.-]?\d{3}-\d{4}", "", s)
        cleaned = re.sub(r"\S+@\S+|https?://\S+|www\.\S+", "", cleaned)
        if DASHES.search(cleaned) or HYPHEN_WORD.search(cleaned) or SPACED_HYPHEN.search(cleaned):
            warnings.append(s[:160])
    return warnings[:30]


def shot(page, path: Path, full_page: bool):
    page.screenshot(path=str(path), full_page=full_page, type="jpeg", quality=82)


def open_page(browser, viewport, url, mobile=False):
    ctx = browser.new_context(viewport=viewport, user_agent=UA if not mobile else None,
                              is_mobile=mobile, has_touch=mobile,
                              device_scale_factor=2 if mobile else 1, ignore_https_errors=True)
    page = ctx.new_page()
    page.goto(url, wait_until="load", timeout=60000)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    page.wait_for_timeout(800)
    return ctx, page


def label_font(size):
    for f in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]:
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def make_compare(current: Path, concept: Path, out: Path):
    """Side by side: current site (left) and concept (right), top of page, 1200px wide."""
    w_each, gap, pad, label_h = 580, 16, 12, 44
    imgs = []
    for p in (current, concept):
        im = Image.open(p).convert("RGB")
        im = im.crop((0, 0, im.width, min(im.height, int(im.width * 0.625))))  # 16:10 hero area
        im = im.resize((w_each, int(im.height * w_each / im.width)))
        imgs.append(im)
    h = max(i.height for i in imgs)
    canvas = Image.new("RGB", (pad * 2 + w_each * 2 + gap, pad + label_h + h + pad), (244, 239, 230))
    d = ImageDraw.Draw(canvas)
    font = label_font(20)
    for idx, (im, label) in enumerate(zip(imgs, ("Your current homepage", "Our concept"))):
        x = pad + idx * (w_each + gap)
        d.text((x, pad + 8), label, fill=(27, 26, 23) if idx == 0 else (191, 69, 26), font=font)
        canvas.paste(im, (x, pad + label_h))
        d.rectangle([x - 1, pad + label_h - 1, x + im.width, pad + label_h + im.height], outline=(200, 192, 180))
    canvas.save(out, "JPEG", quality=85)


def build_prospect(browser, folder: Path) -> dict:
    p = json.loads((folder / "prospect.json").read_text())
    out = folder / "out"
    out.mkdir(exist_ok=True)
    slug = folder.name
    result = {"slug": slug, "type": p.get("type", "mockup"), "rendered_at": None,
              "source_commit": git("log", "-1", "--format=%H", "--",
                                   f"prospects/{slug}/prospect.json", f"prospects/{slug}/mockup.html"),
              "image_errors": [], "broken_images_in_mockup": [], "phone_horizontal_scroll": False,
              "copy_warnings": [], "errors": []}

    site_url = p.get("site_url", "")
    if result["type"] == "audit":
        try:
            ctx, page = open_page(browser, PHONE, site_url, mobile=True)
            shot(page, out / "current-phone.jpg", full_page=False)
            ctx.close()
        except Exception as e:
            result["errors"].append(f"current site phone screenshot failed: {str(e)[:200]}")
        result["rendered_at"] = now_iso()
        return result

    result["image_errors"] = download_images(folder, p.get("images", {}))
    mockup = folder / "mockup.html"
    if not mockup.exists():
        result["errors"].append("mockup.html is missing")
        result["rendered_at"] = now_iso()
        return result
    murl = mockup.resolve().as_uri()

    try:
        ctx, page = open_page(browser, DESKTOP, site_url)
        shot(page, out / "current-desktop.jpg", full_page=False)
        ctx.close()
    except Exception as e:
        result["errors"].append(f"current site screenshot failed: {str(e)[:200]}")

    ctx, page = open_page(browser, DESKTOP, murl)
    page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(500)
    page.evaluate("() => window.scrollTo(0, 0)")
    result["broken_images_in_mockup"] = page.evaluate(
        "() => [...document.images].filter(i => !i.complete || i.naturalWidth === 0).map(i => i.getAttribute('src'))")
    result["copy_warnings"] = copy_warnings(visible_text(page))
    shot(page, out / "desktop.jpg", full_page=True)
    shot(page, out / "desktop-top.jpg", full_page=False)
    ctx.close()

    ctx, page = open_page(browser, PHONE, murl, mobile=True)
    result["phone_horizontal_scroll"] = page.evaluate(
        "() => document.documentElement.scrollWidth > window.innerWidth + 1")
    shot(page, out / "phone.jpg", full_page=True)
    ctx.close()

    if (out / "current-desktop.jpg").exists():
        make_compare(out / "current-desktop.jpg", out / "desktop-top.jpg", out / "email-compare.jpg")
    else:
        result["errors"].append("email-compare.jpg not made: no screenshot of the current site")
    result["rendered_at"] = now_iso()
    return result


def render_preview_page(p: dict, slug: str) -> str:
    tpl = TEMPLATE.read_text()
    biz = p["business"]
    changes = "".join(
        f'<li><strong>{html.escape(c.get("title", ""))}</strong> {html.escape(c.get("text", ""))}</li>'
        for c in p.get("changes", []))
    values = {
        "BUSINESS": html.escape(biz),
        "SOURCES_PHRASE": html.escape(p.get("sources_phrase") or p.get("domain") or "your current site"),
        "CHANGES": changes,
        "CALENDLY": html.escape(CALENDLY + urllib.parse.quote(biz)),
        "SLUG": slug,
        "BUSINESS_Q": urllib.parse.quote(biz),
    }
    intro = p.get("intro") or DEFAULT_INTRO
    values["INTRO"] = html.escape(intro.replace("{{BUSINESS}}", biz))
    for k, v in values.items():
        tpl = tpl.replace("{{" + k + "}}", v)
    return tpl


def assemble_site():
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir()
    (SITE / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
    (SITE / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><meta name="robots" content="noindex">'
        '<meta http-equiv="refresh" content="0; url=https://tallorderworks.com">'
        '<title>Tall Order Works</title><a href="https://tallorderworks.com">tallorderworks.com</a>')
    (SITE / "CNAME").write_text("preview.tallorderworks.com\n")
    published = []
    for folder in sorted(PROSPECTS.iterdir()):
        if not folder.is_dir() or folder.name.startswith("_"):
            continue
        try:
            p = json.loads((folder / "prospect.json").read_text())
        except Exception:
            continue
        if p.get("type", "mockup") != "mockup" or not p.get("published", False):
            continue
        out = folder / "out"
        if not (out / "desktop.jpg").exists():
            continue
        dest = SITE / folder.name
        (dest / "concept").mkdir(parents=True)
        (dest / "index.html").write_text(render_preview_page(p, folder.name))
        for f in ("desktop.jpg", "phone.jpg"):
            if (out / f).exists():
                shutil.copy(out / f, dest / f)
        shutil.copy(folder / "mockup.html", dest / "concept" / "index.html")
        if (folder / "img").exists():
            shutil.copytree(folder / "img", dest / "concept" / "img")
        published.append(folder.name)
    print("Published:", ", ".join(published) or "none")


def main():
    folders = [f for f in sorted(PROSPECTS.iterdir())
               if f.is_dir() and not f.name.startswith("_") and (f / "prospect.json").exists()]
    todo = [f for f in folders if needs_build(f)]
    print("To build:", ", ".join(f.name for f in todo) or "none")
    if todo:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for folder in todo:
                try:
                    res = build_prospect(browser, folder)
                except Exception as e:
                    res = {"slug": folder.name, "rendered_at": now_iso(), "errors": [f"build failed: {str(e)[:300]}"]}
                if res.get("type") == "mockup":
                    res["preview_url"] = f"{PREVIEW_BASE}/{folder.name}/"
                (folder / "out").mkdir(exist_ok=True)
                (folder / "out" / "build.json").write_text(json.dumps(res, indent=2))
                print(json.dumps(res, indent=2))
            browser.close()
    assemble_site()


if __name__ == "__main__":
    sys.exit(main())
