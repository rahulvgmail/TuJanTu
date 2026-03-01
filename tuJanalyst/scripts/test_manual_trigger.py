#!/usr/bin/env python3
"""End-to-end test: submit a manual trigger for BOI and track it through all pipeline layers.

Usage:
    python scripts/test_manual_trigger.py [--base-url http://localhost:8000] [--timeout 300]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone

import requests

# ── Configuration ────────────────────────────────────────────────────────────

COMPANY_SYMBOL = "BOI"
COMPANY_NAME = "Bank of India"

TRIGGER_CONTENT = (
    "Bank of India (BOI) reported Q3 FY25 results with net profit surging 62% YoY "
    "to Rs 2,517 crore, beating consensus estimates by a wide margin. Net interest "
    "income grew 18% YoY to Rs 6,200 crore driven by robust loan book growth of 15%. "
    "Asset quality improved sharply — GNPA ratio fell to 3.8% from 5.4% a year ago, "
    "and NNPA declined to 0.8%. The board approved a 1:1 bonus issue and declared an "
    "interim dividend of Rs 5 per share. Management raised FY25 credit growth guidance "
    "to 16-18% and expects RoA to sustain above 1.1%. Brokerage upgrades expected."
)

# Expected status progression through the pipeline
STATUS_ORDER = [
    "pending",
    "gate_passed",
    "analyzing",
    "analyzed",
    "assessing",
    "assessed",
    "reported",
]

# Terminal statuses where polling should stop
TERMINAL_STATUSES = {"reported", "filtered_out", "error", "analyzed"}

POLL_INTERVAL = 10  # seconds


# ── Helpers ──────────────────────────────────────────────────────────────────

def ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def print_status(label: str, msg: str) -> None:
    print(f"[{ts()}] {label:<12} {msg}")


def api_get(base: str, path: str) -> dict | None:
    url = f"{base}{path}"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        print_status("WARN", f"GET {path} failed: {exc}")
        return None


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="E2E manual trigger test for BOI")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout in seconds (default 300)")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")

    # ── 0. Health check ──────────────────────────────────────────────────
    print_status("HEALTH", f"Checking {base}/health ...")
    try:
        health = requests.get(f"{base}/health", timeout=5)
        health.raise_for_status()
        print_status("HEALTH", f"OK — {health.json()}")
    except requests.RequestException as exc:
        print_status("FATAL", f"Health check failed: {exc}")
        sys.exit(1)

    # ── 1. Submit manual trigger ─────────────────────────────────────────
    print_status("SUBMIT", f"Creating manual trigger for {COMPANY_SYMBOL} ...")
    payload = {
        "content": TRIGGER_CONTENT,
        "company_symbol": COMPANY_SYMBOL,
        "company_name": COMPANY_NAME,
        "triggered_by": "test_manual_trigger.py",
        "notes": "E2E pipeline verification run",
    }
    try:
        resp = requests.post(f"{base}/api/v1/triggers/human", json=payload, timeout=15)
        resp.raise_for_status()
        result = resp.json()
    except requests.RequestException as exc:
        print_status("FATAL", f"Trigger creation failed: {exc}")
        sys.exit(1)

    trigger_id = result["trigger_id"]
    print_status("SUBMIT", f"Trigger accepted — id={trigger_id}")

    # ── 2. Poll for status transitions ───────────────────────────────────
    print()
    print("=" * 70)
    print(f"  Polling trigger {trigger_id}")
    print(f"  Timeout: {args.timeout}s | Poll interval: {POLL_INTERVAL}s")
    print("=" * 70)
    print()

    last_status = None
    transitions: list[tuple[str, str, float]] = []  # (from, to, elapsed)
    start_time = time.monotonic()

    while True:
        elapsed = time.monotonic() - start_time
        if elapsed > args.timeout:
            print()
            print_status("TIMEOUT", f"Pipeline did not complete within {args.timeout}s")
            print_status("TIMEOUT", f"Last status: {last_status}")
            sys.exit(2)

        data = api_get(base, f"/api/v1/triggers/{trigger_id}?include_details=true")
        if data is None:
            print_status("ERROR", "Could not fetch trigger status")
            time.sleep(POLL_INTERVAL)
            continue

        current_status = data["status"]

        if current_status != last_status:
            if last_status is not None:
                transitions.append((last_status, current_status, elapsed))
                milestone = _milestone_label(current_status)
                print_status("TRANSITION", f"{last_status} -> {current_status}  ({elapsed:.1f}s)  {milestone}")
            else:
                print_status("INITIAL", f"Status: {current_status}  ({elapsed:.1f}s)")

            last_status = current_status

            # If analyzed but not significant, pipeline stops here
            if current_status == "analyzed":
                # Give a beat for the orchestrator to advance if it's going to
                time.sleep(POLL_INTERVAL)
                recheck = api_get(base, f"/api/v1/triggers/{trigger_id}?include_details=true")
                if recheck and recheck["status"] == "analyzed":
                    print()
                    print_status("INFO", "Pipeline stopped at ANALYZED (likely is_significant=False)")
                    print_status("INFO", "This is expected if the analysis didn't find significance.")
                    break

            if current_status in {"reported", "filtered_out", "error"}:
                break

        time.sleep(POLL_INTERVAL)

    # ── 3. Summary ───────────────────────────────────────────────────────
    total_elapsed = time.monotonic() - start_time
    print()
    print("=" * 70)
    print("  PIPELINE SUMMARY")
    print("=" * 70)
    print()
    print(f"  Trigger ID : {trigger_id}")
    print(f"  Final status: {last_status}")
    print(f"  Total time : {total_elapsed:.1f}s")
    print()

    if transitions:
        print("  Status transitions:")
        for frm, to, t in transitions:
            print(f"    {frm:<15} -> {to:<15}  at {t:.1f}s")
        print()

    # Print milestones checklist
    _print_milestones(transitions, last_status)

    # ── 4. Fetch final artifacts ─────────────────────────────────────────
    print()
    print("=" * 70)
    print("  FINAL ARTIFACTS")
    print("=" * 70)
    print()

    # Investigation
    inv_data = api_get(base, f"/api/v1/investigations/company/{COMPANY_SYMBOL}")
    if inv_data and inv_data.get("items"):
        inv = inv_data["items"][0]
        print_status("INVEST", f"Investigation found: {inv.get('investigation_id', 'N/A')}")
        print_status("INVEST", f"  Significance: {inv.get('is_significant', 'N/A')}")
        print_status("INVEST", f"  Significance score: {inv.get('significance_score', 'N/A')}")
        if inv.get("key_findings"):
            print_status("INVEST", f"  Key findings: {len(inv['key_findings'])} items")
        if inv.get("synthesis"):
            preview = inv["synthesis"][:120] + "..." if len(inv.get("synthesis", "")) > 120 else inv.get("synthesis", "")
            print_status("INVEST", f"  Synthesis: {preview}")
    else:
        print_status("INVEST", "No investigation found for BOI")

    print()

    # Report
    rpt_data = api_get(base, "/api/v1/reports/?limit=1")
    if rpt_data and rpt_data.get("items"):
        rpt = rpt_data["items"][0]
        print_status("REPORT", f"Report found: {rpt.get('report_id', 'N/A')}")
        print_status("REPORT", f"  Title: {rpt.get('title', 'N/A')}")
        if rpt.get("executive_summary"):
            preview = rpt["executive_summary"][:120] + "..."
            print_status("REPORT", f"  Summary: {preview}")
    else:
        print_status("REPORT", "No reports found")

    print()

    # Position
    pos_data = api_get(base, f"/api/v1/positions/{COMPANY_SYMBOL}")
    if pos_data:
        print_status("POSITION", f"Position found for {COMPANY_SYMBOL}")
        print_status("POSITION", f"  Recommendation: {pos_data.get('recommendation', 'N/A')}")
        print_status("POSITION", f"  Confidence: {pos_data.get('confidence', 'N/A')}")
    else:
        print_status("POSITION", f"No position found for {COMPANY_SYMBOL}")

    print()

    # ── 5. Final verdict ─────────────────────────────────────────────────
    if last_status == "reported":
        print("RESULT: PASS — Pipeline completed through all 5 layers")
        sys.exit(0)
    elif last_status == "analyzed":
        print("RESULT: PARTIAL — Pipeline stopped at Layer 3 (analysis not significant)")
        sys.exit(0)
    elif last_status == "error":
        print("RESULT: FAIL — Pipeline encountered an error")
        # Fetch and print the trigger details for debugging
        final = api_get(base, f"/api/v1/triggers/{trigger_id}?include_details=true")
        if final:
            print(f"\nTrigger details:\n{json.dumps(final, indent=2, default=str)}")
        sys.exit(1)
    else:
        print(f"RESULT: UNKNOWN — Unexpected final status: {last_status}")
        sys.exit(1)


def _milestone_label(status: str) -> str:
    labels = {
        "gate_passed": "[Layer 2] Gate bypass (human_bypass)",
        "analyzing": "[Layer 3] Analysis started",
        "analyzed": "[Layer 3] Analysis completed",
        "assessing": "[Layer 4] Assessment started",
        "assessed": "[Layer 4] Assessment completed",
        "reported": "[Layer 5] Report generated",
        "filtered_out": "[Layer 2] Filtered out",
        "error": "[ERROR]",
    }
    return labels.get(status, "")


def _print_milestones(transitions: list[tuple[str, str, float]], final_status: str | None) -> None:
    milestones = [
        ("pending -> gate_passed", "Trigger picked up, human bypass works"),
        ("gate_passed -> analyzing", "Layer 3 started"),
        ("analyzing -> analyzed", "DSPy analysis pipeline completed"),
        ("analyzed -> assessing", "Layer 4 started (significant)"),
        ("assessing -> assessed", "DecisionModule produced recommendation"),
        ("assessed -> reported", "ReportModule generated + delivery attempted"),
    ]

    transition_set = {f"{frm} -> {to}" for frm, to, _ in transitions}

    print("  Milestone checklist:")
    for key, desc in milestones:
        if key in transition_set:
            print(f"    [x] {key:<30} {desc}")
        else:
            print(f"    [ ] {key:<30} {desc}")
    print()


if __name__ == "__main__":
    main()
