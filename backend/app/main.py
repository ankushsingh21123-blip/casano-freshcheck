"""FastAPI application: stale-answer checks backed by Tavily search.

Modes:
  * live    — TAVILY_API_KEY is set; each check runs one Tavily search.
  * offline — no key set; no live search is performed. The check still
              extracts date/number claims from the answer itself and is
              labelled answer-only analysis with verdict UNKNOWN.

Verdicts are heuristics, not ground truth; every signal is returned.
Tavily failures are stored and returned as honest error states, never
as faked verdicts. The API key is never exposed in any response.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import get_cors_origins, get_mode, get_tavily_api_key
from .db import get_check, init_db, insert_check, list_checks
from .models import CheckCreate, CheckResponse, HealthResponse
from .query import derive_query
from .tavily import TavilyError, search_tavily
from .verdict import answer_only_analysis, evaluate_verdict

HEURISTIC_NOTE = (
    "Heuristic detector: verdicts are based on transparent signals "
    "(evidence dates, claim matching, keyword overlap) and are not ground truth."
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="casano-freshcheck",
    description="Stale-Answer Detector for AI Applications. " + HEURISTIC_NOTE,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/", response_model=dict)
def read_root() -> dict:
    return {
        "service": "casano-freshcheck",
        "mode": get_mode(),
        "note": HEURISTIC_NOTE,
    }


@app.get("/health", response_model=HealthResponse)
def read_health() -> HealthResponse:
    return HealthResponse(status="ok", mode=get_mode(), service="casano-freshcheck")


@app.post("/checks", response_model=CheckResponse, status_code=201)
def create_check(payload: CheckCreate) -> CheckResponse:
    query = derive_query(payload.question, payload.answer)
    answer_date_str = payload.answer_date.isoformat() if payload.answer_date else None

    api_key = get_tavily_api_key()
    if api_key is None:
        signals = answer_only_analysis(payload.answer)
        signals["answer_date"] = answer_date_str
        record = {
            "question": payload.question,
            "answer": payload.answer,
            "answer_date": answer_date_str,
            "topic": payload.topic,
            "mode": "offline",
            "verdict": "UNKNOWN",
            "query": query,
            "reasons": [
                "Offline mode: no Tavily API key is set, so no live search "
                "was performed and freshness cannot be judged.",
                "The signals below are answer-only analysis: date and "
                "number claims extracted from the stored answer itself.",
            ],
            "signals": signals,
            "evidence": [],
            "error": None,
            "message": (
                "Offline — live search needs TAVILY_API_KEY. Set it in "
                "backend/.env (see .env.example) and restart the backend. "
                + HEURISTIC_NOTE
            ),
        }
        return CheckResponse(**insert_check(record))

    try:
        evidence = search_tavily(query, payload.topic, api_key)
    except TavilyError as exc:
        signals = answer_only_analysis(payload.answer)
        signals["answer_date"] = answer_date_str
        signals["tavily_error"] = {"kind": exc.kind, "detail": exc.detail}
        record = {
            "question": payload.question,
            "answer": payload.answer,
            "answer_date": answer_date_str,
            "topic": payload.topic,
            "mode": "live",
            "verdict": "UNKNOWN",
            "query": query,
            "reasons": [
                f"Live search failed ({exc.kind}): {exc.detail}",
                "No verdict could be determined from live evidence.",
            ],
            "signals": signals,
            "evidence": [],
            "error": {"kind": exc.kind, "detail": exc.detail},
            "message": (
                "Live search failed; this check has no freshness verdict. "
                + HEURISTIC_NOTE
            ),
        }
        return CheckResponse(**insert_check(record))

    outcome = evaluate_verdict(payload.answer, payload.answer_date, evidence)
    record = {
        "question": payload.question,
        "answer": payload.answer,
        "answer_date": answer_date_str,
        "topic": payload.topic,
        "mode": "live",
        "verdict": outcome["verdict"],
        "query": query,
        "reasons": outcome["reasons"],
        "signals": outcome["signals"],
        "evidence": evidence,
        "error": None,
        "message": "Checked against live Tavily evidence. " + HEURISTIC_NOTE,
    }
    return CheckResponse(**insert_check(record))


@app.get("/checks", response_model=dict)
def read_checks(limit: int = Query(default=50, ge=1, le=100)) -> dict:
    checks = list_checks(limit=limit)
    return {"checks": [CheckResponse(**check).model_dump() for check in checks]}


@app.get("/checks/{check_id}", response_model=CheckResponse)
def read_check(check_id: int) -> CheckResponse:
    check = get_check(check_id)
    if check is None:
        raise HTTPException(status_code=404, detail="Check not found")
    return CheckResponse(**check)
