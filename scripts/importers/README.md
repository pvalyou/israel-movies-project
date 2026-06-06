# scripts/importers/

Write hand-curated or specially-parsed data directly into `out/<source>/mentions.jsonl`, bypassing the LLM scraping pipeline. Used when a source has no scrapeable web page (board lists, PDF rosters, guild data), or when the LLM extraction missed content.

All importers support `--dry-run` to preview output without writing. They are **idempotent** — re-running appends a new synthetic entry with a fresh hash but does not duplicate people.

---

## import_fdoc_board.py

Imports the Forum for Documentary Film (fdoc) board of directors.

- Source: `https://www.fdoc.org.il/הנהלה/` (term 2024–2026)
- Output: `out/fdoc/mentions.jsonl`

```bash
python3 scripts/importers/import_fdoc_board.py [--dry-run]
```

---

## import_film_faculty.py

Imports film school faculty (Sam Spiegel, Sapir College, Tel Aviv University) from the pre-collected JSON file.

- Source: `film_faculty_data/faculty_members.json`
- Output: `out/film_schools/mentions.jsonl`

```bash
python3 scripts/importers/import_film_faculty.py [--dry-run]
```

---

## import_filmfund_lectors.py

Imports Israel Film Fund lectors from the seed JSON file into the filmfund source.

- Source: `sources/filmfund/lecturers_israel.json`
- Output: `out/filmfund/mentions.jsonl`

```bash
python3 scripts/importers/import_filmfund_lectors.py [--dry-run]
```

---

## import_gesher_lectors.py

Imports Gesher Film Fund lectors for all rounds 2015–2025 from the scraped page. This was created because the LLM returned 0 people for the Gesher lectors page (content too long for the model's context).

- Source: `https://gesherfilmfund.org.il/Page/45/`
- Output: `out/gesher/mentions.jsonl`

```bash
python3 scripts/importers/import_gesher_lectors.py [--dry-run]
```

---

## import_guilds_boards.py

Imports board members for the Directors Guild and Producers Guild.

- Sources: `directorsguild.org.il`, `producers.org.il` (accessed 2026-05-26)
- Output: `out/guilds/mentions.jsonl`

```bash
python3 scripts/importers/import_guilds_boards.py [--dry-run]
```

---

## import_haifa_film_festival.py

Imports Haifa Film Festival staff and board.

- Source: `https://www.haifaff.co.il/צוות_הפסטיבל` (accessed 2026-05-26)
- Output: `out/haifa_film_festival/mentions.jsonl`

```bash
python3 scripts/importers/import_haifa_film_festival.py [--dry-run]
```

---

## import_israeli_film_academy.py

Imports Israeli Film Academy (Ophir Prize) board and staff.

- Source: `https://israelfilmacademy.co.il/?section=590` (accessed 2026-05-27)
- Output: `out/israeli_film_academy/mentions.jsonl`

```bash
python3 scripts/importers/import_israeli_film_academy.py [--dry-run]
```

---

## import_jerusalem_cinematheque.py

Imports Jerusalem Cinematheque staff and board.

- Sources: staff page `jer-cin.org.il/he/מאמר/4202`, board page `.../4204` (accessed 2026-05-26)
- Output: `out/jerusalem_cinematheque/mentions.jsonl`

```bash
python3 scripts/importers/import_jerusalem_cinematheque.py [--dry-run]
```

---

## import_rabinovich_films.py

Parses Rabinovich Cinema Project funded-film PDFs (OCR'd via Gemini) and writes film + crew records.

- Source: `sources/rabinovich_cinema/files/rabinovich__films_ocr.json`
  (keys: `films2023`, `projects2015`, `budget2020_2025`)
- Output: `out/rabinovich_cinema/mentions.jsonl`

```bash
python3 scripts/importers/import_rabinovich_films.py [--dry-run]
```

---

## import_rabinovich_lectors.py

Parses 5 Rabinovich Cinema Project lector PDFs (2013–2025). These PDFs have per-character reversed Hebrew tokens due to RTL encoding — the importer handles reversal automatically.

- Source: `sources/rabinovich_cinema/files/*.pdf` (pre-extracted text)
- Output: `out/rabinovich_cinema/mentions.jsonl`

```bash
python3 scripts/importers/import_rabinovich_lectors.py [--dry-run]
```

---

## import_writers_guild_board.py

Imports Israeli Screenwriters Guild board members.

- Sources: Wikipedia + `writersguild.org.il` (accessed 2026-05-27)
- Output: `out/writers_guild/mentions.jsonl`

```bash
python3 scripts/importers/import_writers_guild_board.py [--dry-run]
```
