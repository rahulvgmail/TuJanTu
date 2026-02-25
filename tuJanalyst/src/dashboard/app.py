"""Streamlit dashboard for investor/analyst recommendations and report view."""

from __future__ import annotations

import os
from typing import Any

import httpx
import streamlit as st

from src.dashboard.recommendation_utils import (
    expected_impact_score,
    extract_confidence_pct,
    infer_recommendation_signal,
    parse_created_at,
    sort_reports_by_expected_impact,
)

DEFAULT_API_BASE_URL = os.getenv("TUJ_API_BASE_URL", "http://localhost:8000")
DEFAULT_REPORT_LIMIT = 50
HTTP_TIMEOUT_SECONDS = 12.0


def _api_get(base_url: str, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    with httpx.Client(timeout=HTTP_TIMEOUT_SECONDS) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected API payload type for {path}: {type(payload)!r}")
    return payload


def _fetch_reports(base_url: str, limit: int) -> list[dict[str, Any]]:
    payload = _api_get(base_url, "/api/v1/reports/", params={"limit": limit})
    items = payload.get("items", [])
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _fetch_report_detail(base_url: str, report_id: str) -> dict[str, Any]:
    return _api_get(base_url, f"/api/v1/reports/{report_id}")


def _build_recommendation_rows(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for report in reports:
        summary = str(report.get("recommendation_summary") or "")
        created_at = parse_created_at(str(report.get("created_at") or ""))
        rows.append(
            {
                "report_id": str(report.get("report_id") or ""),
                "company": str(report.get("company_symbol") or "UNKNOWN"),
                "title": str(report.get("title") or ""),
                "recommendation": infer_recommendation_signal(summary),
                "confidence_pct": extract_confidence_pct(summary),
                "created_at": created_at.isoformat() if created_at.year > 1900 else "",
                "expected_impact_score": round(expected_impact_score(report), 2),
            }
        )
    return rows


def _display_report_detail(base_url: str, report_id: str) -> None:
    if not report_id:
        st.info("Select a report from Recommendations to view details.")
        return

    try:
        detail = _fetch_report_detail(base_url, report_id)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        st.error(f"Could not load report `{report_id}` (HTTP {status}).")
        return
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not load report `{report_id}`: {exc}")
        return

    st.subheader(detail.get("title") or f"Report {report_id}")
    meta_cols = st.columns(4)
    meta_cols[0].metric("Company", str(detail.get("company_symbol") or "UNKNOWN"))
    meta_cols[1].metric("Report ID", str(detail.get("report_id") or ""))
    meta_cols[2].metric("Delivery", str(detail.get("delivery_status") or "unknown").upper())
    meta_cols[3].metric("Created", str(detail.get("created_at") or "")[:19])

    st.markdown("**Recommendation Summary**")
    st.write(detail.get("recommendation_summary") or "_No recommendation summary_")

    st.markdown("**Executive Summary**")
    st.write(detail.get("executive_summary") or "_No executive summary_")

    st.markdown("**Report Body**")
    st.write(detail.get("report_body") or "_No report body_")

    feedback = detail.get("feedback_rating")
    feedback_text = "Awaiting review" if feedback is None else ("Thumbs Up" if int(feedback) > 0 else "Thumbs Down")
    st.caption(f"Feedback: {feedback_text}")


def main() -> None:
    st.set_page_config(
        page_title="tuJanalyst Investor Dashboard",
        page_icon=":bar_chart:",
        layout="wide",
    )
    st.title("Investor / Analyst Dashboard")
    st.caption("T-502 MVP: recommendations list + report detail view")

    with st.sidebar:
        st.header("Data Source")
        api_base_url = st.text_input("API Base URL", value=DEFAULT_API_BASE_URL, help="FastAPI base URL")
        report_limit = st.slider("Reports to load", min_value=10, max_value=200, value=DEFAULT_REPORT_LIMIT, step=10)
        sort_mode = st.selectbox(
            "Default Sort",
            options=["Expected Impact", "Newest"],
            index=0,
            help="Expected Impact ranks BUY/SELL > HOLD > NONE, then confidence, then recency.",
        )
        reload_clicked = st.button("Reload")
        if reload_clicked:
            st.cache_data.clear()

    @st.cache_data(ttl=30, show_spinner=False)
    def cached_reports(base_url: str, limit: int) -> list[dict[str, Any]]:
        return _fetch_reports(base_url, limit)

    try:
        reports = cached_reports(api_base_url, report_limit)
    except httpx.HTTPStatusError as exc:
        st.error(f"Failed to fetch reports (HTTP {exc.response.status_code}) from {api_base_url}.")
        return
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to fetch reports from {api_base_url}: {exc}")
        return

    if sort_mode == "Expected Impact":
        ordered_reports = sort_reports_by_expected_impact(reports)
    else:
        ordered_reports = sorted(
            reports,
            key=lambda item: parse_created_at(str(item.get("created_at") or "")),
            reverse=True,
        )

    rows = _build_recommendation_rows(ordered_reports)
    recommendations_tab, report_tab = st.tabs(["Recommendations", "Report View"])

    with recommendations_tab:
        c1, c2, c3 = st.columns(3)
        c1.metric("Loaded Reports", len(rows))
        c2.metric("BUY/SELL Signals", sum(1 for row in rows if row["recommendation"] in {"BUY", "SELL"}))
        c3.metric("Avg Confidence", round(sum(row["confidence_pct"] for row in rows) / len(rows), 1) if rows else 0.0)

        if not rows:
            st.info("No reports found.")
        else:
            st.dataframe(
                rows,
                hide_index=True,
                use_container_width=True,
                column_order=[
                    "company",
                    "title",
                    "recommendation",
                    "confidence_pct",
                    "created_at",
                    "expected_impact_score",
                    "report_id",
                ],
            )

            selected_default = rows[0]["report_id"]
            selected_report_id = st.selectbox(
                "Open report",
                options=[row["report_id"] for row in rows],
                index=0,
                format_func=lambda value: next(
                    (
                        f'{row["company"]} | {row["recommendation"]} | {row["title"][:80]}'
                        for row in rows
                        if row["report_id"] == value
                    ),
                    value,
                ),
            )
            st.session_state["selected_report_id"] = selected_report_id or selected_default

    with report_tab:
        selected_report_id = str(st.session_state.get("selected_report_id") or "")
        _display_report_detail(api_base_url, selected_report_id)


if __name__ == "__main__":
    main()

