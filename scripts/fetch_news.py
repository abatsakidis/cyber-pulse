```python
#!/usr/bin/env python3

import json
import re
import hashlib
import html as H

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from xml.etree import ElementTree as ET


R = Path(__file__).resolve().parents[1]
S = R / "data/sources.json"
O = R / "data/news.json"
T = R / "data/status.json"


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

ARTICLE_FETCH_TIMEOUT = 8
MAX_ARTICLE_FETCHES_PER_SOURCE = 40
USER_AGENT = (
    "Mozilla/5.0 (compatible; CyberPulseRSS/2.0; "
    "+https://github.com/abatsakidis/cyber-pulse)"
)


# ---------------------------------------------------------
# Basic helpers
# ---------------------------------------------------------

def clean(x):
    x = re.sub(
        r"<script.*?</script>|<style.*?</style>",
        " ",
        x or "",
        flags=re.I | re.S,
    )
    return re.sub(
        r"\s+",
        " ",
        H.unescape(re.sub(r"<[^>]+>", " ", x)),
    ).strip()


def txt(e, names):
    wanted = {n.lower() for n in names}

    for n in wanted:
        for x in e.iter():
            tag = x.tag.split("}")[-1].lower()

            if tag == n and (x.text or "").strip():
                return x.text.strip()

    return ""


def date(e):
    v = txt(e, ["pubDate", "published", "updated", "date", "dc:date"])

    try:
        return parsedate_to_datetime(v).astimezone(timezone.utc).isoformat()
    except Exception:
        try:
            return datetime.fromisoformat(
                v.replace("Z", "+00:00")
            ).astimezone(timezone.utc).isoformat()
        except Exception:
            return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------
# URL / image helpers
# ---------------------------------------------------------

def absolute_url(url, base_url=""):
    """
    Convert relative image URLs into absolute URLs.
    Also normalize protocol-relative URLs such as //cdn.example.com/x.jpg.
    """
    if not url:
        return ""

    url = H.unescape(url.strip())

    if url.startswith("//"):
        url = "https:" + url

    if base_url:
        url = urljoin(base_url, url)

    if not re.match(r"^https?://", url, re.I):
        return ""

    return url


def valid_image_url(url):
    """
    Basic sanity check.

    We deliberately do NOT require a .jpg/.png extension because many
    publishers use image CDNs where the URL has no obvious extension.
    """
    if not url:
        return False

    url = url.strip()

    if not re.match(r"^https?://", url, re.I):
        return False

    lowered = url.lower()

    # Avoid obvious tracking pixels / tiny placeholders.
    blocked = (
        "pixel.gif",
        "spacer.gif",
        "transparent.gif",
        "1x1.gif",
        "1x1.png",
        "tracking",
        "doubleclick.net",
    )

    if any(x in lowered for x in blocked):
        return False

    return True


def image_from_html(html, base_url=""):
    """
    Try common HTML image metadata used by news websites.

    Priority:
      1. og:image
      2. twitter:image
      3. image_src
      4. first meaningful <img>
    """

    if not html:
        return ""

    # -----------------------------------------------------
    # OpenGraph
    # -----------------------------------------------------

    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',

        r'<meta[^>]+property=["\']og:image:url["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image:url["\']',

        r'<meta[^>]+property=["\']og:image:secure_url["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image:secure_url["\']',
    ]

    for pattern in patterns:
        m = re.search(pattern, html, re.I | re.S)
        if m:
            u = absolute_url(m.group(1), base_url)
            if valid_image_url(u):
                return u

    # -----------------------------------------------------
    # Twitter card
    # -----------------------------------------------------

    patterns = [
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',

        r'<meta[^>]+name=["\']twitter:image:src["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image:src["\']',
    ]

    for pattern in patterns:
        m = re.search(pattern, html, re.I | re.S)
        if m:
            u = absolute_url(m.group(1), base_url)
            if valid_image_url(u):
                return u

    # -----------------------------------------------------
    # image_src
    # -----------------------------------------------------

    patterns = [
        r'<link[^>]+rel=["\']image_src["\'][^>]+href=["\']([^"\']+)["\']',
        r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\']image_src["\']',
    ]

    for pattern in patterns:
        m = re.search(pattern, html, re.I | re.S)
        if m:
            u = absolute_url(m.group(1), base_url)
            if valid_image_url(u):
                return u

    # -----------------------------------------------------
    # First meaningful <img>
    # -----------------------------------------------------

    images = re.findall(
        r"<img\b[^>]+(?:src|data-src|data-lazy-src|data-original)"
        r'\s*=\s*["\']([^"\']+)["\']',
        html,
        re.I | re.S,
    )

    for raw in images:
        u = absolute_url(raw, base_url)

        if valid_image_url(u):
            return u

    return ""


def image_from_article(url):
    """
    Fetch the article page and try to discover its main image.

    This is only called when the RSS item itself did not provide
    an image.
    """

    if not url:
        return ""

    try:
        req = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": (
                    "text/html,application/xhtml+xml,"
                    "application/xml;q=0.9,*/*;q=0.8"
                ),
                "Accept-Language": "en-US,en;q=0.8",
            },
        )

        with urlopen(req, timeout=ARTICLE_FETCH_TIMEOUT) as r:
            raw = r.read(1200000)

        # Most news pages are UTF-8. We still handle common alternatives.
        try:
            html = raw.decode("utf-8", errors="replace")
        except Exception:
            html = raw.decode("latin-1", errors="replace")

        return image_from_html(html, url)

    except Exception:
        return ""


# ---------------------------------------------------------
# RSS image extraction
# ---------------------------------------------------------

def img(e, description="", base_url=""):
    """
    Extract image from RSS/Atom item.

    Supports:
      - media:content
      - media:thumbnail
      - enclosure
      - content / thumbnail with URL attributes
      - <img src="..."> in description/content
    """

    # Prefer explicit media/enclosure elements.
    for x in e.iter():
        tag = x.tag.split("}")[-1].lower()

        u = (
            x.attrib.get("url")
            or x.attrib.get("href")
            or x.attrib.get("src")
            or ""
        )

        if not u:
            continue

        if tag in ("content", "thumbnail", "enclosure"):
            u = absolute_url(u, base_url)

            if valid_image_url(u):
                return u

    # Some feeds put an image URL in a generic attribute.
    for x in e.iter():
        for attr in ("url", "href", "src"):
            u = x.attrib.get(attr)

            if not u:
                continue

            u = absolute_url(u, base_url)

            if not valid_image_url(u):
                continue

            # Only accept URLs that look like actual image resources
            # when they came from a generic element.
            if re.search(
                r"\.(jpg|jpeg|png|gif|webp|avif)(?:\?|$)",
                u,
                re.I,
            ):
                return u

    # Finally inspect HTML contained in RSS description/content.
    m = re.search(
        r'<img[^>]+(?:src|data-src|data-lazy-src|data-original)'
        r'\s*=\s*["\']([^"\']+)',
        description or "",
        re.I | re.S,
    )

    if m:
        u = absolute_url(m.group(1), base_url)

        if valid_image_url(u):
            return u

    return ""


# ---------------------------------------------------------
# Categorization
# ---------------------------------------------------------

def cat(t, d):
    s = (t + " " + d).lower()

    for c, p in [
        (
            "AI Security",
            r"\b(ai|artificial intelligence|llm|agentic|generative ai|chatgpt|copilot)\b"
            r".{0,90}"
            r"\b(secur|hack|attack|cyber|phish|malware|ransom|exploit)",
        ),
        ("Ransomware", r"ransomware|extortion"),
        (
            "Malware",
            r"malware|trojan|botnet|spyware|infostealer|rootkit",
        ),
        (
            "Vulnerability",
            r"zero[- ]day|cve-\d{4}-\d+|vulnerab|exploit|patch|security flaw",
        ),
        (
            "Cyberwarfare",
            r"cyber ?war|state[- ]sponsor|nation[- ]state|apt\d*|espionage|geopolit",
        ),
        (
            "Privacy",
            r"privacy|surveillance|data breach|data leak|personal data",
        ),
        (
            "Hacking",
            r"hack|phish|credential|ddos|intrusion|cyberattack|cyber attack",
        ),
    ]:
        if re.search(p, s, re.I):
            return c

    return "General Security"


# ---------------------------------------------------------
# RSS / Atom parsing
# ---------------------------------------------------------

def parse(raw, source, feed_url=""):
    root = ET.fromstring(raw)
    out = []

    for e in root.iter():
        if e.tag.split("}")[-1].lower() not in ("item", "entry"):
            continue

        t = clean(txt(e, ["title"]))

        l = ""

        for x in e.iter():
            if x.tag.split("}")[-1].lower() == "link":
                l = x.attrib.get("href") or (x.text or "").strip()

                if l:
                    break

        d = clean(
            txt(
                e,
                [
                    "description",
                    "summary",
                    "content",
                    "encoded",
                ],
            )
        )

        if not t or not l:
            continue

        # First attempt: image directly from RSS.
        image = img(e, d, feed_url)

        out.append(
            {
                "id": hashlib.sha1(
                    (l + t).encode()
                ).hexdigest()[:16],
                "source": source,
                "title": t,
                "description": d[:600],
                "link": l,
                "date": date(e),
                "image": image,
                "category": cat(t, d),
                "hot": bool(
                    re.search(
                        r"zero[- ]day|actively exploited|critical|"
                        r"ransomware|emergency|breach|massive attack",
                        t + " " + d,
                        re.I,
                    )
                ),
            }
        )

    return out


# ---------------------------------------------------------
# Main collector
# ---------------------------------------------------------

def main():
    all_articles = []
    status = []

    for s in json.loads(S.read_text()):
        if not s.get("enabled"):
            continue

        row = {
            "name": s["name"],
            "url": s["url"],
            "ok": False,
            "count": 0,
        }

        try:
            req = Request(
                s["url"],
                headers={
                    "User-Agent": "CyberPulseRSS/2.0",
                    "Accept": (
                        "application/rss+xml,"
                        "application/atom+xml,"
                        "application/xml,"
                        "text/xml;q=0.9,*/*;q=0.5"
                    ),
                },
            )

            with urlopen(req, timeout=25) as r:
                raw = r.read(4000000)

            x = parse(
                raw,
                s["name"],
                s["url"],
            )

            all_articles += x

            row.update(
                ok=True,
                count=len(x),
            )

        except Exception as e:
            row["error"] = str(e)[:220]

        status.append(row)

    # -----------------------------------------------------
    # Deduplicate
    # -----------------------------------------------------

    d = {
        x["id"]: x
        for x in all_articles
    }

    items = sorted(
        d.values(),
        key=lambda x: x["date"],
        reverse=True,
    )[:700]

    # -----------------------------------------------------
    # Image fallback
    #
    # Only fetch article pages when the RSS item has no image.
    # Limit the number of page requests per source.
    # -----------------------------------------------------

    fallback_count = 0
    fallback_by_source = {}

    source_fetch_count = {}

    for item in items:
        if item.get("image"):
            continue

        source = item.get("source", "")

        current = source_fetch_count.get(source, 0)

        if current >= MAX_ARTICLE_FETCHES_PER_SOURCE:
            continue

        source_fetch_count[source] = current + 1

        image = image_from_article(
            item.get("link", "")
        )

        if image:
            item["image"] = image
            fallback_count += 1

            fallback_by_source[source] = (
                fallback_by_source.get(source, 0) + 1
            )

    # -----------------------------------------------------
    # Write output
    # -----------------------------------------------------

    O.write_text(
        json.dumps(
            items,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    T.write_text(
        json.dumps(
            {
                "updated": datetime.now(
                    timezone.utc
                ).isoformat(),
                "sources": status,
                "image_fallback": {
                    "enabled": True,
                    "articles_checked": sum(
                        source_fetch_count.values()
                    ),
                    "images_found": fallback_count,
                    "by_source": fallback_by_source,
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        f"{len(items)} articles; "
        f"{sum(x['ok'] for x in status)}/{len(status)} sources OK"
    )

    print(
        f"Image fallback: checked "
        f"{sum(source_fetch_count.values())} articles; "
        f"found {fallback_count} additional images"
    )


if __name__ == "__main__":
    main()
```
