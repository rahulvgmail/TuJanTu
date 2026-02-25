# tuJanalyst

AI-powered stock analysis system for NSE/BSE listed companies.

See `docs/DOC_INDEX.md` for project documentation.

## Dashboard (Investor/Analyst MVP)

Run the Streamlit dashboard:

```bash
uv run streamlit run src/dashboard/app.py
```

If FastAPI is not on `http://localhost:8000`, set `TUJ_API_BASE_URL` before launching.

Current MVP views:
- Recommendations list (expected-impact default sort)
- Report detail viewer
- Manual trigger submission form
