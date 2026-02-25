"""Streamlit dashboard for investor/analyst recommendations and report view."""

from __future__ import annotations

import os
from typing import Any

import httpx
import streamlit as st

from src.dashboard.manual_trigger_utils import build_manual_trigger_payload
from src.dashboard.recommendation_utils import (
    expected_impact_score,
    extract_confidence_pct,
    infer_recommendation_signal,
    parse_created_at,
    sort_reports_by_expected_impact,
)

DEFAULT_API_BASE_URL = os.getenv("TUJ_API_BASE_URL", "http://localhost:8000")
DEFAULT_REPORT_LIMIT = 50
DEFAULT_PERFORMANCE_LIMIT = 100
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


def _api_post(base_url: str, path: str, *, json_payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    with httpx.Client(timeout=HTTP_TIMEOUT_SECONDS) as client:
        response = client.post(url, json=json_payload)
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


def _fetch_trigger_status(base_url: str, trigger_id: str) -> dict[str, Any]:
    return _api_get(base_url, f"/api/v1/triggers/{trigger_id}", params={"include_details": "true"})


def _submit_manual_trigger(base_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _api_post(base_url, "/api/v1/triggers/human", json_payload=payload)


def _fetch_performance_summary(base_url: str, limit: int, *, include_live_price: bool) -> dict[str, Any]:
    return _api_get(
        base_url,
        "/api/v1/performance/summary",
        params={
            "limit": limit,
            "include_live_price": str(include_live_price).lower(),
        },
    )


def _fetch_performance_recommendations(base_url: str, limit: int, *, include_live_price: bool) -> list[dict[str, Any]]:
    payload = _api_get(
        base_url,
        "/api/v1/performance/recommendations",
        params={
            "limit": limit,
            "offset": 0,
            "include_live_price": str(include_live_price).lower(),
        },
    )
    items = payload.get("items", [])
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


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


def _format_price(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "-"


def _format_return_pct(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):+.2f}%"
    except (TypeError, ValueError):
        return "-"


def _build_performance_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        company_symbol = str(item.get("company_symbol") or "UNKNOWN")
        company_name = str(item.get("company_name") or "")
        recommendation_date = str(item.get("recommendation_date") or "")[:19]
        recommendation = str(item.get("recommendation") or "none").upper()
        timeframe = str(item.get("timeframe") or "medium_term").replace("_", " ").upper()
        status = str(item.get("status") or "unknown").replace("_", " ").title()
        outcome = str(item.get("outcome") or "unknown").upper()
        rows.append(
            {
                "date": recommendation_date,
                "company": f"{company_symbol} | {company_name}".strip(" |"),
                "action": recommendation,
                "price_at_recommendation": _format_price(item.get("price_at_recommendation")),
                "price_now": _format_price(item.get("price_now")),
                "return_pct": _format_return_pct(item.get("return_pct")),
                "timeframe": timeframe,
                "status": status,
                "outcome": outcome,
                "assessment_id": str(item.get("assessment_id") or ""),
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
    st.caption("T-502/T-503/T-504 MVP: recommendations, report detail, manual triggers, and performance tracking")

    with st.sidebar:
        st.header("Data Source")
        api_base_url = st.text_input("API Base URL", value=DEFAULT_API_BASE_URL, help="FastAPI base URL")
        report_limit = st.slider("Reports to load", min_value=10, max_value=200, value=DEFAULT_REPORT_LIMIT, step=10)
        performance_limit = st.slider(
            "Performance rows",
            min_value=20,
            max_value=500,
            value=DEFAULT_PERFORMANCE_LIMIT,
            step=20,
        )
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

    @st.cache_data(ttl=30, show_spinner=False)
    def cached_performance_summary(base_url: str, limit: int, include_live_price: bool) -> dict[str, Any]:
        return _fetch_performance_summary(base_url, limit, include_live_price=include_live_price)

    @st.cache_data(ttl=30, show_spinner=False)
    def cached_performance_rows(base_url: str, limit: int, include_live_price: bool) -> list[dict[str, Any]]:
        return _fetch_performance_recommendations(base_url, limit, include_live_price=include_live_price)

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
    recommendations_tab, report_tab, manual_tab, performance_tab = st.tabs(
        ["Recommendations", "Report View", "Manual Trigger", "Performance"]
    )

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

    with manual_tab:
        st.subheader("Create Manual Trigger")
        st.caption("Required fields: company symbol and event summary.")
        with st.form("manual_trigger_form", clear_on_submit=False):
            company_symbol = st.text_input("Company Symbol *", placeholder="e.g., SUZLON")
            event_summary = st.text_area(
                "Event Summary *",
                placeholder="Summarize the event that should trigger a fresh analysis.",
                height=120,
            )
            company_name = st.text_input("Company Name (optional)")
            source_url = st.text_input("Source URL (optional)")
            triggered_by = st.text_input("Triggered By (optional)")
            notes = st.text_area("Notes (optional)", height=80)
            submitted = st.form_submit_button("Submit Trigger", type="primary")

        if submitted:
            try:
                payload = build_manual_trigger_payload(
                    company_symbol=company_symbol,
                    event_summary=event_summary,
                    company_name=company_name,
                    source_url=source_url,
                    triggered_by=triggered_by,
                    notes=notes,
                )
                response = _submit_manual_trigger(api_base_url, payload)
                trigger_id = str(response.get("trigger_id") or "")
                if trigger_id:
                    st.session_state["last_trigger_id"] = trigger_id
                st.success(f"Trigger submitted successfully. Trigger ID: {trigger_id}")
            except ValueError as exc:
                st.error(str(exc))
            except httpx.HTTPStatusError as exc:
                st.error(f"Trigger submission failed (HTTP {exc.response.status_code}).")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Trigger submission failed: {exc}")

        last_trigger_id = str(st.session_state.get("last_trigger_id") or "")
        if last_trigger_id:
            st.markdown("### Latest Trigger Status")
            status_cols = st.columns([3, 1])
            status_cols[0].code(last_trigger_id)
            refresh = status_cols[1].button("Refresh Status")
            if refresh:
                try:
                    status_payload = _fetch_trigger_status(api_base_url, last_trigger_id)
                    st.json(status_payload)
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Could not load trigger status: {exc}")

    with performance_tab:
        st.subheader("Historical Performance")
        use_live_price = st.toggle(
            "Use live price snapshot",
            value=False,
            help="When enabled, price_now uses live market data; otherwise latest stored investigation price is used.",
        )
        try:
            summary = cached_performance_summary(api_base_url, performance_limit, use_live_price)
            performance_items = cached_performance_rows(api_base_url, performance_limit, use_live_price)
        except httpx.HTTPStatusError as exc:
            st.error(f"Failed to fetch performance metrics (HTTP {exc.response.status_code}).")
            return
        except Exception as exc:  # noqa: BLE001
            st.error(f"Failed to fetch performance metrics: {exc}")
            return

        metric_cols = st.columns(6)
        metric_cols[0].metric("Total Recos", int(summary.get("total_recommendations") or 0))
        metric_cols[1].metric("Evaluated", int(summary.get("evaluated_recommendations") or 0))
        win_rate = float(summary.get("win_rate") or 0.0) * 100.0
        metric_cols[2].metric("Win Rate", f"{win_rate:.1f}%")
        metric_cols[3].metric("BUY Avg Return", _format_return_pct(summary.get("avg_return_buy")))
        metric_cols[4].metric("SELL Avg Return", _format_return_pct(summary.get("avg_return_sell")))
        metric_cols[5].metric("Wins", int(summary.get("wins") or 0))

        best_call = summary.get("best_call")
        worst_call = summary.get("worst_call")
        call_cols = st.columns(2)
        if isinstance(best_call, dict):
            best_symbol = best_call.get("company_symbol", "-")
            best_reco = str(best_call.get("recommendation", "-")).upper()
            best_return = _format_return_pct(best_call.get("return_pct"))
            call_cols[0].info(
                f"Best Call: {best_symbol} {best_reco} ({best_return})"
            )
        else:
            call_cols[0].info("Best Call: -")
        if isinstance(worst_call, dict):
            worst_symbol = worst_call.get("company_symbol", "-")
            worst_reco = str(worst_call.get("recommendation", "-")).upper()
            worst_return = _format_return_pct(worst_call.get("return_pct"))
            call_cols[1].info(
                f"Worst Call: {worst_symbol} {worst_reco} ({worst_return})"
            )
        else:
            call_cols[1].info("Worst Call: -")

        performance_rows = _build_performance_rows(performance_items)
        if not performance_rows:
            st.info("No recommendation performance data available yet.")
        else:
            st.dataframe(
                performance_rows,
                hide_index=True,
                use_container_width=True,
                column_order=[
                    "date",
                    "company",
                    "action",
                    "price_at_recommendation",
                    "price_now",
                    "return_pct",
                    "timeframe",
                    "status",
                    "outcome",
                    "assessment_id",
                ],
            )


if __name__ == "__main__":
    main()
