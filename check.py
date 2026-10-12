#!/usr/bin/env python3
"""
ARG Monitor – rozbudowana wersja
- Sprawdza stronę główną + kluczowe podstrony
- Wykrywa każdą zmianę (hash SHA-256)
- Zapisuje pełne snapshoty do archive/
- Generuje czytelny diff
- Wysyła ładne powiadomienie na Discorda
"""

import hashlib
import json
import os
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from difflib import unified_diff

# ========== KONFIGURACJA ==========

URLS = [
    ("main",        "https://haahaaaahaaaaahah.pl/"),
    ("index",       "https://haahaaaahaaaaahah.pl/index.html"),
    ("zdjecia",     "https://haahaaaahaaaaahah.pl/zdjecia.html"),
    ("nagrania",    "https://haahaaaahaaaaahah.pl/nagrania.html"),
    ("ferma",       "https://haahaaaahaaaaahah.pl/ferma.html"),
    ("toniejejwina","https://haahaaaahaaaaahah.pl/toniejejwina.html"),
    ("tura3",       "https://haahaaaahaaaaahah.pl/tura3/"),
]

STATE_FILE = Path("state.json")
ARCHIVE_DIR = Path("archive")
MAX_DIFF_CHARS = 1800          # limit znaków diffu w wiadomości Discord
USER_AGENT = "ARG-Monitor/2.0 (+github-actions)"

# ========== POMOCNICZE ==========

def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=25) as resp:
        return resp.read()

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}

def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

def clean_text(html: bytes) -> str:
    """Upraszcza HTML do porównywania (usuwa zbędne białe znaki)."""
    text = html.decode("utf-8", errors="replace")
    # zredukuj wielokrotne białe znaki
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text

def make_diff(old: str, new: str, name: str) -> str:
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff = unified_diff(old_lines, new_lines, fromfile=f"stary/{name}", tofile=f"nowy/{name}", n=2)
    return "".join(diff)

def truncate(s: str, limit: int = MAX_DIFF_CHARS) -> str:
    if len(s) <= limit:
        return s
    return s[:limit] + "\n… (ucięte)"

def send_discord(content: str, embeds: list | None = None):
    webhook = os.environ.get("DISCORD_WEBHOOK")
    if not webhook:
        print("Brak DISCORD_WEBHOOK – pomijam powiadomienie")
        return

    payload = {"content": content}
    if embeds:
        payload["embeds"] = embeds

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"Discord OK ({resp.status})")
    except Exception as e:
        print(f"Discord błąd: {e}")

# ========== GŁÓWNA LOGIKA ==========

def main():
    ARCHIVE_DIR.mkdir(exist_ok=True)
    state = load_state()
    changes = []          # lista dictów ze zmianami
    errors = []

    for key, url in URLS:
        try:
            raw = fetch(url)
            h = sha256(raw)
            text = clean_text(raw)
            old_hash = state.get(key, {}).get("hash")

            entry = {
                "url": url,
                "hash": h,
                "size": len(raw),
                "checked_at": utcnow(),
            }

            if old_hash is None:
                # pierwsze uruchomienie – zapisujemy bazę
                print(f"[NEW]  {key}: zapisuję pierwszą wersję ({h[:12]}…)")
                snap_path = ARCHIVE_DIR / f"{key}_initial.html"
                snap_path.write_bytes(raw)
                entry["file"] = str(snap_path)
                state[key] = entry

            elif old_hash != h:
                # === ZMIANA ===
                print(f"[CHG]  {key}: {old_hash[:12]}… → {h[:12]}…")
                ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                new_file = ARCHIVE_DIR / f"{key}_{ts}.html"
                new_file.write_bytes(raw)

                # spróbuj wczytać poprzednią treść do diffa
                old_text = ""
                prev_file = state[key].get("file")
                if prev_file and Path(prev_file).exists():
                    old_text = clean_text(Path(prev_file).read_bytes())

                diff_text = make_diff(old_text, text, key) if old_text else "(brak poprzedniej wersji do porównania)"

                changes.append({
                    "key": key,
                    "url": url,
                    "old_hash": old_hash,
                    "new_hash": h,
                    "file": str(new_file),
                    "diff": diff_text,
                    "size": len(raw),
                })

                entry["file"] = str(new_file)
                state[key] = entry

            else:
                print(f"[OK]   {key}: bez zmian")
                # aktualizujemy tylko timestamp
                state[key]["checked_at"] = utcnow()

        except Exception as e:
            msg = f"{key} ({url}): {e}"
            print(f"[ERR]  {msg}")
            errors.append(msg)

    save_state(state)

    # ----- Powiadomienia -----
    if changes:
        lines = [f"**ARG – wykryto {len(changes)} zmian(y)!**", f"`{utcnow()}`", ""]
        embeds = []

        for c in changes:
            lines.append(f"• **{c['key']}** → `{c['url']}`")
            lines.append(f"  `{c['old_hash'][:10]}…` → `{c['new_hash'][:10]}…`")

            # embed z diffem (Discord limit ~4096 na description)
            diff_preview = truncate(c["diff"], 3500)
            embeds.append({
                "title": f"Zmiana: {c['key']}",
                "url": c["url"],
                "description": f"```diff\n{diff_preview}\n```",
                "color": 0xF85149,  # czerwony
                "footer": {"text": f"rozmiar: {c['size']} B"},
            })

        content = "\n".join(lines)
        # Discord pozwala max 10 embedów
        send_discord(content, embeds[:10])

        print("\n=== PODSUMOWANIE ZMIAN ===")
        for c in changes:
            print(f"  {c['key']}: zapisano {c['file']}")
    else:
        print("Brak zmian.")

    if errors:
        send_discord("**ARG Monitor – błędy:**\n" + "\n".join(f"• {e}" for e in errors))

if __name__ == "__main__":
    main()
