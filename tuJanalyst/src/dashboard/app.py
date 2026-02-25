"""Streamlit dashboard for investor/analyst and admin workflows."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import streamlit as st

from src.dashboard.manual_trigger_utils import build_manual_trigger_payload
from src.dashboard.recommendation_utils import (
    average_confidence_pct,
    expected_impact_score,
    extract_confidence_pct,
    infer_recommendation_signal,
    parse_created_at,
    sort_reports_by_expected_impact,
)

DEFAULT_API_BASE_URL = os.getenv("TUJ_API_BASE_URL", "http://localhost:8000")
DEFAULT_REPORT_LIMIT = 50
DEFAULT_PERFORMANCE_LIMIT = 100
DEFAULT_NOTES_LIMIT = 100
DEFAULT_NOTIFICATION_LIMIT = 50
DEFAULT_ADMIN_WINDOW_DAYS = 7
HTTP_TIMEOUT_SECONDS = 30.0


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


def _fetch_notes(base_url: str, *, company: str, tag: str, limit: int) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"limit": limit}
    if company.strip():
        params["company"] = company.strip().upper()
    if tag.strip():
        params["tag"] = tag.strip().lower()
    payload = _api_get(base_url, "/api/v1/notes", params=params)
    items = payload.get("items", [])
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _create_note(base_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _api_post(base_url, "/api/v1/notes", json_payload=payload)


def _fetch_notifications(base_url: str, *, since: str, limit: int) -> list[dict[str, Any]]:
    payload = _api_get(
        base_url,
        "/api/v1/notifications/feed",
        params={
            "since": since,
            "limit": limit,
        },
    )
    items = payload.get("items", [])
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _fetch_watchlist_overview(base_url: str) -> dict[str, Any]:
    return _api_get(base_url, "/api/v1/watchlist/overview")


def _fetch_agent_policy(base_url: str) -> dict[str, Any]:
    return _api_get(base_url, "/api/v1/watchlist/agent-policy")


def _fetch_trigger_stats(base_url: str, since: str) -> dict[str, Any]:
    return _api_get(base_url, "/api/v1/triggers/stats", params={"since": since})


def _fetch_cost_summary(base_url: str, since: str) -> dict[str, Any]:
    return _api_get(base_url, "/api/v1/costs/summary", params={"since": since})


def _parse_tag_list(value: str) -> list[str]:
    seen: set[str] = set()
    tags: list[str] = []
    for part in value.split(","):
        tag = part.strip().lower()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
    return tags


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


def _format_datetime(value: Any) -> str:
    text = str(value or "")
    return text[:19] if text else ""


def _build_performance_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        company_symbol = str(item.get("company_symbol") or "UNKNOWN")
        company_name = str(item.get("company_name") or "")
        recommendation = str(item.get("recommendation") or "none").upper()
        timeframe = str(item.get("timeframe") or "medium_term").replace("_", " ").upper()
        status = str(item.get("status") or "unknown").replace("_", " ").title()
        outcome = str(item.get("outcome") or "unknown").upper()
        rows.append(
            {
                "date": _format_datetime(item.get("recommendation_date")),
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


def _build_note_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        tags = item.get("tags")
        tags_text = ", ".join(str(tag) for tag in tags) if isinstance(tags, list) else ""
        rows.append(
            {
                "updated_at": _format_datetime(item.get("updated_at")),
                "company_symbol": str(item.get("company_symbol") or "UNKNOWN"),
                "author": str(item.get("created_by") or "analyst"),
                "tags": tags_text,
                "content": str(item.get("content") or ""),
                "report_id": str(item.get("report_id") or ""),
                "investigation_id": str(item.get("investigation_id") or ""),
                "note_id": str(item.get("note_id") or ""),
            }
        )
    return rows


def _build_notification_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        rows.append(
            {
                "time": _format_datetime(item.get("created_at")),
                "type": str(item.get("kind") or ""),
                "company": str(item.get("company_symbol") or "UNKNOWN"),
                "title": str(item.get("title") or ""),
                "message": str(item.get("message") or ""),
                "entity_id": str(item.get("entity_id") or ""),
            }
        )
    return rows


def _build_watchlist_company_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        aliases = item.get("aliases")
        alias_text = ", ".join(str(alias) for alias in aliases) if isinstance(aliases, list) else ""
        recommendation = str(item.get("current_recommendation") or "none").upper()
        rows.append(
            {
                "symbol": str(item.get("symbol") or ""),
                "name": str(item.get("name") or ""),
                "sector": str(item.get("sector") or ""),
                "priority": str(item.get("priority") or ""),
                "aliases": alias_text,
                "status": str(item.get("status") or "").title(),
                "last_trigger": _format_datetime(item.get("last_trigger")),
                "total_investigations": int(item.get("total_investigations") or 0),
                "current_recommendation": recommendation,
            }
        )
    return rows


def _build_sector_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        keywords = item.get("keywords")
        keyword_text = ", ".join(str(keyword) for keyword in keywords) if isinstance(keywords, list) else ""
        rows.append(
            {
                "sector_name": str(item.get("sector_name") or ""),
                "keywords": keyword_text,
                "companies_count": int(item.get("companies_count") or 0),
            }
        )
    return rows


def _build_policy_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        actions = item.get("actions")
        action_text = ", ".join(str(action) for action in actions) if isinstance(actions, list) else ""
        rows.append(
            {
                "agent": str(item.get("agent") or ""),
                "domain": str(item.get("domain") or ""),
                "actions": action_text,
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
        st.error(f"Could not load report `{report_id}` (HTTP {exc.response.status_code}).")
        return
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not load report `{report_id}`: {exc}")
        return

    st.subheader(detail.get("title") or f"Report {report_id}")
    meta_cols = st.columns(4)
    meta_cols[0].metric("Company", str(detail.get("company_symbol") or "UNKNOWN"))
    meta_cols[1].metric("Report ID", str(detail.get("report_id") or ""))
    meta_cols[2].metric("Delivery", str(detail.get("delivery_status") or "unknown").upper())
    meta_cols[3].metric("Created", _format_datetime(detail.get("created_at")))

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
        page_title="tuJanalyst Dashboard",
        page_icon=":bar_chart:",
        layout="wide",
    )

    if "notifications_since" not in st.session_state:
        st.session_state["notifications_since"] = datetime.now(UTC).isoformat()

    with st.sidebar:
        st.header("Workspace")
        view_mode = st.selectbox("UI Surface", options=["Investor/Analyst", "Admin"], index=0)
        api_base_url = st.text_input("API Base URL", value=DEFAULT_API_BASE_URL, help="FastAPI base URL")
        report_limit = st.slider("Reports to load", min_value=10, max_value=200, value=DEFAULT_REPORT_LIMIT, step=10)
        performance_limit = st.slider(
            "Performance rows",
            min_value=20,
            max_value=500,
            value=DEFAULT_PERFORMANCE_LIMIT,
            step=20,
        )
        notes_limit = st.slider("Notes rows", min_value=20, max_value=300, value=DEFAULT_NOTES_LIMIT, step=20)
        notification_limit = st.slider(
            "Notification rows",
            min_value=10,
            max_value=200,
            value=DEFAULT_NOTIFICATION_LIMIT,
            step=10,
        )
        admin_window_days = st.slider(
            "Admin lookback (days)",
            min_value=1,
            max_value=30,
            value=DEFAULT_ADMIN_WINDOW_DAYS,
            step=1,
        )
        sort_mode = st.selectbox(
            "Recommendation Sort",
            options=["Expected Impact", "Newest"],
            index=0,
            help="Expected Impact ranks BUY/SELL > HOLD > NONE, then confidence, then recency.",
        )
        if st.button("Reload"):
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

    @st.cache_data(ttl=15, show_spinner=False)
    def cached_notes(base_url: str, company: str, tag: str, limit: int) -> list[dict[str, Any]]:
        return _fetch_notes(base_url, company=company, tag=tag, limit=limit)

    @st.cache_data(ttl=15, show_spinner=False)
    def cached_notifications(base_url: str, since: str, limit: int) -> list[dict[str, Any]]:
        return _fetch_notifications(base_url, since=since, limit=limit)

    @st.cache_data(ttl=30, show_spinner=False)
    def cached_watchlist_overview(base_url: str) -> dict[str, Any]:
        return _fetch_watchlist_overview(base_url)

    @st.cache_data(ttl=30, show_spinner=False)
    def cached_agent_policy(base_url: str) -> dict[str, Any]:
        return _fetch_agent_policy(base_url)

    @st.cache_data(ttl=30, show_spinner=False)
    def cached_trigger_stats(base_url: str, since: str) -> dict[str, Any]:
        return _fetch_trigger_stats(base_url, since)

    @st.cache_data(ttl=30, show_spinner=False)
    def cached_cost_summary(base_url: str, since: str) -> dict[str, Any]:
        return _fetch_cost_summary(base_url, since)

    if view_mode == "Admin":
        st.title("Admin Dashboard")
        st.caption("T-506 MVP: watchlist management (read-only) and agent access policy placeholder")

        since_iso = (datetime.now(UTC) - timedelta(days=admin_window_days)).isoformat()
        try:
            watchlist_overview = cached_watchlist_overview(api_base_url)
            agent_policy = cached_agent_policy(api_base_url)
            trigger_stats = cached_trigger_stats(api_base_url, since_iso)
            cost_summary = cached_cost_summary(api_base_url, since_iso)
        except httpx.HTTPStatusError as exc:
            st.error(f"Failed to fetch admin data (HTTP {exc.response.status_code}).")
            return
        except Exception as exc:  # noqa: BLE001
            st.error(f"Failed to fetch admin data: {exc}")
            return

        company_rows = _build_watchlist_company_rows(watchlist_overview.get("companies", []))
        sector_rows = _build_sector_rows(watchlist_overview.get("sectors", []))
        active_recommendations = sum(
            1 for row in company_rows if str(row.get("current_recommendation") or "NONE") != "NONE"
        )

        metric_cols = st.columns(5)
        metric_cols[0].metric("Tracked Companies", len(company_rows))
        metric_cols[1].metric("Tracked Sectors", len(sector_rows))
        metric_cols[2].metric("Active Recos", active_recommendations)
        metric_cols[3].metric("Triggers (Window)", int(trigger_stats.get("total") or 0))
        metric_cols[4].metric(
            "Cost / Report",
            f"${float(cost_summary.get('cost_per_completed_report_usd') or 0.0):.4f}",
        )

        overview_tab, policy_tab = st.tabs(["Watchlist", "Agent Policy Placeholder"])

        with overview_tab:
            st.caption(
                f"Watchlist source: {watchlist_overview.get('watchlist_path', '-')}, "
                f"loaded at {str(watchlist_overview.get('watchlist_loaded_at') or '-')[:19]}"
            )

            counts_col_1, counts_col_2 = st.columns(2)
            counts_col_1.markdown("**Trigger Status Split**")
            counts_col_1.json(trigger_stats.get("counts_by_status") or {})
            counts_col_2.markdown("**Trigger Source Split**")
            counts_col_2.json(trigger_stats.get("counts_by_source") or {})

            if not company_rows:
                st.info("No watchlist company records found.")
            else:
                st.markdown("**Tracked Companies**")
                st.dataframe(
                    company_rows,
                    hide_index=True,
                    use_container_width=True,
                    column_order=[
                        "symbol",
                        "name",
                        "sector",
                        "priority",
                        "aliases",
                        "status",
                        "last_trigger",
                        "total_investigations",
                        "current_recommendation",
                    ],
                )

            if not sector_rows:
                st.info("No watchlist sectors found.")
            else:
                st.markdown("**Tracked Sectors**")
                st.dataframe(
                    sector_rows,
                    hide_index=True,
                    use_container_width=True,
                    column_order=["sector_name", "companies_count", "keywords"],
                )

        with policy_tab:
            st.info("MVP placeholder: policy editing remains config-file driven and read-only in UI.")
            policy_meta_cols = st.columns(3)
            policy_meta_cols[0].metric("Policy Exists", "Yes" if agent_policy.get("exists") else "No")
            policy_meta_cols[1].metric("Editable In UI", "Yes" if agent_policy.get("editable_in_ui") else "No")
            policy_meta_cols[2].metric("Permissions", len(agent_policy.get("permissions") or []))

            st.code(str(agent_policy.get("policy_path") or "-"), language="text")
            st.caption(f"Last loaded: {_format_datetime(agent_policy.get('last_loaded_at')) or '-'}")
            st.caption(
                f"Domains: {', '.join(agent_policy.get('domains') or [])} | "
                f"Actions: {', '.join(agent_policy.get('actions') or [])}"
            )

            policy_rows = _build_policy_rows(agent_policy.get("permissions") or [])
            if not policy_rows:
                st.info("No explicit agent permission rows configured.")
            else:
                st.dataframe(
                    policy_rows,
                    hide_index=True,
                    use_container_width=True,
                    column_order=["agent", "domain", "actions"],
                )

        return

    st.title("Investor / Analyst Dashboard")
    st.caption(
        "T-502/T-503/T-504/T-505 MVP: recommendations, report detail, manual triggers, "
        "performance tracking, shared notes, and in-app notifications"
    )

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

    recommendation_rows = _build_recommendation_rows(ordered_reports)
    tabs = st.tabs(
        [
            "Recommendations",
            "Report View",
            "Manual Trigger",
            "Performance",
            "Notes",
            "Notifications",
        ]
    )
    recommendations_tab, report_tab, manual_tab, performance_tab, notes_tab, notifications_tab = tabs

    with recommendations_tab:
        c1, c2, c3 = st.columns(3)
        c1.metric("Loaded Reports", len(recommendation_rows))
        c2.metric("BUY/SELL Signals", sum(1 for row in recommendation_rows if row["recommendation"] in {"BUY", "SELL"}))
        c3.metric("Avg Confidence", average_confidence_pct(recommendation_rows))

        if not recommendation_rows:
            st.info("No reports found.")
        else:
            st.dataframe(
                recommendation_rows,
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

            selected_default = recommendation_rows[0]["report_id"]
            selected_report_id = st.selectbox(
                "Open report",
                options=[row["report_id"] for row in recommendation_rows],
                index=0,
                format_func=lambda value: next(
                    (
                        f'{row["company"]} | {row["recommendation"]} | {row["title"][:80]}'
                        for row in recommendation_rows
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
            if status_cols[1].button("Refresh Status"):
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
            call_cols[0].info(f"Best Call: {best_symbol} {best_reco} ({best_return})")
        else:
            call_cols[0].info("Best Call: -")
        if isinstance(worst_call, dict):
            worst_symbol = worst_call.get("company_symbol", "-")
            worst_reco = str(worst_call.get("recommendation", "-")).upper()
            worst_return = _format_return_pct(worst_call.get("return_pct"))
            call_cols[1].info(f"Worst Call: {worst_symbol} {worst_reco} ({worst_return})")
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

    with notes_tab:
        st.subheader("Shared Notes")
        st.caption("Notes are organization-shared and indexed with company context.")

        filter_cols = st.columns(3)
        notes_company_filter = filter_cols[0].text_input("Filter Company", placeholder="e.g., SUZLON")
        notes_tag_filter = filter_cols[1].text_input("Filter Tag", placeholder="e.g., thesis")
        if filter_cols[2].button("Refresh Notes"):
            st.cache_data.clear()

        with st.form("shared_note_form", clear_on_submit=False):
            note_company_symbol = st.text_input("Company Symbol *", placeholder="e.g., SUZLON")
            note_content = st.text_area("Note *", height=120, placeholder="Add context for future analyses...")
            note_tags_csv = st.text_input("Tags (comma-separated)", placeholder="risk, thesis, management")
            note_company_name = st.text_input("Company Name (optional)")
            note_report_id = st.text_input("Related Report ID (optional)")
            note_investigation_id = st.text_input("Related Investigation ID (optional)")
            note_author = st.text_input("Author (optional)", value="analyst")
            note_submitted = st.form_submit_button("Add Shared Note", type="primary")

        if note_submitted:
            try:
                payload = {
                    "company_symbol": note_company_symbol,
                    "company_name": note_company_name,
                    "content": note_content,
                    "tags": _parse_tag_list(note_tags_csv),
                    "report_id": note_report_id,
                    "investigation_id": note_investigation_id,
                    "created_by": note_author,
                }
                created = _create_note(api_base_url, payload)
                st.success(f"Note saved. Note ID: {created.get('note_id', '')}")
                st.cache_data.clear()
            except httpx.HTTPStatusError as exc:
                st.error(f"Note save failed (HTTP {exc.response.status_code}).")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Note save failed: {exc}")

        try:
            notes_items = cached_notes(api_base_url, notes_company_filter, notes_tag_filter, notes_limit)
        except httpx.HTTPStatusError as exc:
            st.error(f"Failed to fetch notes (HTTP {exc.response.status_code}).")
            return
        except Exception as exc:  # noqa: BLE001
            st.error(f"Failed to fetch notes: {exc}")
            return

        note_rows = _build_note_rows(notes_items)
        if not note_rows:
            st.info("No notes found for current filters.")
        else:
            st.dataframe(
                note_rows,
                hide_index=True,
                use_container_width=True,
                column_order=[
                    "updated_at",
                    "company_symbol",
                    "author",
                    "tags",
                    "content",
                    "report_id",
                    "investigation_id",
                    "note_id",
                ],
            )

    with notifications_tab:
        st.subheader("Notifications")
        st.caption("In-app feed since your current dashboard session started.")

        notifications_since = str(st.session_state.get("notifications_since") or datetime.now(UTC).isoformat())
        header_cols = st.columns(3)
        header_cols[0].code(f"Since: {notifications_since[:19]}")
        if header_cols[1].button("Mark All Read"):
            st.session_state["notifications_since"] = datetime.now(UTC).isoformat()
            st.cache_data.clear()
            notifications_since = str(st.session_state["notifications_since"])

        try:
            notification_items = cached_notifications(api_base_url, notifications_since, notification_limit)
        except httpx.HTTPStatusError as exc:
            st.error(f"Failed to fetch notifications (HTTP {exc.response.status_code}).")
            return
        except Exception as exc:  # noqa: BLE001
            st.error(f"Failed to fetch notifications: {exc}")
            return

        header_cols[2].metric("Unread", len(notification_items))
        notification_rows = _build_notification_rows(notification_items)
        if not notification_rows:
            st.info("No new notifications in this session.")
        else:
            st.dataframe(
                notification_rows,
                hide_index=True,
                use_container_width=True,
                column_order=["time", "type", "company", "title", "message", "entity_id"],
            )


if __name__ == "__main__":
    main()
