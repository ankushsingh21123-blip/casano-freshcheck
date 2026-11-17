# FreshCheck — Stale-Answer Detector for AI Applications

Built by **Casano** (solo: Ankush Singh) for the HackCulture Global AI
Hackathon, Tavily track.

AI applications store answers. Facts change. FreshCheck takes a stored
question + answer, runs **one live Tavily search** for current evidence,
and returns a transparent, heuristic freshness verdict with every signal
shown — so a human can judge for themselves instead of trusting a black
box.

**This is a heuristic detector, not ground truth.** Verdicts are based
on the signals listed below. Nothing here claims an answer is true or
false — only whether current evidence suggests it may be out of date.

## How it works

1. **Query derivation (deterministic, no LLM).** Keywords are extracted
   from the question + answer: lowercased, stopwords removed, question
   terms weighted double, ties broken alphabetically, capped at 8 terms
   / 200 characters. The same input always produces the same query, and
   the query used is stored with every check.
2. **One Tavily search per check.** `POST https://api.tavily.com/search`
   with basic depth, `max_results: 5`, `include_answer: false` — 1 credit
   per check on the free Researcher tier. Topic is `general` or `news`
   (chosen in the UI). 20-second timeout.
3. **Evidence dating.** Each result's date is `published_date` when
   Tavily provides it and it parses; otherwise a date extracted from the
   snippet; otherwise the UI shows **"date not provided"**. (The Tavily
   SDK reference does not guarantee `published_date` on results, so it
   is treated as optional throughout.)
4. **Verdict engine.** See "How the verdict works" below.
5. **History.** Every check — including offline checks and failed live
   searches — is stored in a local SQLite database and listed in the UI.

## How the verdict works

Verdicts: `FRESH`, `POSSIBLY_STALE`, `STALE`, `UNKNOWN`. Every check
response includes a `reasons` list and a `signals` object with all of:

- **(a) Evidence dates vs answer date.** The newest evidence date is
  compared with the answer date when both are known (gap in days).
- **(b) Date/number claims.** Years, full dates, and figures (grouped
  numbers, decimals, percents) extracted from the stored answer are
  checked against the evidence snippets: found vs not found. Years in
  the evidence that are newer than any year in the answer are flagged.
- **(c) Keyword overlap.** The fraction of the answer's content terms
  that appear in the evidence text.

Decision rules, applied in order:

1. No evidence → `UNKNOWN`.
2. Keyword overlap below 0.15 → `UNKNOWN` (evidence may not be about
   the same topic, so date signals would be meaningless).
3. Newest evidence date more than 180 days newer than the answer date
   **and** evidence mentions a newer year than any year in the answer
   → `STALE`.
4. Newest evidence date more than 90 days newer than the answer date
   → `POSSIBLY_STALE`.
5. Keyword overlap below 0.30 → `POSSIBLY_STALE`.
6. At least one extracted claim not found in evidence **and** overlap
   below 0.50 → `POSSIBLY_STALE` (partial corroboration only).
7. Otherwise → `FRESH`.

## Live vs offline

| Mode | When | Behaviour |
| ---- | ---- | --------- |
| `live` | `TAVILY_API_KEY` is set | One Tavily search per check; verdict from live evidence. |
| `offline` | No key set | **No live search is performed.** Verdict is always `UNKNOWN`. Date/number claims are still extracted from the answer itself and labelled **answer-only analysis**. Offline results are never presented as live. |

`GET /health` reports the current mode. The mode is never derived from
anything except whether a key is configured, and the key itself is never
returned, logged, or exposed by any endpoint.

**Tavily failures are honest failures.** A 401, 429, timeout, network
error, or malformed response produces a stored check with verdict
`UNKNOWN` and an `error` object (`kind` + `detail`) — never a faked
verdict.

> **Verification note:** the Tavily integration was tested against
> mocked HTTP responses only (see `backend/tests/test_tavily.py`). It
> was **not** verified against the live Tavily API — no API key was
> available during development. The request shape follows the official
> Tavily docs (docs.tavily.com) as read on 17 Nov 2026: `POST
> https://api.tavily.com/search`, `Authorization: Bearer <key>`, body
> fields `query`, `search_depth`, `topic`, `time_range`, `max_results`,
> `include_answer`, `include_raw_content`, `include_domains` /
> `exclude_domains`; response `{results: [{title, url, content, score,
> raw_content?}], query, response_time, request_id, answer?}`.

## Run it

Prerequisites: Python 3.12, Node.js 18+ (tested with Node 24), npm.
No paid services. No accounts needed except a free Tavily key for live
mode (obtained by you from tavily.com — this repo creates no accounts).

### Backend (FastAPI)

```bash
cd backend
python3 -m venv .venv
# NOTE: on VMs where /tmp is a small tmpfs, set TMPDIR so pip does not
# run out of space:
TMPDIR=~/workspace/.pip-tmp .venv/bin/pip install --no-cache-dir \
  -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

The API listens at `http://localhost:8000`. Storage is SQLite at
`backend/data/freshcheck.db` (created automatically, gitignored).

### Frontend (Next.js App Router + TypeScript, plain CSS)

```bash
cd web
npm install
npm run dev
```

The UI runs at `http://localhost:3000` and talks to the backend at
`http://localhost:8000` by default. Override the API base URL with
`NEXT_PUBLIC_API_URL`:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Production build (verified passing):

```bash
npm run build
npm run start
```

### Configure live mode

```bash
cp .env.example backend/.env
# Edit backend/.env and set TAVILY_API_KEY to your own key.
```

The free Researcher plan is 1,000 credits/month with no card required
(per Tavily docs pricing); basic search costs 1 credit, advanced costs
2. FreshCheck uses basic depth only, so each check costs 1 credit.
Restart the backend after setting the key. `GET /health` should then
report `"mode": "live"`. Never commit `backend/.env`.

## API reference

| Endpoint | Description |
| -------- | ----------- |
| `GET /health` | `{status, mode, service}` — `mode` is `live` or `offline`. |
| `POST /checks` | Create a check. Body: `{question (≤500 chars), answer (≤5000 chars), answer_date? ("YYYY-MM-DD"), topic? ("general" \| "news")}`. Returns `201` with the full check record. |
| `GET /checks` | List checks, newest first. `?limit=` (1–100, default 50). |
| `GET /checks/{id}` | One check by id, or `404`. |

Every check record contains: `id, question, answer, answer_date, topic,
mode, verdict, query, reasons[], signals{}, evidence[], error, message,
created_at`. Evidence items contain: `title, url, date, date_display,
date_source, snippet, score`.

## Tests

41 pytest tests, all passing (17 Nov 2026):

```bash
cd backend
.venv/bin/python -m pytest -q
# 41 passed
```

Coverage: verdict engine (fresh / possibly-stale / stale / unknown
with fixed inputs, date + number claim extraction), query derivation
(determinism, caps, weighting, fallback), Tavily client with mocked
httpx (success incl. missing `published_date`, 401, 429, timeout,
network error, invalid-URL filtering, malformed response), offline
mode, API endpoints via TestClient (happy paths, validation errors,
404), and history persistence across clients.

## Project structure

```
casano-freshcheck/
├── README.md
├── .env.example            # placeholder only; copy to backend/.env
├── .gitignore
├── backend/
│   ├── requirements.txt        # fastapi, uvicorn, pydantic v2, httpx
│   ├── requirements-dev.txt    # pytest
│   ├── app/
│   │   ├── main.py         # FastAPI app + endpoints
│   │   ├── config.py       # env config, fixed Tavily URL, CORS
│   │   ├── db.py           # stdlib sqlite3 storage, no ORM
│   │   ├── models.py       # pydantic bounds (500 / 5000 chars)
│   │   ├── query.py        # deterministic keyword extraction
│   │   ├── tavily.py       # Tavily client, evidence normalisation
│   │   └── verdict.py      # heuristic verdict engine + date extraction
│   ├── tests/              # 41 pytest tests (mocked HTTP only)
│   └── data/               # freshcheck.db lives here (gitignored)
└── web/
    ├── package.json
    ├── app/                # layout, page, globals.css (plain CSS)
    └── lib/api.ts          # typed API client
```

## Security notes

- Input bounds enforced by pydantic: question ≤ 500 chars, answer
  ≤ 5000 chars; blank values rejected; `topic` restricted to
  `general`/`news`; `answer_date` must be a valid `YYYY-MM-DD` date.
- All external HTTP has a 20-second timeout. Only the fixed Tavily URL
  is ever contacted — no user-supplied URLs are fetched.
- Evidence URLs are validated as `http`/`https` with a host before
  storage; anything else is dropped.
- CORS is restricted to `localhost:3000` / `127.0.0.1:3000` by default
  (override via `CORS_ORIGINS`).
- `.env` files, `*.db` files, `.venv/`, and `node_modules/` are
  gitignored. `.env.example` files contain placeholders only.

## Limitations

- Heuristic only: keyword overlap and snippet date extraction are
  approximations. Snippet dates reflect what a page mentions, not
  necessarily when it was published.
- Evidence is limited to 5 basic-depth results per check by design
  (credit-conscious); deeper or broader searches may surface more.
- Dates are compared at day granularity; month/year-only mentions are
  normalised to the 1st of the month/year.
- No authentication or multi-user support — this is a single-user
  local demo. Do not expose the backend publicly without adding auth.
- The Tavily integration has not been exercised against the live API
  (see verification note above).
