"""Seed BSE scrip codes and company names into company_master from trigger data.

Extracts 'Company Name (BSE code)' patterns from BSE RSS triggers and:
1. Merges BSE scrip codes into existing company_master records (matched by name)
2. Creates new company_master records for BSE-only companies

Usage:
    python scripts/seed_bse_from_triggers.py [--dry-run]
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from difflib import SequenceMatcher

from motor.motor_asyncio import AsyncIOMotorClient

MONGODB_URI = os.environ.get(
    "TUJ_MONGODB_URI",
    "mongodb://localhost:27017",
)
MONGODB_DATABASE = "tuJanalyst"
BSE_NAME_SCRIP_RE = re.compile(r"^(.+?)\s*\((\d{5,7})\)\s*$")
NON_ALNUM = re.compile(r"[^a-z0-9]+")
FUZZY_THRESHOLD = 0.88


def normalize_name(s: str) -> str:
    s = re.sub(r"\b(limited|ltd\.?|pvt\.?|private|india|-\$)\b", "", s, flags=re.IGNORECASE)
    return NON_ALNUM.sub(" ", s.lower()).strip()


async def seed_bse_from_triggers(dry_run: bool = False):
    client = AsyncIOMotorClient(MONGODB_URI)
    db = client[MONGODB_DATABASE]

    # Step 1: Extract BSE companies from triggers
    print("Scanning BSE triggers for company data...")
    bse_companies: dict[str, str] = {}  # scrip_code -> company_name
    async for trigger in db.triggers.find({"source": "bse_rss"}):
        raw = (trigger.get("raw_content") or "").strip()
        first_line = raw.split("\n")[0].strip()
        m = BSE_NAME_SCRIP_RE.match(first_line)
        if m:
            name = m.group(1).strip()
            code = m.group(2)
            if code not in bse_companies:
                bse_companies[code] = name
    print(f"  Found {len(bse_companies)} unique BSE companies from triggers")

    # Step 2: Build existing company_master lookup
    print("Building company_master lookup...")
    norm_to_doc: dict[str, dict] = {}
    bse_code_exists: set[str] = set()
    async for doc in db.company_master.find():
        bse_code = doc.get("bse_scrip_code")
        if bse_code:
            bse_code_exists.add(str(bse_code))
        name = (doc.get("company_name") or "").strip()
        if name:
            norm_to_doc[normalize_name(name)] = doc
        for alias in doc.get("aliases", []):
            if alias:
                norm_to_doc[normalize_name(alias)] = doc

    print(f"  Existing records: {len(norm_to_doc)} name entries, {len(bse_code_exists)} BSE codes")

    # Step 3: Match and upsert
    merged = 0
    created = 0
    skipped_existing = 0

    for scrip_code, company_name in sorted(bse_companies.items()):
        # Skip if BSE code already in master
        if scrip_code in bse_code_exists:
            skipped_existing += 1
            continue

        norm = normalize_name(company_name)

        # Try exact normalized name match
        matched_doc = norm_to_doc.get(norm)

        # Try fuzzy match if no exact match
        if matched_doc is None:
            best_score = 0.0
            best_doc = None
            for existing_norm, doc in norm_to_doc.items():
                score = SequenceMatcher(None, norm, existing_norm).ratio()
                if score > best_score:
                    best_score = score
                    best_doc = doc
            if best_score >= FUZZY_THRESHOLD and best_doc is not None:
                matched_doc = best_doc

        if matched_doc is not None:
            # Merge BSE code into existing record
            nse_sym = matched_doc.get("nse_symbol", "?")
            if dry_run:
                print(f"  [MERGE] BSE:{scrip_code} ({company_name}) -> {nse_sym} ({matched_doc.get('company_name')})")
            else:
                update: dict = {
                    "bse_scrip_code": scrip_code,
                    "bse_listed": True,
                }
                await db.company_master.update_one(
                    {"canonical_id": matched_doc["canonical_id"]},
                    {"$set": update},
                )
            merged += 1
        else:
            # Create new BSE-only record
            if dry_run:
                print(f"  [NEW] BSE:{scrip_code} - {company_name}")
            else:
                import uuid

                new_doc = {
                    "canonical_id": str(uuid.uuid4()),
                    "nse_symbol": f"BSE:{scrip_code}",
                    "bse_scrip_code": scrip_code,
                    "isin": f"BSE:{scrip_code}",
                    "company_name": company_name,
                    "aliases": [],
                    "description": "",
                    "nse_listed": False,
                    "bse_listed": True,
                    "sector": None,
                    "industry": None,
                    "tags": ["bse_trigger_seed"],
                    "metadata": {"source": "bse_trigger_seed"},
                }
                try:
                    await db.company_master.insert_one(new_doc)
                except Exception as exc:
                    if "duplicate" not in str(exc).lower():
                        print(f"  [ERROR] BSE:{scrip_code}: {exc}")
                    continue
            created += 1

    print(f"\nResults:")
    print(f"  Merged BSE codes into existing records: {merged}")
    print(f"  Created new BSE-only records: {created}")
    print(f"  Skipped (BSE code already exists): {skipped_existing}")

    if not dry_run and (merged > 0 or created > 0):
        # Now re-run the fix for existing Unknown Company records
        print("\nRe-resolving Unknown Company records with new BSE data...")
        bse_to_symbol: dict[str, str] = {}
        bse_to_name: dict[str, str] = {}
        async for doc in db.company_master.find({"bse_scrip_code": {"$ne": None}}):
            code = str(doc.get("bse_scrip_code"))
            sym = doc.get("nse_symbol") or code
            name = doc.get("company_name", "")
            if code:
                bse_to_symbol[code] = sym
                bse_to_name[code] = name

        fixed = 0
        for coll_name in ["investigations", "reports", "assessments", "triggers"]:
            coll = db[coll_name]
            query = {"company_name": {"$in": ["Unknown Company", None, ""]}}
            async for doc in coll.find(query):
                raw = (doc.get("raw_content") or "").strip()
                first_line = raw.split("\n")[0].strip()
                m = BSE_NAME_SCRIP_RE.match(first_line)
                if not m:
                    # Check trigger for this record
                    tid = doc.get("trigger_id")
                    if tid:
                        trigger = await db.triggers.find_one({"trigger_id": tid})
                        if trigger:
                            raw2 = (trigger.get("raw_content") or "").strip()
                            first_line = raw2.split("\n")[0].strip()
                            m = BSE_NAME_SCRIP_RE.match(first_line)
                if not m:
                    continue
                code = m.group(2)
                new_sym = bse_to_symbol.get(code)
                new_name = bse_to_name.get(code)
                if not new_sym:
                    continue

                update_fields = {"company_symbol": new_sym, "company_name": new_name or m.group(1).strip()}
                id_field_map = {
                    "investigations": "investigation_id",
                    "reports": "report_id",
                    "assessments": "assessment_id",
                    "triggers": "trigger_id",
                }
                id_field = id_field_map.get(coll_name, "_id")
                await coll.update_one({id_field: doc[id_field]}, {"$set": update_fields})
                fixed += 1
            print(f"  {coll_name}: {fixed} records updated")
            fixed = 0

    if dry_run:
        print("\n[DRY RUN] No changes were made.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    asyncio.run(seed_bse_from_triggers(dry_run=dry_run))
