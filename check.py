#!/usr/bin/env python3
"""
ARG Monitor v3 – pełna wersja
- Wszystkie znane podstrony
- Skanowanie nowych podstron
- Przy zmianie: nowy folder z datą/godziną
- W folderze: HTML + wszystkie media z danej podstrony
- Diff + powiadomienie Discord
"""

import hashlib
import json
import os
import re
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from difflib import unified_diff
from html.parser import HTMLParser

# ========== KONFIGURACJA ==========

BASE = "https://haahaaaahaaaaahah.pl"

# Wszystkie znane podstrony (klucz → ścieżka)
KNOWN_PAGES = {
    "main":             "/",
    "index":            "/index.html",
    "zdjecia":          "/zdjecia.html",
    "nagrania":         "/nagrania.html",
    "logowanie":        "/logowanie.html",
    "toniejejwina":     "/toniejejwina.html",
    "ferma":            "/ferma.html",
    "hgsupepmgkug":     "/hgsupepmgkug.html",
    "tura3":            "/tura3/",
    "404":              "/404.html",
    "szukajszczegolow": "/szukajszczegolow/",
}

# Dodatkowe ścieżki do bruteforce'owania (wykrywanie nowych)
DISCOVERY_CANDIDATES = [
    "/admin.html", "/login.html", "/panel.html", "/secret.html",
    "/haslo.html", "/mail.html", "/poczta.html", "/kontakt.html",
    "/o-nas.html", "/about.html", "/news.html", "/aktualnosci.html",
    "/film.html", "/filmy.html", "/video.html", "/videos.html",
    "/foto.html", "/photos.html", "/galeria.html", "/gallery.html",
    "/tura1/", "/tura2/", "/tura4/", "/tura5/",
    "/dok.html", "/dokumenty.html", "/docs.html",
    "/przesluchanie.html", "/ofiara.html", "/potwor.html",
    "/bieniow.html", "/wroclaw.html", "/ferma2.html",
    "/update.html", "/nowe.html", "/new.html",
    "/test.html", "/dev.html", "/staging.html",
    "/robots.txt", "/sitemap.xml",
]

STATE_FILE = Path("state.json")
ARCHIVE_DIR = Path("archive")
MAX_DIFF_CHARS = 3200
USER_AGENT = "ARG-Monitor/3.0 (+github-actions)"
REQUEST_TIMEOUT = 25

# ========== HTML PARSER – zbiera media ==========

class MediaCollector(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.media = set()

    def _abs(self, src: str) -> str | None:
        if not src or src.startswith("data:") or src.startswith("javascript:"):
            return None
        return urllib.parse.urljoin(self.base_url, src)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        candidates = []
        if tag == "img":
            candidates = [attrs.get("src"), attrs.get("data-src"), attrs.get("data-lazy")]
        elif tag == "video":
            candidates = [attrs.get("src"), attrs.get("poster")]
        elif tag == "source":
            candidates = [attrs.get("src")]
        elif tag == "audio":
            candidates = [attrs.get("src")]
        elif tag == "a":
            href = attrs.get("href", "")
            if any(href.lower().endswith(ext) for ext in (
                ".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".webm",
                ".mp3", ".wav", ".pdf", ".zip", ".svg"
            )):
                candidates = [href]
        elif tag == "link" and attrs.get("rel") in ("stylesheet", "icon", "shortcut icon"):
            candidates = [attrs.get("href")]
        elif tag == "script":
            candidates = [attrs.get("src")]

        for c in candidates:
            abs_url = self._abs(c) if c else None
            if abs_url and abs_url.startswith("http"):
                self.media.add(abs_url)

# ========== POMOCNICZE ==========

def utcnow_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def folder_ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")

def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return resp.read()

def fetch_safe(url: str) -> tuple[bytes | None, int | None]:
    """Zwraca (content, status) lub (None, status/None) przy błędzie."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return resp.read(), resp.status
    except urllib.error.HTTPError as e:
        return None, e.code
    except Exception:
        return None, None

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def clean_text(html: bytes) -> str:
    text = html.decode("utf-8", errors="replace")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text

def make_diff(old: str, new: str, name: str) -> str:
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff = unified_diff(
        old_lines, new_lines,
        fromfile=f"stary/{name}", tofile=f"nowy/{name}", n=2
    )
    return "".join(diff)

def truncate(s: str, limit: int = MAX_DIFF_CHARS) -> str:
    if len(s) <= limit:
        return s
    return s[:limit] + "\n… (ucięte)"

def safe_filename(url: str) -> str:
    path = urllib.parse.urlparse(url).path
    name = Path(path).name or "file"
    name = re.sub(r"[^\w.\-]", "_", name)
    return name[:120]

def download_media(urls: set[str], dest_dir: Path) -> list[str]:
    """Pobiera media do dest_dir. Zwraca listę zapisanych plików."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for url in sorted(urls):
        try:
            data, status = fetch_safe(url)
            if data is None:
                continue
            fname = safe_filename(url)
            # unikaj kolizji
            out = dest_dir / fname
            counter = 1
            while out.exists():
                stem = out.stem
                out = dest_dir / f"{stem}_{counter}{out.suffix}"
                counter += 1
            out.write_bytes(data)
            saved.append(str(out.relative_to(dest_dir.parent.parent)) if False else out.name)
            print(f"      media: {fname} ({len(data)} B)")
        except Exception as e:
            print(f"      media FAIL {url}: {e}")
    return saved

def send_discord(content: str, embeds: list | None = None):
    webhook = os.environ.get("DISCORD_WEBHOOK")
    if not webhook:
        print("Brak DISCORD_WEBHOOK – pomijam powiadomienie")
        return
    payload = {"content": content[:1900]}
    if embeds:
        payload["embeds"] = embeds[:10]
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook, data=data,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"Discord OK ({resp.status})")
    except Exception as e:
        print(f"Discord błąd: {e}")

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"pages": {}, "discovered": []}

def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

# ========== ODKRYWANIE NOWYCH STRON ==========

def discover_new_pages(state: dict) -> list[tuple[str, str]]:
    """Sprawdza listę kandydatów + linki z main. Zwraca listę (key, path) nowych."""
    found = []
    known_paths = set(KNOWN_PAGES.values())
    already = set(state.get("discovered", []))

    # 1) bruteforce kandydatów
    for path in DISCOVERY_CANDIDATES:
        if path in known_paths or path in already:
            continue
        url = BASE + path
        data, status = fetch_safe(url)
        if status == 200 and data and len(data) > 50:
            key = path.strip("/").replace("/", "_").replace(".html", "") or "root"
            print(f"[NEW PAGE] Znaleziono: {url} ({status})")
            found.append((key, path))
            already.add(path)
            time.sleep(0.4)

    # 2) wyciągnij linki .html z głównej strony
    try:
        main_data, _ = fetch_safe(BASE + "/")
        if main_data:
            text = main_data.decode("utf-8", errors="replace")
            links = re.findall(r'href=["\']([^"\']+\.html)["\']', text, re.I)
            for link in links:
                full = urllib.parse.urljoin(BASE + "/", link)
                path = urllib.parse.urlparse(full).path
                if not path.startswith("/"):
                    path = "/" + path
                if path in known_paths or path in already:
                    continue
                data, status = fetch_safe(BASE + path)
                if status == 200 and data:
                    key = path.strip("/").replace("/", "_").replace(".html", "")
                    print(f"[NEW PAGE] Z linku: {BASE + path}")
                    found.append((key, path))
                    already.add(path)
                    time.sleep(0.3)
    except Exception as e:
        print(f"Discovery linków: {e}")

    state["discovered"] = list(already)
    return found

# ========== GŁÓWNA LOGIKA ==========

def main():
    ARCHIVE_DIR.mkdir(exist_ok=True)
    state = load_state()
    if "pages" not in state:
        state["pages"] = {}
    if "discovered" not in state:
        state["discovered"] = []

    # --- Odkrywanie nowych podstron ---
    print("=== Skanowanie nowych podstron ===")
    new_pages = discover_new_pages(state)
    for key, path in new_pages:
        KNOWN_PAGES[key] = path

    # --- Sprawdzanie wszystkich stron ---
    print("\n=== Sprawdzanie stron ===")
    changes = []  # lista zmian w tej turze
    errors = []

    for key, path in KNOWN_PAGES.items():
        url = BASE + path
        try:
            raw, status = fetch_safe(url)
            if raw is None:
                print(f"[SKIP] {key}: niedostępna (status={status})")
                continue

            h = sha256(raw)
            text = clean_text(raw)
            prev = state["pages"].get(key, {})
            old_hash = prev.get("hash")

            if old_hash is None:
                print(f"[INIT] {key}: pierwsza wersja ({h[:12]}…)")
                state["pages"][key] = {
                    "hash": h,
                    "url": url,
                    "size": len(raw),
                    "checked_at": utcnow_str(),
                    "path": path,
                }
            elif old_hash != h:
                print(f"[CHG]  {key}: {old_hash[:10]}… → {h[:10]}…")
                changes.append({
                    "key": key,
                    "path": path,
                    "url": url,
                    "old_hash": old_hash,
                    "new_hash": h,
                    "raw": raw,
                    "text": text,
                    "old_text": prev.get("text_preview", ""),
                    "size": len(raw),
                })
                state["pages"][key] = {
                    "hash": h,
                    "url": url,
                    "size": len(raw),
                    "checked_at": utcnow_str(),
                    "path": path,
                    "text_preview": text[:5000],  # do diffa przy następnej zmianie
                }
            else:
                print(f"[OK]   {key}")
                state["pages"][key]["checked_at"] = utcnow_str()

            # zachowaj krótki preview tekstu do przyszłego diffa
            if key in state["pages"] and "text_preview" not in state["pages"][key]:
                state["pages"][key]["text_preview"] = text[:5000]

        except Exception as e:
            msg = f"{key}: {e}"
            print(f"[ERR]  {msg}")
            errors.append(msg)

    # --- Jeśli są zmiany: tworzymy folder wersji ---
    if changes:
        ts = folder_ts()
        version_dir = ARCHIVE_DIR / ts
        version_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n=== Zapisuję wersję → archive/{ts}/ ===")

        summary = {
            "timestamp": utcnow_str(),
            "folder": ts,
            "changes": [],
        }

        embeds = []
        discord_lines = [
            f"**ARG – wykryto {len(changes)} zmian(y)!**",
            f"`{utcnow_str()}`",
            f"Folder: `archive/{ts}/`",
            "",
        ]

        for c in changes:
            page_dir = version_dir / c["key"]
            page_dir.mkdir(exist_ok=True)

            # 1) zapisz HTML
            html_file = page_dir / "index.html"
            html_file.write_bytes(c["raw"])
            print(f"  [{c['key']}] HTML zapisany")

            # 2) zbierz i pobierz media
            parser = MediaCollector(c["url"])
            try:
                parser.feed(c["raw"].decode("utf-8", errors="replace"))
            except Exception:
                pass
            media_dir = page_dir / "media"
            saved_media = download_media(parser.media, media_dir)
            print(f"  [{c['key']}] media: {len(saved_media)} plików")

            # 3) diff
            old_text = c.get("old_text") or ""
            if not old_text:
                # spróbuj z poprzedniego stanu
                old_text = state["pages"].get(c["key"], {}).get("text_preview", "")
            diff_text = make_diff(old_text, c["text"], c["key"]) if old_text else "(pierwsza zapisana zmiana – brak poprzedniej treści do diffa)"
            diff_file = page_dir / "diff.txt"
            diff_file.write_text(diff_text, encoding="utf-8")

            # 4) meta
            meta = {
                "key": c["key"],
                "url": c["url"],
                "path": c["path"],
                "old_hash": c["old_hash"],
                "new_hash": c["new_hash"],
                "size": c["size"],
                "media_count": len(saved_media),
                "media_files": saved_media,
            }
            (page_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

            summary["changes"].append(meta)

            discord_lines.append(f"• **{c['key']}** → `{c['url']}`")
            discord_lines.append(f"  `{c['old_hash'][:10]}…` → `{c['new_hash'][:10]}…` · media: {len(saved_media)}")

            embeds.append({
                "title": f"Zmiana: {c['key']}",
                "url": c["url"],
                "description": f"```diff\n{truncate(diff_text, 3500)}\n```",
                "color": 0xF85149,
                "footer": {"text": f"{c['size']} B · media: {len(saved_media)}"},
            })

        # summary całej wersji
        (version_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # jeśli odkryto nowe strony – dopisz do discorda
        if new_pages:
            discord_lines.append("")
            discord_lines.append("**Nowe podstrony:**")
            for key, path in new_pages:
                discord_lines.append(f"• `{BASE + path}`")

        send_discord("\n".join(discord_lines), embeds)
        print(f"\nZapisano wersję: archive/{ts}/")
    else:
        print("\nBrak zmian w treści stron.")
        if new_pages:
            lines = ["**ARG – odkryto nowe podstrony!**", f"`{utcnow_str()}`", ""]
            for key, path in new_pages:
                lines.append(f"• `{BASE + path}`")
            send_discord("\n".join(lines))

    if errors:
        send_discord("**ARG Monitor – błędy:**\n" + "\n".join(f"• {e}" for e in errors))

    save_state(state)
    print("\nGotowe.")

if __name__ == "__main__":
    main()
