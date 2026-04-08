"""
worker.py
Place at: OreHack/evaluation_engine1/worker.py

Polling worker that:
  1. Finds rows in `submissions` where Progress = 'incomplete'
  2. Atomically claims each row (incomplete → processing) to prevent
     double-processing across multiple machines
  3. Runs the full evaluation pipeline
  4. Writes all scores + reasoning back to the DB (processing → completed)
  5. On any error, resets Progress back to 'incomplete' for retry

Run on each evaluation machine:
  python worker.py

To run multiple workers on different machines simultaneously, just run this
script on each machine — the atomic claim logic prevents any row from being
processed twice.

Install dependencies first:
  pip install supabase python-dotenv
"""

import time
import traceback
import sys
import os

from supabase_client import supabase
from main import run_pipeline

# ─── Config ────────────────────────────────────────────────────────────────────

TABLE          = "Submissions"
POLL_INTERVAL  = 10        # seconds between polls when idle
BATCH_SIZE     = 5         # max rows to fetch per poll (process one by one)
ERROR_BEHAVIOR = "queued"   # what to set Progress to on failure: 'incomplete' or 'rejected'

# ─── Helpers ───────────────────────────────────────────────────────────────────

def log(msg: str):
    """Timestamped print."""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def build_reasoning_text(result: dict) -> str:
    """
    Combine all LLM reasoning fields from the pipeline result into a single
    string for the Reasoning column.
    """
    parts = []

    # Project understanding
    understanding = result.get("understanding", {})
    if understanding.get("problem_summary"):
        parts.append(f"Problem: {understanding['problem_summary']}")
    if understanding.get("solution_summary"):
        parts.append(f"Solution: {understanding['solution_summary']}")
    if understanding.get("architecture_summary"):
        parts.append(f"Architecture: {understanding['architecture_summary']}")

    # Technical evaluation reasoning
    tech = result.get("technical", {})
    if tech.get("reasoning"):
        parts.append(f"Technical: {tech['reasoning']}")

    # Final evaluation reasoning (strengths / weaknesses / summary)
    final = result.get("final", {})
    reasoning = final.get("reasoning", {})
    if reasoning.get("strengths"):
        parts.append(f"Strengths: {reasoning['strengths']}")
    if reasoning.get("weaknesses"):
        parts.append(f"Weaknesses: {reasoning['weaknesses']}")
    if reasoning.get("overall_summary"):
        parts.append(f"Summary: {reasoning['overall_summary']}")

    return " | ".join(parts) if parts else "Evaluation completed."


def fetch_incomplete_rows() -> list:
    """Fetch up to BATCH_SIZE rows with Progress = 'incomplete'."""
    try:
        response = (
            supabase.table(TABLE)
            .select("teamID, Team_Name, Repo_URL, Problem_Statement")
            .eq("Progress", "queued")
            .limit(BATCH_SIZE)
            .execute()
        )
        return response.data or []
    except Exception as e:
        log(f"[ERROR] Failed to fetch rows: {e}")
        return []


def claim_row(team_id: str) -> bool:
    """
    Atomically claim a row: only succeeds if it's still 'incomplete'.
    Returns True if this worker won the race, False if another worker got it first.
    """
    try:
        result = (
            supabase.table(TABLE)
            .update({"Progress": "processing"})
            .eq("teamID", team_id)
            .eq("Progress", "queued")   # ← race condition guard
            .execute()
        )
        # If data is empty, another worker already claimed this row
        return bool(result.data)
    except Exception as e:
        log(f"[ERROR] Failed to claim row {team_id}: {e}")
        return False


def write_scores(team_id: str, result: dict):
    """Write evaluation results back to the DB row."""
    final = result.get("final", {})

    total_score        = final.get("final_score",         0)
    technical_score    = final.get("technical_total",     0)
    innovation_score   = final.get("innovation_total",    0)
    completeness_score = final.get("completeness_total",  0)
    reasoning_text     = build_reasoning_text(result)

    supabase.table(TABLE).update({
        "Progress":           "completed",
        "Total_Scores":       round(float(total_score),        1),
        "Tech_Scores":        round(float(technical_score),    1),
        "Innov_Scores":       round(float(innovation_score),   1),
        "Completeness_Scores":round(float(completeness_score), 1),
        "Reasoning":          reasoning_text[:2000],   # cap at 2000 chars for varchar
    }).eq("teamID", team_id).eq("Progress", "processing").execute()


def reset_row(team_id: str):
    """Reset a row back to ERROR_BEHAVIOR status on failure."""
    try:
        supabase.table(TABLE).update({
            "Progress": ERROR_BEHAVIOR
        }).eq("teamID", team_id).execute()
    except Exception as e:
        log(f"[ERROR] Failed to reset row {team_id}: {e}")


# ─── Core process loop ─────────────────────────────────────────────────────────

def process_row(row: dict):
    """Run the full evaluation pipeline on a single submission row."""

    team_id           = row.get("teamID", "?")
    team_name         = row.get("Team_Name", "?")
    repo_url          = row.get("Repo_URL", "").strip()
    problem_statement = row.get("Problem_Statement", "").strip()

    log(f"Processing [{team_id}] {team_name}  →  {repo_url}")

    # Validate inputs before even starting
    if not repo_url:
        log(f"  [SKIP] Row {team_id} has no Repo_URL — marking as {ERROR_BEHAVIOR}")
        reset_row(team_id)
        return

    if not problem_statement:
        log(f"  [WARN] Row {team_id} has no Problem_Statement — proceeding with empty string")

    try:
        result = run_pipeline(repo_url, problem_statement)

        if result is None:
            # run_pipeline returns None if analysis was completely empty
            raise ValueError("Pipeline returned None — no files were analyzed.")

        final = result.get("final", {})
        total = final.get("final_score", 0)

        write_scores(team_id, result)
        log(f"  [DONE] [{team_id}] {team_name} → {total}/100")

    except Exception:
        log(f"  [FAIL] [{team_id}] {team_name}")
        traceback.print_exc()
        reset_row(team_id)


# ─── Main polling loop ─────────────────────────────────────────────────────────

def run_worker():
    log("Worker started. Polling for queued submissions...")
    log(f"  Table:         {TABLE}")
    log(f"  Poll interval: {POLL_INTERVAL}s")
    log(f"  Batch size:    {BATCH_SIZE}")
    log(f"  On error:      Progress → '{ERROR_BEHAVIOR}'")
    log("")

    consecutive_empty = 0

    while True:
        rows = fetch_incomplete_rows()

        if not rows:
            consecutive_empty += 1
            if consecutive_empty == 1 or consecutive_empty % 3 == 0:
                # Log every 2 minutes of idle (12 × 10s) to show we're alive
                log(f"No queued rows. Waiting... (idle for ~{consecutive_empty * POLL_INTERVAL}s)")
            time.sleep(POLL_INTERVAL)
            continue

        consecutive_empty = 0
        log(f"Found {len(rows)} queued row(s).")

        for row in rows:
            team_id = row.get("teamID")
            if not team_id:
                log("  [SKIP] Row has no teamID — skipping.")
                continue

            # Try to atomically claim this row
            claimed = claim_row(team_id)
            if not claimed:
                log(f"  [SKIP] Row {team_id} already claimed by another worker.")
                continue

            process_row(row)

        # Short pause after processing a batch before polling again
        time.sleep(2)


if __name__ == "__main__":
    try:
        run_worker()
    except KeyboardInterrupt:
        log("Worker stopped by user.")
        sys.exit(0)
    except Exception as e:
        log(f"[FATAL] Worker crashed: {e}")
        traceback.print_exc()
        sys.exit(1)
