# Format Recommendation: JSON + CSV for Film Governance Data

## Your Question: "What is the best format?"

**Answer: Use JSON for structure, CSV for quick analysis**

### Why This Combination?

| Format | Best For | Your Use Case |
|--------|----------|--------------|
| **JSON** | Machine-readable structured data | ✅ Feed to visualization platform, databases, APIs |
| **CSV** | Human analysis, spreadsheets, quick checks | ✅ Review data in Excel, identify patterns, manual cleanup |
| **Graph DB** | Relationship queries | 🔄 Later step (Neo4j/Cytoscape) |

---

## Recommended Data Flow (for P-Valyou)

```
┌─────────────────────────────────────────────────────────┐
│  Step 1: EXTRACTION (Offline, on your Mac)              │
│  Your 200+ scraped files → Python extractor script     │
│  Output: extracted_entities.json + CSV files            │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  Step 2: REVIEW & CLEAN (Manual)                       │
│  Open CSVs in Excel → Remove duplicates/noise           │
│  Add context: verified facts, conflict evidence         │
│  Output: cleaned_relationships.csv                      │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  Step 3: STRUCTURE (Optional - for platform)           │
│  Import cleaned CSV → normalize names/orgs              │
│  Add conflict tags, verify sources                      │
│  Output: normalized_entities.json                       │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  Step 4: VISUALIZE (Your Platform)                     │
│  pvalyou.github.io/israel-movies-project/              │
│  Interactive relationship mapping + conflict detection  │
└─────────────────────────────────────────────────────────┘
```

---

## Output Format Specifications

### 1. `extracted_entities.json` (Primary output)

**Structure**:
```json
{
  "metadata": {
    "extraction_date": "2026-05-09T14:32:15Z",
    "files_processed": 247,
    "entities_found": {
      "people": 312,
      "organizations": 45,
      "films": 87,
      "funds": 12
    }
  },
  
  "entities": {
    "people": {
      "moshe_aderi": {
        "id": "moshe_aderi",
        "name": "משה אדרי",
        "name_en": "Moshe Aderi",
        "entity_type": "person",
        "roles": ["producer", "distributor", "investor"],
        "organizations": ["rabinovich_fund", "gesher_fund", "united_kinng"],
        "timeline": {
          "years_active": ["2015", "2016", "2017", "2018", "2019", "2020", "2021"],
          "first_mention": 2015,
          "last_mention": 2021
        },
        "sources": {
          "url_count": 47,
          "sample_urls": [
            "https://aravaff.co.il/#main",
            "https://filmfund.org.il/..."
          ]
        },
        "metadata": {
          "confidence": 0.95,
          "needs_verification": false
        }
      },
      
      "giora_eini": {
        "id": "giora_eini",
        "name": "גיורא עיני",
        "name_en": "Giora Eini",
        "entity_type": "person",
        "roles": ["ceo", "lecturer", "advisor"],
        "organizations": ["rabinovich_fund"],
        "timeline": {
          "years_active": ["1995", "2000", "2010", "2015", "2019", "2020", "2021"],
          "tenure_start": 1995,
          "tenure_end": null
        },
        "sources": {
          "url_count": 89,
          "sample_urls": [...]
        }
      }
    },
    
    "organizations": {
      "rabinovich_fund": {
        "id": "rabinovich_fund",
        "name": "קרן רבינוביץ",
        "name_en": "Rabinovich Foundation",
        "entity_type": "organization",
        "type": "fund",
        "members": ["giora_eini", "yoav_abramowitz", "..."],
        "beneficiaries": ["moshe_aderi", "..."],
        "years_active": ["1995", "2015", "2016", "2017", "2018", "2019", "2020", "2021"],
        "sources": {
          "url_count": 156
        }
      },
      
      "gesher_fund": {
        "id": "gesher_fund",
        "name": "קרן גשר",
        "name_en": "Gesher Fund",
        "entity_type": "organization",
        "type": "fund",
        "ceo": "zivu_nawe"
      }
    },
    
    "films": {
      "ani_lo_maamin_ani_robot": {
        "id": "ani_lo_maamin_ani_robot",
        "name": "אני לא מאמין אני רובוט",
        "name_en": "I Am Not Sure I'm a Robot",
        "entity_type": "film",
        "year": 2015,
        "producers": ["amir_manor"],
        "funded_by": ["cinema_fund"],
        "notes": "bypassed lecturer review process"
      }
    }
  },
  
  "relationships": [
    {
      "source_id": "moshe_aderi",
      "target_id": "rabinovich_fund",
      "relationship_type": "works_for",
      "role": "producer",
      "confidence": 0.92,
      "evidence": [
        "85 films produced",
        "₪104,333,500 received",
        "49% of fund distributions"
      ],
      "years": ["2015", "2016", "2017", "2018", "2019", "2020", "2021"],
      "source_urls": ["https://...", "https://..."]
    },
    {
      "source_id": "giora_eini",
      "target_id": "rabinovich_fund",
      "relationship_type": "manages",
      "role": "ceo",
      "confidence": 0.98,
      "years": ["1995", "2000", "2010", "2015", "2019", "2020", "2021"],
      "source_urls": ["https://..."]
    },
    {
      "source_id": "yoav_abramowitz",
      "target_id": "ani_lo_maamin_ani_robot",
      "relationship_type": "appeared_in",
      "role": "lecturer",
      "conflict_indicator": true,
      "reason": "evaluator of own projects",
      "confidence": 0.87
    }
  ],
  
  "conflicts": [
    {
      "conflict_id": "conf_001",
      "type": "evaluator_and_beneficiary",
      "person": "yoav_abramowitz",
      "description": "Appears as lecturer in both application and appeal stages for films he has interest in",
      "evidence": [
        "26 applications where Abramowitz was lecturer",
        "6+ where he also appeared in appeal stage",
        "Concurrent role as co-CEO and artistic director"
      ],
      "severity": "high",
      "verified": false
    },
    {
      "conflict_id": "conf_002",
      "type": "multiple_fund_roles",
      "person": "asnat_bukofzer",
      "description": "Council member who worked on funded film while serving",
      "organizations": [
        "film_council",
        "rabinovich_fund",
        "gesher_fund"
      ],
      "concurrent_film": "abba_john",
      "severity": "medium"
    },
    {
      "conflict_id": "conf_003",
      "type": "fund_concentration",
      "beneficiary": "moshe_aderi",
      "organization": "rabinovich_fund",
      "percentage": 49,
      "description": "49% of all Rabinovich fund distributions went to films produced by Aderi",
      "severity": "high",
      "verified": true
    }
  ],
  
  "extraction_stats": {
    "processing_time_seconds": 187,
    "files_processed": 247,
    "files_failed": 3,
    "people_extracted": 312,
    "people_with_conflicts": 47,
    "organizations_extracted": 45,
    "relationships_found": 1204,
    "conflicts_detected": 89
  }
}
```

### 2. `relationships.csv` (For Excel analysis)

```csv
source_id,source_name,relationship_type,target_id,target_name,role,years,confidence,conflict_indicator
moshe_aderi,משה אדרי,works_for,rabinovich_fund,קרן רבינוביץ,producer,"2015,2016,2017,2018,2019,2020,2021",0.92,false
giora_eini,גיורא עיני,manages,rabinovich_fund,קרן רבינוביץ,ceo,"1995,2000,2010,2015,2019,2020,2021",0.98,false
yoav_abramowitz,יואב אברמוביץ,evaluates,ani_lo_maamin_ani_robot,אני לא מאמין אני רובוט,lecturer,2015,0.87,true
zivu_nawe,זיו נווה,manages,gesher_fund,קרן גשר,ceo,"2014,2015,2016,2017,2018,2019,2020,2021",0.95,false
```

### 3. `conflicts.csv` (For conflict analysis)

```csv
conflict_id,type,entity_name,entity_id,description,severity,evidence_count,verified,years_active
conf_001,evaluator_and_beneficiary,יואב אברמוביץ,yoav_abramowitz,Appears as lecturer in 26 applications and appeals,high,4,false,"2015,2019,2020,2021"
conf_002,multiple_fund_roles,אסנת בוקופצר,asnat_bukofzer,Council member who worked on funded film,medium,3,false,"2015,2017"
conf_003,fund_concentration,משה אדרי,moshe_aderi,49% of Rabinovich fund distributions,high,5,true,"2015,2016,2017,2018,2019,2020,2021"
```

### 4. `people.csv` (Contact/reference sheet)

```csv
id,name,name_en,organizations,roles,years_mentioned,source_count,verified
moshe_aderi,משה אדרי,Moshe Aderi,"rabinovich_fund,gesher_fund,united_kinng","producer,distributor,investor","2015,2016,2017,2018,2019,2020,2021",47,false
giora_eini,גיורא עיני,Giora Eini,rabinovich_fund,"ceo,lecturer,advisor","1995,2000,2010,2015,2019,2020,2021",89,true
yoav_abramowitz,יואב אברמוביץ,Yoav Abramowitz,rabinovich_fund,"co-ceo,artistic_director,lecturer","2015,2019,2020,2021",54,false
```

---

## Why This Format Works for You

### For Immediate Analysis
- **Open CSVs in Excel** → filter/sort/pivot quickly
- **Spot patterns** → who appears most, which orgs overlap
- **Manual review** → verify against source documents

### For Platform Integration
- **JSON is API-ready** → feed directly to your visualization tool
- **Structured relationships** → enable graph visualization
- **Metadata included** → confidence scores, source tracking, evidence

### For Future Enhancement
- **Easily deduplicate** → match similar names, merge orgs
- **Add annotations** → manual verification, context, dates
- **Scale up** → add more sources, expand geographic scope

---

## Recommendation Summary

| Stage | Format | Action |
|-------|--------|--------|
| **Extract** | JSON + CSV | Run script on your Mac (offline) |
| **Review** | CSV in Excel | Check for duplicates, noise, patterns |
| **Enrich** | JSON + notes | Add verified info, conflict evidence |
| **Visualize** | JSON → Your platform | Import into relationship mapper |

**Start with CSV** → Quick visual check of what you have
**Keep JSON** → Structured for long-term use & platform integration

---

## Next: Run the Extractor

```bash
cd ~
python3 film_data_extractor.py ~/your_scraped_data ~/output_results

# Check output
ls -lh ~/output_results/
open ~/output_results/extracted_entities.json
open ~/output_results/relationships.csv  # in Excel
```

Ready to process your data?
