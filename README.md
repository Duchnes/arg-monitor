# ARG Monitor – rozbudowany

Automatyczny monitoring strony **haahaaaahaaaaahah.pl** z:

- wykrywaniem **każdej** zmiany (nawet 1 litera)
- zapisem pełnych snapshotów HTML do folderu `archive/`
- generowaniem **diffu** (co dokładnie się zmieniło)
- ładnymi powiadomieniami na **Discord**

Działa 24/7 za darmo dzięki GitHub Actions (co 10 minut).

---

## Szybki start (5–7 minut)

### 1. Stwórz repozytorium
1. Wejdź na [github.com/new](https://github.com/new)
2. Nazwa np. `arg-monitor`
3. Ustaw na **Private** (zalecane)
4. Kliknij **Create repository**

### 2. Wrzuć pliki
Skopiuj do repo te pliki:
```
.github/workflows/monitor.yml
check.py
README.md
```

Najłatwiej:
- kliknij **uploading an existing file**
- albo użyj gita lokalnie

### 3. Discord Webhook
1. Na Discordzie: Ustawienia serwera → **Integracje** → **Webhooki** → Nowy webhook
2. Wybierz kanał i skopiuj **URL webhooka**
3. W repo GitHub: **Settings → Secrets and variables → Actions → New repository secret**
4. Name: `DISCORD_WEBHOOK`
5. Value: wklej URL webhooka

### 4. Uruchom pierwszy raz
1. Zakładka **Actions**
2. Wybierz workflow **ARG Monitor (rozbudowany)**
3. **Run workflow** → Run workflow

Po pierwszym uruchomieniu zapisze się stan początkowy (bez alarmu).

---

## Co dostaniesz na Discordzie przy zmianie

```
ARG – wykryto 1 zmian(y)!
`2026-10-12T22:30:00Z`

• tura3 → https://haahaaaahaaaaahah.pl/tura3/
  `a1b2c3d4e5…` → `f6g7h8i9j0…`
```

+ **embed** z diffem (fragment zmian w formacie diff).

---

## Co jest w repozytorium

| Plik / folder      | Opis                                      |
|--------------------|-------------------------------------------|
| `state.json`       | aktualne hashe wszystkich stron           |
| `archive/`         | pełne kopie HTML (każda zmiana = nowy plik) |
| `check.py`         | skrypt monitorujący                       |
| `.github/workflows/monitor.yml` | harmonogram Actions              |

---

## Częstotliwość

Domyślnie **co 10 minut**.  
Możesz zmienić w `monitor.yml`:

```yaml
- cron: '*/5 * * * *'   # co 5 minut (agresywniej)
- cron: '*/15 * * * *'  # co 15 minut (oszczędniej)
```

GitHub Free ma limit minut – przy sprawdzaniu co 10 min spokojnie się mieścisz.

---

## Ręczne odpalenie

Actions → ARG Monitor → **Run workflow**

---

## Rozszerzanie

Chcesz dodać kolejne podstrony?  
Edytuj listę `URLS` w `check.py`:

```python
URLS = [
    ("main", "https://haahaaaahaaaaahah.pl/"),
    ("nowa", "https://haahaaaahaaaaahah.pl/nowa-strona.html"),
    ...
]
```
