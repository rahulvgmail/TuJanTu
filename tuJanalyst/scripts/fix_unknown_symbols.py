"""One-time script to re-resolve UNKNOWN and numeric company_symbol values
in investigations, reports, assessments, and positions using the now-populated
company_master collection.

Usage:
    python scripts/fix_unknown_symbols.py [--dry-run]
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from motor.motor_asyncio import AsyncIOMotorClient


MONGODB_URI = os.environ.get(
    "TUJ_MONGODB_URI",
    "mongodb://localhost:27017",
)
MONGODB_DATABASE = "tuJanalyst"

# Collections that store company_symbol and need fixing
TARGET_COLLECTIONS = ["investigations", "reports", "assessments", "positions"]


def normalize_name(s: str) -> str:
    """Strip suffixes like 'Limited', 'Ltd', 'Pvt', 'India' and non-alphanum chars."""
    s = re.sub(r"\b(limited|ltd\.?|pvt\.?|private|india)\b", "", s, flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9]", "", s.lower()).strip()


async def build_lookup(db) -> tuple[dict[str, str], dict[str, str], set[str], dict[str, str]]:
    """Build name->symbol, BSE code->symbol, and URL symbol lookup from company_master."""
    norm_to_symbol: dict[str, str] = {}
    exact_to_symbol: dict[str, str] = {}
    bse_to_symbol: dict[str, str] = {}
    all_nse_symbols: set[str] = set()

    async for doc in db.company_master.find():
        sym = doc.get("nse_symbol")
        if not sym:
            continue
        all_nse_symbols.add(sym)
        bse_code = doc.get("bse_scrip_code")
        if bse_code:
            bse_to_symbol[str(bse_code)] = sym
        name = doc.get("company_name", "").strip()
        if name:
            exact_to_symbol[name.upper()] = sym
            norm_to_symbol[normalize_name(name)] = sym
        for alias in doc.get("aliases", []):
            if alias:
                exact_to_symbol[alias.strip().upper()] = sym
                norm_to_symbol[normalize_name(alias)] = sym

    return exact_to_symbol, norm_to_symbol, all_nse_symbols, bse_to_symbol


_BSE_NAME_SCRIP_RE = re.compile(r"^(.+?)\s*\((\d{5,7})\)\s*$")
_NSE_SYMBOL_FROM_URL = re.compile(r"/(?:corporate/(?:xbrl/)?)?([A-Z][A-Z0-9]{1,19})_\d{6,}")


def resolve_from_trigger(trigger: dict, exact_map: dict, norm_map: dict, nse_symbols: set, bse_to_symbol: dict | None = None) -> tuple[str | None, str | None]:
    """Try to resolve symbol and company_name from trigger data."""
    resolved_sym = None
    resolved_name = None

    # Method 1: Extract symbol from NSE source URL (alphabetical)
    url = trigger.get("source_url", "") or ""
    if "nsearchives" in url or "nseindia" in url:
        m = re.search(r"/corporate/(?:xbrl/)?([A-Z][A-Z0-9]+?)_", url)
        if m and m.group(1) in nse_symbols:
            resolved_sym = m.group(1)
        # Also try broader URL pattern
        if not resolved_sym:
            m2 = _NSE_SYMBOL_FROM_URL.search(url)
            if m2 and m2.group(1) in nse_symbols:
                resolved_sym = m2.group(1)

    # Method 2: Extract BSE scrip code from "Company Name (NNNNNN)" in raw_content
    raw = (trigger.get("raw_content") or "").strip()
    first_line = raw.split("\n")[0].strip()

    if not resolved_sym and first_line:
        bse_match = _BSE_NAME_SCRIP_RE.match(first_line)
        if bse_match:
            scrip_code = bse_match.group(2)
            company_name_raw = bse_match.group(1).strip()
            if bse_to_symbol and scrip_code in bse_to_symbol:
                resolved_sym = bse_to_symbol[scrip_code]
                resolved_name = company_name_raw
            else:
                # Try matching the company name part
                norm = normalize_name(company_name_raw)
                if norm and norm in norm_map:
                    resolved_sym = norm_map[norm]
                    resolved_name = company_name_raw

    # Method 3: Match raw_content first line against company master (exact)
    if not resolved_sym and first_line:
        if first_line.upper() in exact_map:
            resolved_sym = exact_map[first_line.upper()]

    # Method 4: Fuzzy normalized name match
    if not resolved_sym and first_line:
        norm = normalize_name(first_line)
        if norm and norm in norm_map:
            resolved_sym = norm_map[norm]

    # Use raw_content first line as company_name if we resolved the symbol
    if resolved_sym and first_line and not resolved_name:
        resolved_name = first_line

    return resolved_sym, resolved_name


async def build_symbol_to_name(db) -> dict[str, str]:
    """Build nse_symbol -> company_name lookup from company_master."""
    symbol_to_name: dict[str, str] = {}
    async for doc in db.company_master.find():
        sym = doc.get("nse_symbol")
        name = (doc.get("company_name") or "").strip()
        if sym and name and name != "Unknown Company":
            symbol_to_name[sym] = name
    return symbol_to_name


async def fix_unknown_company_names(db, symbol_to_name: dict[str, str], dry_run: bool = False):
    """Fix records that have a valid company_symbol but company_name is 'Unknown Company'."""
    print("\n--- Fixing 'Unknown Company' names using company_master ---")
    all_collections = TARGET_COLLECTIONS + ["triggers"]
    total_fixed = 0
    for coll_name in all_collections:
        coll = db[coll_name]
        query = {"company_name": {"$in": ["Unknown Company", None, ""]}}
        count = await coll.count_documents(query)
        fixed = 0
        async for doc in coll.find(query):
            sym = (doc.get("company_symbol") or "").strip().upper()
            # Also check resolved_nse_symbol for triggers
            if not sym or sym == "UNKNOWN":
                sym = (doc.get("resolved_nse_symbol") or "").strip().upper()
            if not sym or sym == "UNKNOWN":
                continue
            name = symbol_to_name.get(sym)
            if not name:
                continue
            if dry_run:
                print(f"  [DRY RUN] {coll_name}: {sym} -> {name}")
            else:
                id_field_map = {
                    "investigations": "investigation_id",
                    "reports": "report_id",
                    "assessments": "assessment_id",
                    "triggers": "trigger_id",
                    "positions": "company_symbol",
                }
                id_field = id_field_map.get(coll_name, "_id")
                if id_field == "company_symbol":
                    await coll.update_one({"_id": doc["_id"]}, {"$set": {"company_name": name}})
                else:
                    await coll.update_one({id_field: doc[id_field]}, {"$set": {"company_name": name}})
            fixed += 1
        total_fixed += fixed
        print(f"  {coll_name}: {fixed}/{count} names fixed")
    print(f"  Total names fixed: {total_fixed}")


async def fix_unknown_symbols(dry_run: bool = False):
    client = AsyncIOMotorClient(MONGODB_URI)
    db = client[MONGODB_DATABASE]

    print("Building company master lookup...")
    exact_map, norm_map, nse_symbols, bse_to_symbol = await build_lookup(db)
    symbol_to_name = await build_symbol_to_name(db)
    print(f"  Exact entries: {len(exact_map)}, Normalized entries: {len(norm_map)}, NSE symbols: {len(nse_symbols)}, BSE codes: {len(bse_to_symbol)}, Symbol->Name: {len(symbol_to_name)}")

    # Build trigger_id -> resolved symbol cache
    print("\nScanning triggers for resolution clues...")
    trigger_cache: dict[str, tuple[str, str]] = {}

    query = {"$or": [{"company_symbol": None}, {"company_symbol": {"$regex": r"^\d+$"}}]}
    async for trigger in db.triggers.find(query):
        tid = trigger.get("trigger_id")
        sym, name = resolve_from_trigger(trigger, exact_map, norm_map, nse_symbols, bse_to_symbol)
        if sym:
            trigger_cache[tid] = (sym, name)

    # Also scan triggers where company_symbol is set but investigation is UNKNOWN
    # (trigger might have useful raw_content even if company_symbol was wrong)
    null_trigger_ids = set()
    for coll_name in TARGET_COLLECTIONS:
        query = {"$or": [
            {"company_symbol": "UNKNOWN"},
            {"company_symbol": {"$regex": r"^\d+$"}},
        ]}
        async for doc in db[coll_name].find(query, {"trigger_id": 1}):
            tid = doc.get("trigger_id")
            if tid and tid not in trigger_cache:
                null_trigger_ids.add(tid)

    for tid in null_trigger_ids:
        trigger = await db.triggers.find_one({"trigger_id": tid})
        if trigger:
            sym, name = resolve_from_trigger(trigger, exact_map, norm_map, nse_symbols, bse_to_symbol)
            if sym:
                trigger_cache[tid] = (sym, name)

    print(f"  Resolvable triggers: {len(trigger_cache)}")

    # Now update target collections
    total_updated = 0
    for coll_name in TARGET_COLLECTIONS:
        coll = db[coll_name]
        query = {"$or": [
            {"company_symbol": "UNKNOWN"},
            {"company_symbol": {"$regex": r"^\d+$"}},
        ]}
        count = await coll.count_documents(query)
        updated = 0

        async for doc in coll.find(query):
            tid = doc.get("trigger_id")
            if tid not in trigger_cache:
                continue

            new_sym, new_name = trigger_cache[tid]
            update_fields = {"company_symbol": new_sym}
            if new_name and (not doc.get("company_name") or doc.get("company_name") == "Unknown Company"):
                update_fields["company_name"] = new_name

            if dry_run:
                old = doc.get("company_symbol")
                print(f"  [DRY RUN] {coll_name}: {old} -> {new_sym} ({new_name})")
                updated += 1
            else:
                # Use the collection's primary ID field
                id_field = {
                    "investigations": "investigation_id",
                    "reports": "report_id",
                    "assessments": "assessment_id",
                    "positions": "company_symbol",
                }.get(coll_name, "_id")

                if id_field == "company_symbol":
                    # For positions, we need to use _id since we're changing the key
                    await coll.update_one({"_id": doc["_id"]}, {"$set": update_fields})
                else:
                    await coll.update_one({id_field: doc[id_field]}, {"$set": update_fields})
                updated += 1

        total_updated += updated
        remaining = count - updated
        print(f"  {coll_name}: {updated}/{count} updated, {remaining} unresolvable")

    # Also update triggers themselves
    trigger_updated = 0
    query = {"$or": [{"company_symbol": None}, {"company_symbol": {"$regex": r"^\d+$"}}]}
    async for trigger in db.triggers.find(query):
        tid = trigger.get("trigger_id")
        if tid in trigger_cache:
            new_sym, new_name = trigger_cache[tid]
            update_fields = {"company_symbol": new_sym, "resolved_nse_symbol": new_sym}
            if new_name:
                update_fields["company_name"] = new_name
            if not dry_run:
                await db.triggers.update_one({"trigger_id": tid}, {"$set": update_fields})
            trigger_updated += 1

    print(f"  triggers: {trigger_updated} updated")
    print(f"\nTotal records updated: {total_updated + trigger_updated}")

    # Phase 2: Fix records with valid symbol but "Unknown Company" name
    await fix_unknown_company_names(db, symbol_to_name, dry_run=dry_run)

    if dry_run:
        print("\n[DRY RUN] No changes were made. Run without --dry-run to apply.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    asyncio.run(fix_unknown_symbols(dry_run=dry_run))
