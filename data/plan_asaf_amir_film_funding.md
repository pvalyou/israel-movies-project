# Research Plan: Film Fund Sources for אסף אמיר's Films

## Goal

Find which Israeli film fund(s) supported each film in אסף אמיר's filmography.
Write results to `/Users/moran/projects/israeli-movies-ind/data/asaf_amir_film_funding.json`.

## Films to Research

| # | Title (Hebrew) | Year |
|---|----------------|------|
| 1 | כרוניקה של היעלמות | 1996 |
| 2 | עפולה אקספרס | 1997 |
| 3 | בלש בירושלים | 1998 |
| 4 | לתפוס את השמיים | 2002 |
| 5 | כנפיים שבורות | 2003 |
| 6 | ריקי ריקי | 2004 |
| 7 | מועדון בית הקברות | 2006 |
| 8 | טלי פחימה: חוצה את הקווים | 2006 |
| 9 | ציון ואחיו | 2009 |
| 10 | מגדלים באויר | 2009 |
| 11 | הזמן הוורוד | 2009 |
| 12 | הבודדים | 2009 |
| 13 | בין השמשות | 2010 |
| 14 | הדקדוק הפנימי | 2010 |
| 15 | דור שלם דרש שלום | 2010 |

## Sources to Check (in order)

### 1. Israeli Film Fund — filmfund.org.il
Search each film title:
```
https://www.filmfund.org.il/Search?q=<film-title-in-hebrew>
```
Or browse by movie ID:
```
https://www.filmfund.org.il/Movie?movieId=<id>
```
Record: movie page URL, support amount if shown.

### 2. Rabinovich Foundation — rcy.co.il
- Homepage: `https://www.rcy.co.il`
- Look for "פרויקטים נתמכים" / "סרטים"
- Or search: `site:rcy.co.il "<film title>"`

### 3. NFCT (New Fund for Cinema & TV) — nfct.org.il
- Homepage: `https://www.nfct.org.il`
- Look for supported films list
- Or search: `site:nfct.org.il "<film title>"`

### 4. Gesher Film Fund — gesherfilmfund.co.il
- Homepage: `https://www.gesherfilmfund.co.il`
- Look for films/projects section

### 5. Makor Foundation — makorfilm.org.il
- Homepage: `https://www.makorfilm.org.il`

### 6. Jerusalem Film Fund — jff.org.il or jerusalem-film.co.il
- Search site for each title

### 7. Fallback: Web Search + Hebrew Wikipedia
For each film still unfound after steps 1–6:
- Google search: `"<film title>" "קרן הקולנוע"`
- Google search: `"<film title>" "קרן רבינוביץ'" OR "הקרן החדשה" OR "גשר"`
- Hebrew Wikipedia: search `<film title>` — fund is often listed in the infobox under "מימון" or "הפקה"

## Output File

Write to: `/Users/moran/projects/israeli-movies-ind/data/asaf_amir_film_funding.json`

### Schema

```json
[
  {
    "film_title_he": "כרוניקה של היעלמות",
    "year": 1996,
    "funds": ["filmfund"],
    "fund_labels": ["הקרן הישראלית לקולנוע"],
    "source_urls": ["https://www.filmfund.org.il/Movie?movieId=123"],
    "filmfund_movie_id": 123,
    "support_amount_ils": null,
    "confidence": "confirmed",
    "notes": ""
  }
]
```

### Fund key → label mapping

| Key | Label |
|-----|-------|
| `filmfund` | הקרן הישראלית לקולנוע |
| `rabinovich` | קרן רבינוביץ' לאמנויות |
| `nfct` | הקרן החדשה לקולנוע ולטלוויזיה |
| `gesher` | קרן גשר לקולנוע |
| `makor` | קרן מקור |
| `jff` | קרן ירושלים לקולנוע |

### Confidence values
- `confirmed` — fund page or Wikipedia infobox directly names the film
- `probable` — strong secondary source (press article, interview) names the fund
- `unverified` — no source found

## Notes

- אסף אמיר is credited as יוצר / מפיק / תסריטאי on all listed films (source: EDB — Israeli Film Database).
- He has served as Israeli Film Academy Chair since 2019, and as lector at multiple funds — so establishing which funds supported his films is the core of the conflict-of-interest case.
- If a film was supported by multiple funds, list all of them.
- If nothing is found for a film, still include it in the output JSON with `"funds": []` and `"confidence": "unverified"`.
