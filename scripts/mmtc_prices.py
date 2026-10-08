"""Reads MMTC-PAMP's published distributor price list (a PDF updated several
times a day) and writes data/mmtc-prices.json for the website's coins page.

Only the weights shown on the site are kept: for each weight, the lowest
price (including taxes) among 999.9 gold or silver products. If the PDF
can't be read or any weight is missing, the script exits with an error and
leaves the previous file untouched.
"""
import io
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

import pdfplumber

PDF_URL = "https://cem-cms-data.s3.ap-south-1.amazonaws.com/today_price_list.pdf"
OUT = "data/mmtc-prices.json"
WANT = {"gold": [5, 10, 20, 50, 100], "silver": [10, 50, 100, 1000]}
IST = timezone(timedelta(hours=5, minutes=30))

ROW = re.compile(r"^(\d+)\.\s+(.+?)\s+(\d+(?:\.\d+)?)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})$")
STAMP = re.compile(r"(\d{1,2} [A-Z][a-z]+ \d{4} \d{1,2}:\d{2}:\d{2} [AP]M)")


def money(s):
    return float(s.replace(",", ""))


def read_pdf(data):
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def parse(text):
    m = STAMP.search(text)
    if not m:
        raise ValueError("price list timestamp not found")
    list_time = datetime.strptime(m.group(1), "%d %B %Y %I:%M:%S %p").replace(tzinfo=IST)

    found = {"gold": {}, "silver": {}}
    section = None
    for line in text.splitlines():
        line = line.strip()
        if line == "GOLD":
            section = "gold"
            continue
        if line == "SILVER":
            section = "silver"
            continue
        if "Buyback" in line:
            section = None
        if not section:
            continue
        r = ROW.match(line)
        if not r:
            continue
        name, grams, ex_tax, inc_tax = r.group(2), float(r.group(3)), money(r.group(4)), money(r.group(5))
        if "999.9" not in name or "Set" in name:
            continue
        if section == "gold" and "Gold" not in name or section == "silver" and "Silver" not in name:
            continue
        key = int(grams) if grams.is_integer() else grams
        if key not in WANT[section]:
            continue
        best = found[section].get(key)
        if best is None or inc_tax < best["price"]:
            found[section][key] = {"grams": key, "price": inc_tax, "priceExTax": ex_tax, "product": name}

    out = {}
    for metal, weights in WANT.items():
        missing = [w for w in weights if w not in found[metal]]
        if missing:
            raise ValueError(f"{metal}: weights not found in price list: {missing}")
        rows = [found[metal][w] for w in weights]
        # Sanity check: price per gram should be broadly consistent across weights.
        per_g = [r["price"] / r["grams"] for r in rows]
        if max(per_g) > min(per_g) * 1.5:
            raise ValueError(f"{metal}: implausible prices {per_g}")
        out[metal] = rows
    return list_time, out


def main():
    req = urllib.request.Request(PDF_URL, headers={"User-Agent": "tjh-website-price-sync"})
    data = urllib.request.urlopen(req, timeout=60).read()
    list_time, prices = parse(read_pdf(data))
    doc = {
        "source": "MMTC-PAMP price list",
        "currency": "INR",
        "pricesInclude": "taxes",
        "listTime": list_time.isoformat(),
        "gold": prices["gold"],
        "silver": prices["silver"],
    }
    try:
        with open(OUT) as f:
            old = json.load(f)
    except (OSError, ValueError):
        old = None
    if old == doc:
        print("No change:", doc["listTime"])
        return
    with open(OUT, "w") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print("Updated:", doc["listTime"], [(r["grams"], r["price"]) for r in doc["gold"] + doc["silver"]])


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # leave the last good file in place
        print(f"::error::MMTC-PAMP price sync failed: {e}")
        sys.exit(1)
