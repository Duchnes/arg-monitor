#!/usr/bin/env python3
"""
ARG Monitor v3 – tylko znane strony (bez bruteforce / discovery)
- Sprawdza wyłącznie listę KNOWN_PAGES
- Przy zmianie: nowy folder z datą/godziną
- W folderze: HTML + wszystkie media z danej podstrony
- Diff + powiadomienie Discord
"""
import hashlib
import json
import os
import re
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from difflib import unified_diff
from html.parser import HTMLParser

# ========== KONFIGURACJA ==========
BASE = "https://haahaaaahaaaaahah.pl"

# Tylko znane podstrony / pliki – bez bruteforce'a i discovery
# Uwaga: pierwsze INIT nowej strony NIE wysyła webhooka (tylko prawdziwa zmiana hasha)
KNOWN_PAGES = {
    # --- główne / aktualne ---
    "main":                 "/",
    "index":                "/index.html",
    "zdjecia":              "/zdjecia.html",
    "nagrania":             "/nagrania.html",
    "toniejejwina":         "/toniejejwina.html",
    "gdziejestpotwor":      "/gdziejestpotwor.html",
    "tojegowina":           "/tojegowina.html",
    "tuniemazadnychwojen":  "/tuniemazadnychwojen.html",

    # --- logowanie / formularze ---
    "login_php":            "/login.php",
    "imie_php":             "/imie.php",
    "dobrywybor":           "/dobrywybor/",

    # --- dane ---
    "ofiary_json":          "/ofiary.json",

    # --- znane media z /szukajszczegolow/ ---
    "szukaj_poszukiwaniapotwora_mp4": "/szukajszczegolow/poszukiwaniapotwora.mp4",
    "szukaj_ofiara_jpg":              "/szukajszczegolow/ofiara.jpg",

    # --- novumcapitulum (zdjęcia + wideo + dokumenty) ---
    "novum_1":       "/novumcapitulum/1.jpg",
    "novum_2":       "/novumcapitulum/2.jpg",
    "novum_3":       "/novumcapitulum/3.jpg",
    "novum_4":       "/novumcapitulum/4.jpg",
    "novum_5":       "/novumcapitulum/5.jpg",
    "novum_6":       "/novumcapitulum/6.jpg",
    "novum_7":       "/novumcapitulum/7.jpg",
    "novum_8":       "/novumcapitulum/8.jpg",
    "novum_video1":  "/novumcapitulum/Video1.mp4",
    "novum_video2":  "/novumcapitulum/Video2.mp4",
    "novum_dok1":    "/novumcapitulum/dok1.jpg",
    "novum_dok2":    "/novumcapitulum/dok2.jpg",
    "novum_dok3":    "/novumcapitulum/dok3.jpg",

    # --- poprzednie (zostawione na wypadek powrotu) ---
    "logowanie":            "/logowanie.html",
    "ferma":                "/ferma.html",
    "hgsupepmgkug":         "/hgsupepmgkug.html",
    "tura3":                "/tura3/",
    "404":                  "/404.html",
    "liszt":                "/liszt.html",
    "szukajszczegolow":     "/szukajszczegolow/",
}

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
                ".mp3", ".wav", ".pdf", ".zip", ".svg", ".txt"
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


def is_binary_path(path: str) -> bool:
    return any(path.lower().endswith(ext) for ext in (
        ".mp4", ".webm", ".jpg", ".jpeg", ".png", ".gif", ".webp",
        ".mp3", ".wav", ".pdf", ".zip"
    ))


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
            out = dest_dir / fname
            counter = 1
            while out.exists():
                stem = out.stem
                out = dest_dir / f"{stem}_{counter}{out.suffix}"
                counter += 1
            out.write_bytes(data)
            saved.append(out.name)
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
    return {"pages": {}}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


# ========== GŁÓWNA LOGIKA ==========
def main():
    ARCHIVE_DIR.mkdir(exist_ok=True)
    state = load_state()
    if "pages" not in state:
        state["pages"] = {}

    print("=== Sprawdzanie znanych stron ===")
    changes = []
    errors = []

    for key, path in sorted(KNOWN_PAGES.items()):
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
                    "text_preview": text[:5000],
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
                    "text_preview": text[:5000],
                }
            else:
                print(f"[OK]   {key}")
                state["pages"][key]["checked_at"] = utcnow_str()

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

            # 1) zapisz HTML / plik
            if is_binary_path(c["path"]) or c["path"].lower().endswith((".txt", ".json", ".php")):
                fname = safe_filename(c["url"])
                (page_dir / fname).write_bytes(c["raw"])
                print(f"  [{c['key']}] plik zapisany: {fname}")
            else:
                html_file = page_dir / "index.html"
                html_file.write_bytes(c["raw"])
                print(f"  [{c['key']}] HTML zapisany")

            # 2) zbierz i pobierz media (tylko dla HTML)
            saved_media = []
            if c["path"].endswith(".html") or c["path"].endswith("/"):
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
                old_text = state["pages"].get(c["key"], {}).get("text_preview", "")

            if is_binary_path(c["path"]):
                diff_text = f"(plik binarny – rozmiar: {c['size']} B, hash: {c['new_hash'][:16]}…)"
            else:
                diff_text = (
                    make_diff(old_text, c["text"], c["key"])
                    if old_text
                    else "(pierwsza zapisana zmiana – brak poprzedniej treści do diffa)"
                )

            (page_dir / "diff.txt").write_text(diff_text, encoding="utf-8")

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
            (page_dir / "meta.json").write_text(
                json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            summary["changes"].append(meta)

            discord_lines.append(f"• **{c['key']}** → `{c['url']}`")
            discord_lines.append(
                f"  `{c['old_hash'][:10]}…` → `{c['new_hash'][:10]}…` · media: {len(saved_media)}"
            )

            embeds.append({
                "title": f"Zmiana: {c['key']}",
                "url": c["url"],
                "description": f"```diff\n{truncate(diff_text, 3500)}\n```",
                "color": 0xF85149,
                "footer": {"text": f"{c['size']} B · media: {len(saved_media)}"},
            })

        (version_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        send_discord("\n".join(discord_lines), embeds)
        print(f"\nZapisano wersję: archive/{ts}/")
    else:
        print("\nBrak zmian w treści stron.")

    if errors:
        send_discord("**ARG Monitor – błędy:**\n" + "\n".join(f"• {e}" for e in errors))

    save_state(state)
    print("\nGotowe.")


if __name__ == "__main__":
    main()
