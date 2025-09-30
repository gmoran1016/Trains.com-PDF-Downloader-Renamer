
import os
import re
import shutil
from calendar import month_abbr, month_name

# Paths
SOURCE_DIR = r"C:\Users\Griffin\Downloads\PDFs"
DEST_DIR = r"C:\Users\Griffin\Downloads\OrganizedPDFs"

# Month lookup maps
month_map = {abbr.upper(): name for abbr, name in zip(month_abbr, month_name) if abbr}
month_num_map = {abbr.upper(): f"{i:02d}" for i, abbr in enumerate(month_abbr) if abbr}
all_months = list(month_name)[1:]  # ['January', ..., 'December']

def determine_prefix(filename):
    """Determine prefix based on filename containing 'train' or 'trn'."""
    if re.search(r"train|trn", filename, re.IGNORECASE):
        return "TRN"
    elif re.search(r"CTR", filename, re.IGNORECASE):
        return "CTR"
    return "MRR"


def parse_filename(filepath):
    name, ext = os.path.splitext(os.path.basename(filepath))
    if ext.lower() != ".pdf":
        return None

    prefix = determine_prefix(name)

    # 1️⃣ Numeric format _YYYY_MM or -YYYY-MM
    match_numeric = re.search(r"(?:^|_)(\d{4})[_-](\d{1,2})(?:\D|$)", name)
    if match_numeric:
        year, month_num = match_numeric.groups()
        year = int(year)
        month_num = int(month_num)
        if 1 <= month_num <= 12 and 1900 <= year <= 2099:
            month_full = month_name[month_num]
            return f"{prefix}-{month_num:02d}-{month_full}-{year}", str(year), month_full

    # 2️⃣ YYYYMM anywhere
    match_yyyymm = re.search(r"(\d{4})(\d{2})", name)
    if match_yyyymm:
        year, month_num = match_yyyymm.groups()
        year = int(year)
        month_num = int(month_num)
        if 1 <= month_num <= 12 and 1900 <= year <= 2099:
            month_full = month_name[month_num]
            return f"{prefix}-{month_num:02d}-{month_full}-{year}", str(year), month_full

    # 3️⃣ DDMMMYYYY or DDMMMYY
    match_ddmmmyyyy = re.search(r"(\d{1,2})?([A-Za-z]{3})[-_]?(\d{2,4})", name)
    if match_ddmmmyyyy:
        _, month_abbr, year = match_ddmmmyyyy.groups()
        month_abbr = month_abbr[:3].upper()
        if month_abbr not in month_map:
            return None
        month_full = month_map[month_abbr]
        month_num = month_num_map[month_abbr]

        year = int(year)
        if year < 100:
            year += 2000
        if not (1900 <= year <= 2099):
            return None
        return f"{prefix}-{month_num}-{month_full}-{year}", str(year), month_full

    # 4️⃣ MMMYY or MMMYYYY anywhere
    match_mmmyy = re.search(r"([A-Za-z]{3})(\d{2,4})", name)
    if match_mmmyy:
        month_abbr, year = match_mmmyy.groups()
        month_abbr = month_abbr[:3].upper()
        if month_abbr not in month_map:
            return None
        month_full = month_map[month_abbr]
        month_num = month_num_map[month_abbr]

        year = int(year)
        if year < 100:
            year += 2000
        if not (1900 <= year <= 2099):
            return None
        return f"{prefix}-{month_num}-{month_full}-{year}", str(year), month_full

    return None

def get_unique_path(base_path):
    if not os.path.exists(base_path):
        return base_path
    root, ext = os.path.splitext(base_path)
    counter = 1
    new_path = f"{root}-{counter}{ext}"
    while os.path.exists(new_path):
        counter += 1
        new_path = f"{root}-{counter}{ext}"
    return new_path

def scan_existing_organized():
    """Scan OrganizedPDFs for existing issues."""
    issues_by_year = {}
    for root, _, files in os.walk(DEST_DIR):
        for filename in files:
            if not filename.lower().endswith(".pdf"):
                continue
            parts = filename.split("-")
            if len(parts) >= 4 and parts[0] in {"MRR", "TRN"}:
                month = parts[2]
                year_str = parts[3].replace(".pdf", "")
                if not year_str.isdigit():
                    continue
                year = int(year_str)
                if 1900 <= year <= 2099:
                    issues_by_year.setdefault(str(year), set()).add(month)
    return issues_by_year

def organize_pdfs():
    issues_by_year = scan_existing_organized()
    report_lines = ["Missing issues:"]

    for root, _, files in os.walk(SOURCE_DIR):
        for filename in files:
            filepath = os.path.join(root, filename)
            parsed = parse_filename(filepath)
            if not parsed:
                print(f"Skipping {repr(filename)} (unexpected format)")
                continue

            new_name, year, month = parsed
            year_folder = os.path.join(DEST_DIR, year)
            os.makedirs(year_folder, exist_ok=True)

            new_path = os.path.join(year_folder, new_name + ".pdf")
            unique_path = get_unique_path(new_path)

            shutil.move(filepath, unique_path)
            print(f"Moved: {repr(filepath)} -> {repr(unique_path)}")
            issues_by_year.setdefault(year, set()).add(month)

    # Missing issues report
    for year in sorted(issues_by_year.keys()):
        months_found = issues_by_year[year]
        missing = [m for m in all_months if m not in months_found]
        if missing:
            line = f"{year}: {missing}"
        else:
            line = f"{year}: None (all issues present)"
        print(line)
        report_lines.append(line)

    # Write report to text file
    os.makedirs(DEST_DIR, exist_ok=True)
    report_path = os.path.join(DEST_DIR, "missing_issues_report.txt")
    with open(report_path, "w") as f:
        for line in report_lines:
            f.write(line + "\n")
    print(f"\nMissing issues report written to {report_path}")

if __name__ == "__main__":
    organize_pdfs()

