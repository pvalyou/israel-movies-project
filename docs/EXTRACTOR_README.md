# Film Governance Data Extractor

Local Python tools for extracting and structuring Israeli film industry entities, relationships, and conflicts from scraped web data.

**No API calls • No tokens spent • Runs entirely offline on your Mac**

---

## What It Does

Processes 200+ scraped files (meta.json + markdown pairs) to extract:
- **Entities**: People, organizations, films, funds, events
- **Relationships**: who works where, who funds what, evaluator-beneficiary links
- **Conflicts**: dual roles, evaluator-beneficiary overlap, fund concentration
- **Temporal data**: years, dates of involvement

Output formats: **JSON** (for databases/APIs), **CSV** (for spreadsheets/analysis)

---

## Setup

### 1. Organize Your Scraped Data

Your files should be in a directory like this:

```
~/film_data_scraped/
├── arava_film_fund__root__fb252d5f_meta.json
├── arava_film_fund__root__fb252d5f.md
├── arava_film_fund__root__7d953b11_meta.json
├── arava_film_fund__root__7d953b11.md
├── arava_film_fund__news__ed3b74b9_meta.json
├── arava_film_fund__news__ed3b74b9.md
└── ... (200+ more pairs)
```

Each meta.json should have a corresponding .md file with the same base name.

### 2. No Installation Required

Python 3.7+ comes standard on macOS. Just use the scripts directly:

```bash
python3 film_data_extractor.py ~/path/to/your/film_data_scraped ~/path/to/output
```

---

## Usage

### Basic Extraction

```bash
python3 film_data_extractor.py ~/film_data_scraped ~/output/results
```

This will:
1. Scan all meta.json files in the input directory
2. Load corresponding markdown files
3. Extract entities and relationships
4. Detect conflicts-of-interest
5. Export to JSON and CSV files

### Output Files

After running, you'll get:

#### `extracted_entities.json` (Main output)
```json
{
  "extraction_metadata": {
    "extracted_at": "2026-05-09T...",
    "total_files_processed": 247,
    "entity_counts": {
      "people": 312,
      "organizations": 45,
      "relationships": 1204,
      "conflicts": 89
    }
  },
  "entities": {
    "people": {
      "משה_אדרי": {
        "name": "משה אדרי",
        "sources": ["https://aravaff.co.il/", ...],
        "organizations": ["קרן רבינוביץ", ...],
        "roles": ["מפיק", "משקיע"],
        "dates": ["2015", "2019", "2021"]
      }
    },
    "organizations": {...},
    "films": {...},
    "events": {...}
  },
  "relationships": [
    {
      "person": "משה אדרי",
      "organization": "קרן רבינוביץ",
      "source_url": "https://...",
      "source_file": "arava_film_fund__root__fb252d5f_meta.json"
    }
  ],
  "conflicts": [
    {
      "type": "evaluator_and_beneficiary",
      "person": "יואב אברמוביץ",
      "roles": ["לקטור", "מנכל"]
    }
  ]
}
```

#### `relationships.csv`
```csv
person,organization,source_url,source_file
משה אדרי,קרן רבינוביץ,https://aravaff.co.il/,arava_film_fund__root__fb252d5f_meta.json
יואב אברמוביץ,קרן רבינוביץ,https://...,arava_film_fund__root__7d953b11_meta.json
```

#### `people.csv`
```csv
name,source_count,years_mentioned,sources
משה אדרי,47,2015,2016,2017,2019,2020,2021,https://aravaff.co.il/; https://...
יואב אברמוביץ,31,2015,2019,2020,2021,https://...; https://...
```

---

## Next Steps: Using the Output

### Option 1: Import to Excel/Sheets
Open `relationships.csv` or `people.csv` in Excel/Google Sheets for analysis.

### Option 2: Build a Graph Database
The JSON structure is ready for import to:
- **Neo4j** (graph database) - import relationships directly
- **D3.js** or **Cytoscape.js** - visualize networks
- **Python** (pandas/networkx) - further analysis

Example pandas import:
```python
import pandas as pd
import json

# Load JSON
with open('extracted_entities.json') as f:
    data = json.load(f)

# Convert to DataFrames
entities_df = pd.DataFrame(data['entities']['people']).T
rels_df = pd.DataFrame(data['relationships'])

# Analyze
print(entities_df.groupby('organization').size())  # People per org
```

### Option 3: Interactive Mapping Tool
The relationship data feeds directly into your prototype at `pvalyou.github.io/israel-movies-project/`

---

## Advanced Usage

### Run Both Extractors

The repository includes two tools:

1. **`film_data_extractor.py`** (Simple, fast)
   - Basic entity extraction
   - Good starting point
   
2. **`advanced_film_extractor.py`** (Enhanced patterns)
   - Domain-specific Hebrew patterns
   - Better role detection
   - Conflict inference

Run both for comparison:
```bash
python3 film_data_extractor.py ~/scraped ~/output/basic
python3 advanced_film_extractor.py ~/scraped ~/output/advanced
```

### Customize Patterns

Edit the role/organization patterns in the script:

```python
self.role_patterns = {
    'ceo': r'מנכ"ל|מנהל כללי',
    'your_custom_role': r'your|patterns|here',
}

self.fund_names = {
    'your_fund': ['קרן שם', 'alias'],
}
```

---

## Troubleshooting

### "No meta.json files found"
- Check the input directory path
- Ensure files follow naming: `name_meta.json` + `name.md`

### "Error loading file"
- Verify JSON is valid (use `jq` or JSON validator)
- Check file encoding is UTF-8

### Slow processing (200+ files)
- This is normal; each file takes ~10-50ms
- For 200+ files: expect 2-5 minutes total
- The tool is **not** calling external APIs, so it's as fast as local disk I/O

### Missing entities
- Current patterns focus on Hebrew names
- To add English names or specific titles, edit the regex patterns
- Run with verbose output: add `--verbose` flag (if implemented)

---

## Data Quality Notes

⚠️ **Important**

- Extraction uses pattern matching, not NLP
- Hebrew name detection may catch non-names (common words)
- Manual review of output is recommended for accuracy
- Year extraction includes all 4-digit numbers (may include IDs, amounts)

**Next step**: Review output → Clean obvious noise → Import to visualization tool

---

## For P-Valyou Team

This extractor is designed to feed the relationship mapping platform. 

**Integration flow**:
```
Scraped web data (meta.json + markdown)
    ↓
film_data_extractor.py
    ↓
extracted_entities.json (structured format)
    ↓
Normalize data (merge duplicates, add context)
    ↓
Israel Movies relationship platform
    ↓
Interactive mapping visualization
```

The JSON output is ready for:
- Entity deduplication (people with slight name variations)
- Manual annotation (add conflict evidence, dates)
- Import to Neo4j or Cytoscape for visualization
- Direct feed to the platform's data layer

---

## Questions?

If you need to:
- Add custom patterns for specific organizations
- Change output format
- Handle additional file types (PDF, XLSX)
- Integrate with your existing pipeline

→ Let me know and we can adapt the tool locally!
