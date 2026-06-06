import re
import json
from datetime import datetime

# Read the lecturers page content
with open('/Users/moran/projects/israeli-movies-ind/film_fund_lecturers.md', 'r', encoding='utf-8') as f:
    content = f.read()

# Parse lecturers from the content
lecturers = []

# Extract sections with lecturers
# Pattern for lecturer sections
pattern = r'\*\*(.*?)\*\*\n\n(.*?)(?=\n\n\*\*|\Z)'
matches = re.findall(pattern, content, re.DOTALL)

for title, section in matches:
    # Clean up the title
    title = title.strip()
    
    # Extract lecturer names from the section
    # Names are separated by commas
    names = [name.strip() for name in section.split(',') if name.strip()]
    
    # Determine role and year from title
    if 'לקטורים השקעה בהפקה' in title:
        role = 'לקטור/ יועץ אמנותי'
        fund_name = 'קרן הקולנוע הישראלי'
        # Extract date
        date_match = re.search(r'מועד (\w+ \d{4})', title)
        year = date_match.group(1) if date_match else 'unknown'
    elif 'לקטורים השקעה בפיתוח' in title:
        role = 'לקטור/ יועץ אמנותי'
        fund_name = 'קרן הקולנוע הישראלי'
        date_match = re.search(r'מועד (\w+ \d{4})', title)
        year = date_match.group(1) if date_match else 'unknown'
    elif 'לקטורים השקעה בהשלמת הפקה' in title:
        role = 'לקטור/ יועץ אמנותי'
        fund_name = 'קרן הקולנוע הישראלי'
        date_match = re.search(r'מועד (\w+ \d{4})', title)
        year = date_match.group(1) if date_match else 'unknown'
    elif 'לקטורים מסלול' in title:
        role = 'לקטור/ יועץ אמנותי'
        fund_name = 'קרן הקולנוע הישראלי'
        # Extract date from Hebrew month names
        date_match = re.search(r'מועד (\w+ \d{4})', title)
        if date_match:
            year = date_match.group(1)
        else:
            # Try to find date in the section itself
            date_match = re.search(r'מועד (\w+ \d{4})', section)
            year = date_match.group(1) if date_match else 'unknown'
    else:
        role = 'לקטור/ יועץ אמנותי'
        fund_name = 'קרן הקולנוע הישראלי'
        year = 'unknown'
    
    # Add each lecturer
    for name in names:
        # Skip empty names
        if not name or name in ['', 'ו', 'או']:
            continue
            
        lecturer = {
            "hebrew_name": name,
            "english_name": "",  # We'll need to fill this in later
            "year": year,
            "fund_name": fund_name,
            "role": role,
            "source": "https://www.filmfund.org.il/ContentPage?id=49",
            "details": f"הופיע במקטע: {title}"
        }
        lecturers.append(lecturer)

# Save to JSON
output = {"people": lecturers}

with open('/Users/moran/projects/israeli-movies-ind/film_fund_lecturers_parsed.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"Extracted {len(lecturers)} lecturers from film fund page")