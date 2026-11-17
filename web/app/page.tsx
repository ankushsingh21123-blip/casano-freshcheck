"use client";

import { useCallback, useEffect, useState } from "react";
import {
  createCheck,
  getHealth,
  listChecks,
  type CheckRecord,
} from "../lib/api";

const VERDICT_LABELS: Record<string, string> = {
  FRESH: "FRESH",
  POSSIBLY_STALE: "POSSIBLY STALE",
  STALE: "STALE",
  UNKNOWN: "UNKNOWN",
};

function signalString(
  signals: Record<string, unknown>,
  key: string
): string | null {
  const value = signals[key];
  return typeof value === "string" ? value : null;
}

function signalNumber(
  signals: Record<string, unknown>,
  key: string
): number | null {
  const value = signals[key];
  return typeof value === "number" ? value : null;
}

function signalStringArray(
  signals: Record<string, unknown>,
  key: string
): string[] {
  const value = signals[key];
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string");
}

function formatDateTime(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleString();
}

function VerdictCard({ check }: { check: CheckRecord }) {
  const overlap = signalNumber(check.signals, "keyword_overlap");
  const gapDays = signalNumber(check.signals, "evidence_date_gap_days");
  const newest = signalString(check.signals, "newest_evidence_date");
  const claimsNotFound = signalStringArray(
    check.signals,
    "claims_not_found_in_evidence"
  );
  const claimsFound = signalStringArray(
    check.signals,
    "claims_found_in_evidence"
  );
  const newerYears = check.signals["newer_years_in_evidence"];
  const newerYearsText = Array.isArray(newerYears)
    ? newerYears.map(String).join(", ")
    : "";

  return (
    <section className="card" aria-label="Check result">
      <div className="verdict-header">
        <span className={`verdict-badge verdict-${check.verdict}`}>
          {VERDICT_LABELS[check.verdict] ?? check.verdict}
        </span>
        <span className="meta">
          Check #{check.id} · {check.mode} mode · {check.topic} ·{" "}
          {formatDateTime(check.created_at)}
        </span>
      </div>

      <p>
        <strong>Question:</strong> {check.question}
      </p>
      <p>
        <strong>Stored answer:</strong>
      </p>
      <div className="stored-answer">{check.answer}</div>
      <p className="meta">
        Answer date: {check.answer_date ?? "not supplied"} · Search query
        used: {check.query}
      </p>

      {check.error ? (
        <div className="error-banner" role="alert">
          <strong>Live search failed ({check.error.kind}):</strong>{" "}
          {check.error.detail} No freshness verdict could be determined.
        </div>
      ) : null}

      <h3>Reasons</h3>
      <ul className="reasons">
        {check.reasons.map((reason, index) => (
          <li key={index}>{reason}</li>
        ))}
      </ul>

      <h3>Signals</h3>
      <div className="signals-grid">
        <div className="signal">
          <div className="signal-label">Newest evidence date</div>
          <div className="signal-value">{newest ?? "none"}</div>
        </div>
        <div className="signal">
          <div className="signal-label">Answer date</div>
          <div className="signal-value">
            {check.answer_date ?? "not supplied"}
          </div>
        </div>
        <div className="signal">
          <div className="signal-label">Date gap (days)</div>
          <div className="signal-value">
            {gapDays === null ? "not comparable" : String(gapDays)}
          </div>
        </div>
        <div className="signal">
          <div className="signal-label">Keyword overlap</div>
          <div className="signal-value">
            {overlap === null ? "not computed" : `${Math.round(overlap * 100)}%`}
          </div>
        </div>
        <div className="signal">
          <div className="signal-label">Evidence items</div>
          <div className="signal-value">
            {String(signalNumber(check.signals, "evidence_count") ?? check.evidence.length)}
          </div>
        </div>
        <div className="signal">
          <div className="signal-label">Newer years in evidence</div>
          <div className="signal-value">{newerYearsText || "none"}</div>
        </div>
      </div>

      {claimsFound.length > 0 ? (
        <p className="meta">
          Claims found in evidence: {claimsFound.join(", ")}
        </p>
      ) : null}
      {claimsNotFound.length > 0 ? (
        <p className="meta">
          Claims not found in evidence: {claimsNotFound.join(", ")}
        </p>
      ) : null}

      <h3>Evidence</h3>
      {check.evidence.length === 0 ? (
        <div className="empty-state">
          {check.mode === "offline"
            ? "No live evidence — offline mode performed no search."
            : "No evidence was returned for this check."}
        </div>
      ) : (
        <ul className="evidence-list">
          {check.evidence.map((item) => (
            <li key={item.url} className="evidence-item">
              <a href={item.url} target="_blank" rel="noreferrer">
                {item.title}
              </a>
              <div className="evidence-date">
                {item.date_display}
                {item.date_source === "snippet_date"
                  ? " (date extracted from snippet)"
                  : item.date_source === "published_date"
                    ? " (published date)"
                    : ""}
                {" · "}
                {item.url}
              </div>
              <p className="evidence-snippet">{item.snippet}</p>
            </li>
          ))}
        </ul>
      )}

      <p className="meta">{check.message}</p>
    </section>
  );
}

export default function HomePage() {
  const [mode, setMode] = useState<string | null>(null);
  const [backendDown, setBackendDown] = useState(false);
  const [checks, setChecks] = useState<CheckRecord[]>([]);
  const [selected, setSelected] = useState<CheckRecord | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [answerDate, setAnswerDate] = useState("");
  const [topic, setTopic] = useState("general");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [health, history] = await Promise.all([getHealth(), listChecks()]);
      setMode(health.mode);
      setBackendDown(false);
      setChecks(history);
    } catch {
      setBackendDown(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    if (!question.trim() || !answer.trim()) {
      setFormError("Question and stored answer are both required.");
      return;
    }
    setSubmitting(true);
    try {
      const created = await createCheck({
        question: question.trim(),
        answer: answer.trim(),
        answer_date: answerDate || undefined,
        topic,
      });
      setSelected(created);
      setChecks((previous) => [created, ...previous]);
      await refreshModeOnly();
    } catch (error) {
      setFormError(
        error instanceof Error
          ? error.message
          : "The check could not be run. Is the backend running?"
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function refreshModeOnly() {
    try {
      const health = await getHealth();
      setMode(health.mode);
      setBackendDown(false);
    } catch {
      setBackendDown(true);
    }
  }

  function clearForm() {
    setQuestion("");
    setAnswer("");
    setAnswerDate("");
    setTopic("general");
    setFormError(null);
  }

  const pillClass = backendDown ? "down" : mode === "live" ? "live" : "offline";
  const pillText = backendDown
    ? "Backend unavailable"
    : mode === "live"
      ? "Live evidence via Tavily"
      : "Offline — no Tavily key set, no live search performed";

  return (
    <>
      <header className="header">
        <div className="header-inner">
          <div>
            <h1 className="product-name">FreshCheck</h1>
            <p className="product-tagline">
              Stale-Answer Detector for AI Applications · by Casano
            </p>
          </div>
          <span className={`mode-pill ${pillClass}`}>{pillText}</span>
        </div>
      </header>

      <main className="container">
        <div className="notice">
          <strong>Heuristic detector, not ground truth.</strong> Verdicts
          come from transparent signals — evidence dates, date/number claim
          matching, and keyword overlap — and every signal is shown below
          each verdict so you can judge for yourself.
        </div>

        {backendDown ? (
          <div className="error-banner" role="alert">
            The backend is not reachable. Start it with{" "}
            <code>uvicorn app.main:app --reload</code> from the{" "}
            <code>backend/</code> directory, then refresh this page.
          </div>
        ) : null}

        <section className="card" aria-label="New freshness check">
          <h2>Check a stored answer</h2>
          <p className="card-sub">
            Paste the question and the answer your AI application stored.
            In live mode one Tavily search (basic depth, 5 results) is run
            per check.
          </p>
          <form onSubmit={handleSubmit}>
            <div className="field">
              <label htmlFor="question">Question</label>
              <input
                id="question"
                type="text"
                value={question}
                maxLength={500}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="What did the user ask?"
                required
              />
              <div className="char-count">{question.length} / 500</div>
            </div>
            <div className="field">
              <label htmlFor="answer">Stored answer</label>
              <textarea
                id="answer"
                value={answer}
                maxLength={5000}
                onChange={(event) => setAnswer(event.target.value)}
                placeholder="Paste the exact answer that was stored."
                required
              />
              <div className="char-count">{answer.length} / 5000</div>
            </div>
            <div className="field-row">
              <div className="field">
                <label htmlFor="answer-date">
                  Answer date (optional)
                </label>
                <input
                  id="answer-date"
                  type="date"
                  value={answerDate}
                  onChange={(event) => setAnswerDate(event.target.value)}
                />
              </div>
              <div className="field">
                <label htmlFor="topic">Search topic</label>
                <select
                  id="topic"
                  value={topic}
                  onChange={(event) => setTopic(event.target.value)}
                >
                  <option value="general">General</option>
                  <option value="news">News</option>
                </select>
              </div>
            </div>
            {formError ? (
              <div className="error-banner" role="alert">
                {formError}
              </div>
            ) : null}
            <div className="button-row">
              <button
                className="btn-primary"
                type="submit"
                disabled={submitting}
              >
                {submitting ? "Checking…" : "Run freshness check"}
              </button>
              <button
                className="btn-ghost"
                type="button"
                onClick={clearForm}
              >
                Clear form
              </button>
            </div>
          </form>
        </section>

        {selected ? <VerdictCard check={selected} /> : null}

        <section className="card" aria-label="Check history">
          <h2>History</h2>
          <p className="card-sub">
            Past checks, newest first. Select one to see its verdict,
            signals, and evidence.
          </p>
          {checks.length === 0 ? (
            <div className="empty-state">
              No checks yet. Run your first freshness check above.
            </div>
          ) : (
            <>
              <ul className="history-list">
                {checks.map((check) => (
                  <li key={check.id}>
                    <button
                      type="button"
                      className={`history-item${selected?.id === check.id ? " selected" : ""}`}
                      onClick={() => setSelected(check)}
                    >
                      <span className="history-question">
                        {check.question}
                      </span>
                      <span className="history-meta">
                        <span
                          className={`verdict-badge verdict-${check.verdict}`}
                        >
                          {VERDICT_LABELS[check.verdict] ?? check.verdict}
                        </span>
                        <span>{check.mode} mode</span>
                        <span>{check.topic}</span>
                        <span>{formatDateTime(check.created_at)}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
              <div className="button-row" style={{ marginTop: 16 }}>
                <button
                  className="btn-ghost"
                  type="button"
                  onClick={() => void refresh()}
                >
                  Refresh history
                </button>
              </div>
            </>
          )}
        </section>
      </main>
    </>
  );
}
