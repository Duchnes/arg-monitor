# ARG Monitor v3

Pełny monitoring **haahaaaahaaaaahah.pl** 24/7 (GitHub Actions).

## Co robi

- Sprawdza wszystkie znane podstrony
- **Skanuje nowe** podstrony (bruteforce + linki z main)
- Przy **jakiejkolwiek** zmianie tworzy nowy folder wersji
- W folderze zapisuje:
  - HTML każdej zmienionej strony
  - **wszystkie media** (obrazy, wideo, pliki) z tej strony
  - diff.txt (co się zmieniło)
  - meta.json
- Wysyła powiadomienie na Discord z diffem

## Struktura archiwum

```
archive/
  2026-10-12_22-30-15/          ← jedna wersja (jeden update)
    summary.json
    tura3/
      index.html
      diff.txt
      meta.json
      media/
        1.JPG
        2.JPG
        ...
    zdjecia/
      index.html
      media/
        ...
  2026-10-13_01-05-00/
    ...
```

## Monitorowane strony (startowe)

| Klucz | URL |
|-------|-----|
| main | https://haahaaaahaaaaahah.pl/ |
| index | /index.html |
| zdjecia | /zdjecia.html |
| nagrania | /nagrania.html |
| logowanie | /logowanie.html |
| toniejejwina | /toniejejwina.html |
| ferma | /ferma.html |
| hgsupepmgkug | /hgsupepmgkug.html |
| tura3 | /tura3/ |
| 404 | /404.html |
| szukajszczegolow | /szukajszczegolow/ |

+ automatyczne odkrywanie nowych.

## Setup (raz)

1. Stwórz **prywatne** repo na GitHubie
2. Wrzuć te pliki
3. **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `DISCORD_WEBHOOK`
   - Value: URL webhooka Discord
4. Actions → **ARG Monitor v3** → Run workflow

## Discord

Przy zmianie dostaniesz:
- listę zmienionych stron
- folder w `archive/`
- embed z **diffem** (co dokładnie się zmieniło)
- liczbę pobranych mediów

## Częstotliwość

Domyślnie co **10 minut**. Zmień w `.github/workflows/monitor.yml` jeśli chcesz inaczej.
