#!/usr/bin/env python3
"""
pdf_to_pages.py — Convert PDFs (and DOCX) from sources/*/files/ into .md + .meta.json
pairs in sources/*/pages/ so llm_extract.py can process them normally.

Skips:
  - Scanned/image-only PDFs (< MIN_CHARS extracted)
  - Duplicates (same URL already written)
  - Already-converted files (pages/<stem>.md exists)

Usage:
  python3 pdf_to_pages.py                        # all sources
  python3 pdf_to_pages.py --source gesher        # one source
  python3 pdf_to_pages.py --dry-run              # show what would be written
"""

import argparse
import glob
import json
import os
import sys

MIN_CHARS = 100  # below this = scanned/empty, skip


def extract_pdf_text(path: str) -> str:
    import fitz  # PyMuPDF
    doc = fitz.open(path)
    pages_text = []
    for i, page in enumerate(doc):
        text = page.get_text()
        if text.strip():
            pages_text.append(f"<!-- page {i+1} -->\n{text}")
    doc.close()
    return "\n\n".join(pages_text)


def extract_docx_text(path: str) -> str:
    try:
        import docx
        doc = docx.Document(path)
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception:
        return ""


def process_source(src_dir: str, dry_run: bool) -> dict:
    source_name = os.path.basename(src_dir)
    files_dir = os.path.join(src_dir, "files")
    pages_dir = os.path.join(src_dir, "pages")

    if not os.path.isdir(files_dir):
        return {"source": source_name, "skipped_no_files_dir": True}

    os.makedirs(pages_dir, exist_ok=True)

    stats = {"source": source_name, "written": 0, "skipped_exists": 0,
             "skipped_scanned": 0, "skipped_duplicate_url": 0, "skipped_error": 0}

    seen_urls: set[str] = set()

    candidates = sorted(
        glob.glob(os.path.join(files_dir, "*.pdf")) +
        glob.glob(os.path.join(files_dir, "*.docx")) +
        glob.glob(os.path.join(files_dir, "*.doc"))
    )

    for file_path in candidates:
        base = os.path.basename(file_path)
        # stem = everything before the last .__hash__.ext
        # e.g. gesher__foo__3b34dc85.pdf  → stem = gesher__foo__3b34dc85
        stem = os.path.splitext(base)[0]  # strip .pdf/.docx
        # The stable_id in meta is the stem (without trailing extension)
        meta_path = os.path.join(files_dir, stem + ".meta.json")
        out_md = os.path.join(pages_dir, stem + ".md")
        out_meta = os.path.join(pages_dir, stem + ".meta.json")

        # Already converted
        if os.path.exists(out_md):
            stats["skipped_exists"] += 1
            continue

        # Load meta for URL dedup
        url = ""
        meta = {}
        if os.path.exists(meta_path):
            try:
                meta = json.loads(open(meta_path).read())
                url = meta.get("url", "")
            except Exception:
                pass

        # Deduplicate by URL
        if url and url in seen_urls:
            stats["skipped_duplicate_url"] += 1
            continue
        if url:
            seen_urls.add(url)

        # Extract text
        try:
            ext = os.path.splitext(base)[1].lower()
            if ext == ".pdf":
                text = extract_pdf_text(file_path)
            elif ext in (".docx", ".doc"):
                text = extract_docx_text(file_path)
            else:
                text = ""
        except Exception as e:
            print(f"  ERROR {base}: {e}", file=sys.stderr)
            stats["skipped_error"] += 1
            continue

        if len(text.strip()) < MIN_CHARS:
            stats["skipped_scanned"] += 1
            print(f"  SCANNED  {base}")
            continue

        print(f"  WRITE    {base}  ({len(text)} chars)")
        if not dry_run:
            with open(out_md, "w", encoding="utf-8") as f:
                f.write(text)
            # Write meta sidecar (copy from files/ meta, update path refs)
            out_meta_data = dict(meta)
            out_meta_data["converted_from"] = file_path
            out_meta_data["file_name"] = stem + ".md"
            with open(out_meta, "w", encoding="utf-8") as f:
                json.dump(out_meta_data, f, ensure_ascii=False, indent=2)

        stats["written"] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", help="Process only this source (e.g. gesher)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be written without writing")
    args = parser.parse_args()

    sources_root = "./sources"
    if args.source:
        src_dirs = [os.path.join(sources_root, args.source)]
    else:
        src_dirs = sorted(glob.glob(os.path.join(sources_root, "*")))
        src_dirs = [d for d in src_dirs if os.path.isdir(d)]

    total_written = 0
    for src_dir in src_dirs:
        result = process_source(src_dir, dry_run=args.dry_run)
        if result.get("skipped_no_files_dir"):
            continue
        src = result["source"]
        w = result["written"]
        total_written += w
        print(f"\n{src}: {w} written, "
              f"{result['skipped_exists']} already exist, "
              f"{result['skipped_scanned']} scanned, "
              f"{result['skipped_duplicate_url']} duplicate URLs, "
              f"{result['skipped_error']} errors")

    print(f"\nTotal new .md files: {total_written}")
    if args.dry_run:
        print("(dry run — nothing written)")


if __name__ == "__main__":
    main()
