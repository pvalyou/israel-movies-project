# Quick Start: Run the Extractor on Your Mac

## 1-Minute Setup

### Copy the Scripts to Your Mac

```bash
# Create a working directory
mkdir -p ~/film_extraction
cd ~/film_extraction

# Copy the Python scripts (you'll do this from Claude chat)
# Save these files:
# - film_data_extractor.py
# - advanced_film_extractor.py
# - EXTRACTOR_README.md
# - FORMAT_RECOMMENDATION.md
```

### Run the Extractor

```bash
# Go to your working directory
cd ~/film_extraction

# Run the basic extractor
python3 film_data_extractor.py ~/path/to/your/scraped_data ~/output

# Example:
python3 film_data_extractor.py ~/Downloads/film_scraped ~/film_output
```

**That's it!** The script will:
- Scan all `*_meta.json` files
- Load corresponding `.md` files
- Extract entities and relationships
- Save JSON + CSV outputs to `~/film_output/`

---

## Verify Installation

Check that Python3 is ready:

```bash
python3 --version
# Should output: Python 3.9.x or higher
```

Test on a small directory first:

```bash
# Create test data (copy just 2-3 of your scraped file pairs)
mkdir ~/test_data
cp ~/Downloads/film_scraped/*fb252d5f* ~/test_data/
cp ~/Downloads/film_scraped/*ed3b74b9* ~/test_data/

# Run on test data
python3 film_data_extractor.py ~/test_data ~/test_output

# Check results
ls -lh ~/test_output/
cat ~/test_output/extracted_entities.json | head -50
```

---

## View Results

### Open JSON (view in text editor)

```bash
# Open in default editor
open ~/film_output/extracted_entities.json

# Or use VS Code (if installed)
code ~/film_output/extracted_entities.json
```

### Open CSVs in Excel

```bash
# Open relationships CSV
open -a "Microsoft Excel" ~/film_output/relationships.csv

# Or use Numbers (Mac default)
open -a Numbers ~/film_output/relationships.csv
```

---

## Full Extraction Run

When ready to process all 200+ files:

```bash
# Navigate to working directory
cd ~/film_extraction

# Run on your full dataset
# Note: May take 3-5 minutes for 200+ files (normal)
python3 film_data_extractor.py ~/path/to/all/scraped_data ~/final_output

# Monitor progress (should see file by file output)
```

After completion:

```bash
# See what was extracted
ls -lh ~/final_output/

# Get summary (last 30 lines shows the report)
tail -30 ~/final_output/extracted_entities.json

# Count lines in CSVs
wc -l ~/final_output/*.csv
```

---

## What You'll Get

Inside `~/film_output/` (or wherever you set output):

```
film_output/
├── extracted_entities.json          ← Main structured data (JSON)
├── relationships.csv                ← All connections (open in Excel)
├── people.csv                       ← People reference sheet
└── [processing log in terminal]
```

---

## Troubleshooting

### "Command not found: python3"
Update your Mac's Python:
```bash
brew install python3
python3 --version  # verify
```

### "No meta.json files found"
Check your input directory path:
```bash
# List what's actually there
ls ~/Downloads/film_scraped/ | head -20

# Look for *_meta.json files
ls ~/Downloads/film_scraped/*_meta.json | wc -l
```

### "Permission denied"
Make the script executable:
```bash
chmod +x ~/film_extraction/film_data_extractor.py
```

### Too much output / Want to save logs
```bash
# Run and save output to a log file
python3 film_data_extractor.py ~/input ~/output 2>&1 | tee extraction.log

# Review the log later
cat extraction.log
```

---

## Next Steps After Extraction

### 1. Review in Excel (5 minutes)
```bash
open -a Excel ~/final_output/relationships.csv
```
- Check for obvious duplicates
- Verify person/org names look correct
- Note any patterns you see

### 2. Review JSON Structure
```bash
# Pretty-print first 100 lines
head -100 ~/final_output/extracted_entities.json | python3 -m json.tool
```

### 3. Get Statistics
```bash
# Count entities
python3 << 'EOF'
import json
with open(~/final_output/extracted_entities.json') as f:
    data = json.load(f)
print(f"People: {len(data['entities']['people'])}")
print(f"Organizations: {len(data['entities']['organizations'])}")
print(f"Films: {len(data['entities']['films'])}")
print(f"Relationships: {len(data['relationships'])}")
print(f"Conflicts detected: {len(data['conflicts'])}")
EOF
```

---

## Using the Data

### Option A: Import to Excel
- Open `relationships.csv` in Excel
- Create pivot tables for analysis
- Build your own visualizations

### Option B: Feed to Your Platform
The JSON is ready for your relationship mapping platform:
```javascript
// Your visualization code
fetch('./extracted_entities.json')
  .then(r => r.json())
  .then(data => {
    // data.entities.people
    // data.relationships
    // data.conflicts
  })
```

### Option C: Further Processing
```python
import pandas as pd
import json

# Load data
with open('extracted_entities.json') as f:
    data = json.load(f)

# Create DataFrames
people_df = pd.DataFrame(data['entities']['people']).T
rels_df = pd.DataFrame(data['relationships'])

# Export to Excel with multiple sheets
with pd.ExcelWriter('analysis.xlsx') as w:
    people_df.to_excel(w, 'People')
    rels_df.to_excel(w, 'Relationships')

print(rels_df.groupby('target_name').size().sort_values(ascending=False))
```

---

## Tips for Best Results

### Before Running
✅ Ensure all your scraped files are in one directory  
✅ Check you have matching `*_meta.json` and `*.md` files  
✅ Test on a small subset first (3-5 files)

### During Processing
✅ Let the script run to completion (don't interrupt)  
✅ Leave the terminal open to see progress messages

### After Processing
✅ Open CSVs in Excel and scan for obvious issues  
✅ Spot-check a few relationships against source URLs  
✅ Keep the JSON file for long-term reference  
✅ Document any manual corrections you make

---

## Script Customization (Advanced)

If you want to adjust extraction patterns:

Edit the Hebrew patterns in `film_data_extractor.py`:

```python
self.hebrew_patterns = {
    "roles": [
        "מנהל", "מנהלת", "מנכ\"ל",  # current roles
        "YOUR_CUSTOM_ROLE",           # add your own
    ],
    "fund_indicators": [
        "קרן", "תמיכה", "מימון",      # current
        "YOUR_PATTERN",               # add here
    ]
}
```

Then re-run the script.

---

## Need Help?

1. **Script won't run** → Check Python version: `python3 --version`
2. **No data extracted** → Verify directory structure: `ls ~/your_data/*_meta.json`
3. **Wrong data extracted** → Review the CSV output, may need to tune patterns
4. **Want to add patterns** → Edit the `hebrew_patterns` dict in the script

---

**Ready to start?**

```bash
cd ~/film_extraction
python3 film_data_extractor.py ~/your_data ~/output
```

Good luck! 🚀
