"""
worker.py  —  OreHack Evaluation Worker
Place at: OreHack/evaluation_engine1/worker.py

Status flow:
    queued      → processing  → completed          (success)
    queued      → processing  → queued             (transient fail, retry_count < MAX_RETRIES)
    queued      → processing  → rejected           (permanent fail OR retry_count >= MAX_RETRIES)
    processing  → queued                           (stale recovery — machine crashed mid-eval)
    rejected    → queued                           (retry pass — after ALL queued+processing clear)

Bulletproof design:
    - Atomic claim: single UPDATE with WHERE Progress='queued' guard
      prevents any double-processing regardless of how many machines poll
    - claimed_at timestamp: rows stuck in 'processing' for too long
      are auto-recovered (handles machine crash mid-evaluation)
    - retry_count: rows that keep failing are rejected after MAX_RETRIES
      instead of looping forever
    - Rejected retry pass: when the queue is fully clear, rejected rows
      get one more chance — satisfies the requirement to retry after
      all other evaluations complete
    - BATCH_SIZE=1: each machine claims and processes one row at a time,
      keeping all machines active in parallel with no blocking

Run on each evaluation machine:
    python worker.py

Multiple machines can run simultaneously — no configuration needed.
The atomic claim logic handles all coordination automatically.

Dependencies:
    pip install supabase python-dotenv requests
"""

import time
import traceback
import sys
import os
from datetime import datetime, timezone, timedelta

import requests

from supabase_client import supabase
from main import run_pipeline


# ─── Configuration ────────────────────────────────────────────────────────────

TABLE         = "submissions"   # CASE-SENSITIVE — must match Supabase exactly
POLL_INTERVAL = 10              # seconds between polls when idle
BATCH_SIZE    = 1               # rows fetched per poll — keep at 1 for parallel multi-machine
MAX_RETRIES   = 3               # max transient failure retries before a row is rejected
STALE_TIMEOUT = 30              # minutes — rows stuck in 'processing' longer than this
                                # are assumed to be from a crashed machine and recovered
REASONING_CAP = 4000            # max chars written to Reasoning column
OLLAMA_URL    = os.environ.get("OLLAMA_URL", "http://localhost:11434")

# Git clone error keywords that indicate a permanent, non-retryable failure
PERMANENT_CLONE_ERRORS = [
    "not found", "repository not found", "clone failed",
    "could not read from remote", "authentication failed",
    "403", "404", "permission denied",
]


# ─── Logging ──────────────────────────────────────────────────────────────────

def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def log_separator():
    print(f"{'─' * 60}", flush=True)


# ─── Startup Health Check ─────────────────────────────────────────────────────

def check_health():
    """
    Verify Supabase and Ollama are both reachable before starting.
    Exits immediately with a clear message if either is unavailable.
    """
    log("Running startup health checks...")
    all_ok = True

    # Check Supabase
    try:
        supabase.table(TABLE).select("teamID").limit(1).execute()
        log(f"  ✓ Supabase — table '{TABLE}' reachable")
    except Exception as e:
        log(f"  ✗ Supabase connection failed: {e}")
        log("    → Check VITE_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env")
        all_ok = False

    # Check Ollama
    try:
        resp   = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        models = [m["name"] for m in resp.json().get("models", [])]
        log(f"  ✓ Ollama running — models: {models}")
    except Exception:
        log(f"  ✗ Ollama not reachable at {OLLAMA_URL}")
        log("    → Start it with: ollama serve")
        all_ok = False

    if not all_ok:
        log("\nHealth check failed. Fix the issues above and restart.")
        sys.exit(1)

    log("All checks passed.\n")


# ─── Stale Row Recovery ───────────────────────────────────────────────────────

def recover_stale_rows():
    """
    Find rows stuck in 'processing' longer than STALE_TIMEOUT minutes.
    These belong to machines that crashed mid-evaluation.
    Reset them to 'queued' so they can be picked up again.

    This runs at the start of every poll cycle.
    """
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=STALE_TIMEOUT)).isoformat()
        stale  = (
            supabase.table(TABLE)
            .select("teamID, Team_Name, claimed_at")
            .eq("Progress", "processing")
            .lt("claimed_at", cutoff)
            .execute()
        )

        if not stale.data:
            return

        for row in stale.data:
            tid  = row.get("teamID")
            name = row.get("Team_Name", "?")
            log(f"  [STALE] [{tid}] {name} stuck in processing since {row.get('claimed_at')} — recovering")
            (
                supabase.table(TABLE)
                .update({
                    "Progress":   "queued",
                    "claimed_at": None,
                    "last_error": f"Recovered: machine crashed or timed out after {STALE_TIMEOUT}min",
                    "retry_count": supabase.raw("retry_count + 1"),
                })
                .eq("teamID", tid)
                .eq("Progress", "processing")   # guard — only if still processing
                .execute()
            )

    except Exception as e:
        log(f"  [WARN] Stale row recovery failed: {e}")


# ─── Rejected Retry Pass ──────────────────────────────────────────────────────

def check_for_rejected_retry() -> bool:
    """
    When the queue is fully clear (no queued rows, no processing rows),
    reset rejected rows back to queued for one more attempt.

    Returns True if any rejected rows were reset (triggers another eval cycle).
    Returns False if nothing to do.
    """
    try:
        # Check if anything is still in progress
        active = (
            supabase.table(TABLE)
            .select("teamID")
            .in_("Progress", ["queued", "processing"])
            .limit(1)
            .execute()
        )
        if active.data:
            return False  # still work to do — don't touch rejected yet

        # Queue is clear — check for rejected rows
        rejected = (
            supabase.table(TABLE)
            .select("teamID, Team_Name, retry_count")
            .eq("Progress", "rejected")
            .execute()
        )
        if not rejected.data:
            return False  # nothing rejected either

        log(f"\n{'═' * 60}")
        log(f"Queue clear. Found {len(rejected.data)} rejected row(s) — giving them one more chance.")
        log(f"{'═' * 60}")

        for row in rejected.data:
            tid  = row.get("teamID")
            name = row.get("Team_Name", "?")
            log(f"  → Resetting [{tid}] {name} to queued (was rejected)")
            (
                supabase.table(TABLE)
                .update({
                    "Progress":    "queued",
                    "retry_count": 0,          # reset counter for this retry pass
                    "last_error":  None,
                })
                .eq("teamID", tid)
                .eq("Progress", "rejected")   # guard
                .execute()
            )

        return True

    except Exception as e:
        log(f"  [WARN] Rejected retry check failed: {e}")
        return False


# ─── DB Operations ────────────────────────────────────────────────────────────

def fetch_queued_rows() -> list:
    """Fetch up to BATCH_SIZE rows with Progress = 'queued'."""
    try:
        response = (
            supabase.table(TABLE)
            .select("teamID, Team_Name, Repo_URL, Problem_Statement, retry_count")
            .eq("Progress", "queued")
            .order("teamID")        # consistent ordering across machines
            .limit(BATCH_SIZE)
            .execute()
        )
        return response.data or []
    except Exception as e:
        log(f"[ERROR] Failed to fetch rows: {e}")
        return []


def claim_row(team_id: str) -> bool:
    """
    Atomically claim a row.

    The WHERE Progress='queued' condition is the race condition guard.
    PostgreSQL executes the UPDATE atomically — only ONE machine can win.
    Every other machine gets an empty result and skips this row.

    Also sets claimed_at to NOW() so stale recovery can detect crashed machines.
    """
    try:
        result = (
            supabase.table(TABLE)
            .update({
                "Progress":   "processing",
                "claimed_at": datetime.now(timezone.utc).isoformat(),
            })
            .eq("teamID",  team_id)
            .eq("Progress", "queued")     # ← THE RACE CONDITION GUARD
            .execute()
        )
        return bool(result.data)
    except Exception as e:
        log(f"  [ERROR] Failed to claim {team_id}: {e}")
        return False


def reject_row(team_id: str, reason: str):
    """Permanently reject a row. Will not be retried until rejected retry pass."""
    try:
        (
            supabase.table(TABLE)
            .update({
                "Progress":   "rejected",
                "claimed_at": None,
                "last_error": reason[:500],
            })
            .eq("teamID", team_id)
            .execute()
        )
        log(f"  [REJECTED] {team_id} — {reason[:100]}")
    except Exception as e:
        log(f"  [ERROR] Failed to reject {team_id}: {e}")


def reset_row_for_retry(team_id: str, retry_count: int, error: str):
    """
    Reset a row to 'queued' for retry after a transient failure.
    If retry_count has reached MAX_RETRIES, reject instead.
    """
    new_count = retry_count + 1

    if new_count >= MAX_RETRIES:
        log(f"  [MAX RETRIES] {team_id} reached {MAX_RETRIES} retries — rejecting")
        try:
            (
                supabase.table(TABLE)
                .update({
                    "Progress":    "rejected",
                    "claimed_at":  None,
                    "retry_count": new_count,
                    "last_error":  f"Max retries ({MAX_RETRIES}) reached. Last error: {error[:300]}",
                })
                .eq("teamID", team_id)
                .execute()
            )
        except Exception as e:
            log(f"  [ERROR] Failed to reject after max retries {team_id}: {e}")
    else:
        log(f"  [RETRY] {team_id} → queued (attempt {new_count}/{MAX_RETRIES})")
        try:
            (
                supabase.table(TABLE)
                .update({
                    "Progress":    "queued",
                    "claimed_at":  None,
                    "retry_count": new_count,
                    "last_error":  error[:500],
                })
                .eq("teamID", team_id)
                .execute()
            )
        except Exception as e:
            log(f"  [ERROR] Failed to reset {team_id}: {e}")


def write_scores(team_id: str, result: dict) -> bool:
    """
    Write evaluation scores back to the DB.
    Only writes if Progress is still 'processing' — guards against
    overwriting a row that was recovered by stale detection.
    Returns True on success, False on failure.
    """
    final = result.get("final", {})

    try:
        response = (
            supabase.table(TABLE)
            .update({
                "Progress":            "completed",
                "claimed_at":          None,
                "Total_Scores":        round(float(final.get("final_score",        0)), 1),
                "Tech_Scores":         round(float(final.get("technical_total",    0)), 1),
                "Innov_Scores":        round(float(final.get("innovation_total",   0)), 1),
                "Completeness_Scores": round(float(final.get("completeness_total", 0)), 1),
                "Reasoning":           build_reasoning_text(result)[:REASONING_CAP],
                "last_error":          None,
            })
            .eq("teamID",   team_id)
            .eq("Progress", "processing")   # safety guard
            .execute()
        )

        if not response.data:
            log(f"  [WARN] write_scores: 0 rows updated for {team_id} "
                f"— row may have been recovered by stale detection")
            return False

        total = final.get("final_score", 0)
        tech  = final.get("technical_total", 0)
        innov = final.get("innovation_total", 0)
        comp  = final.get("completeness_total", 0)
        log(f"  [SAVED] Total={total}  Tech={tech}  Innovation={innov}  Completeness={comp}")
        return True

    except Exception as e:
        log(f"  [ERROR] Failed to write scores for {team_id}: {e}")
        return False


# ─── Reasoning Builder ────────────────────────────────────────────────────────

def build_reasoning_text(result: dict) -> str:
    parts = []

    u = result.get("understanding", {})
    if u.get("problem_summary"):    parts.append(f"Problem: {u['problem_summary']}")
    if u.get("solution_summary"):   parts.append(f"Solution: {u['solution_summary']}")
    if u.get("architecture_summary"): parts.append(f"Architecture: {u['architecture_summary']}")

    t = result.get("technical", {})
    if t.get("reasoning"):          parts.append(f"Technical: {t['reasoning']}")

    r = result.get("final", {}).get("reasoning", {})
    if r.get("strengths"):          parts.append(f"Strengths: {r['strengths']}")
    if r.get("weaknesses"):         parts.append(f"Weaknesses: {r['weaknesses']}")
    if r.get("overall_summary"):    parts.append(f"Summary: {r['overall_summary']}")

    return " | ".join(parts) if parts else "Evaluation completed."


# ─── Row Processor ────────────────────────────────────────────────────────────

def process_row(row: dict):
    """
    Run the full evaluation pipeline on a single claimed row.

    Failure classification:
        Permanent → rejected:
            - No Repo_URL
            - Repo not found / private / deleted
            - Repo has no analyzable code

        Transient → queued (up to MAX_RETRIES, then rejected):
            - LLM timeout or crash
            - Network error during evaluation
            - Any unexpected pipeline exception
            - DB write failure after successful evaluation
    """
    team_id     = row.get("teamID", "?")
    team_name   = row.get("Team_Name", "Unknown")
    repo_url    = (row.get("Repo_URL")          or "").strip()
    problem_stmt = (row.get("Problem_Statement") or "").strip()
    retry_count = int(row.get("retry_count", 0))

    log_separator()
    log(f"Processing [{team_id}] {team_name}")
    log(f"  Repo:    {repo_url or '(none)'}")
    log(f"  Attempt: {retry_count + 1}/{MAX_RETRIES}")

    # ── Permanent: no URL ─────────────────────────────────────────────────────
    if not repo_url:
        reject_row(team_id, "No Repo_URL submitted")
        return

    if not problem_stmt:
        log(f"  [WARN] No Problem_Statement — proceeding without it")

    # ── Run evaluation pipeline ───────────────────────────────────────────────
    try:
        result = run_pipeline(repo_url, problem_stmt)

        # Permanent: repo has no code
        if result is None:
            reject_row(team_id, "Repo has no analyzable files (empty or docs-only)")
            return

        # Success — write scores
        total = result.get("final", {}).get("final_score", 0)
        log(f"  [SCORED] {team_name} → {total}/100")

        saved = write_scores(team_id, result)
        if saved:
            log(f"  [DONE] [{team_id}] {team_name} → {total}/100")
        else:
            # Write failed after successful eval — retry so scores aren't lost
            reset_row_for_retry(team_id, retry_count, "Score write failed after successful evaluation")

    # ── Permanent: git clone error ────────────────────────────────────────────
    except RuntimeError as e:
        err = str(e)
        if any(kw in err.lower() for kw in PERMANENT_CLONE_ERRORS):
            reject_row(team_id, err[:300])
        else:
            # Unknown RuntimeError — treat as transient
            log(f"  [FAIL] RuntimeError: {err[:150]}")
            reset_row_for_retry(team_id, retry_count, err[:300])

    # ── Transient: everything else ────────────────────────────────────────────
    except Exception as e:
        err = traceback.format_exc()
        log(f"  [FAIL] Pipeline error: {str(e)[:150]}")
        print(err, flush=True)
        reset_row_for_retry(team_id, retry_count, str(e)[:300])


# ─── Main Poll Loop ───────────────────────────────────────────────────────────

def run_worker():
    check_health()

    log("Worker started.")
    log(f"  Table:         {TABLE}")
    log(f"  Poll interval: {POLL_INTERVAL}s")
    log(f"  Max retries:   {MAX_RETRIES}")
    log(f"  Stale timeout: {STALE_TIMEOUT} minutes")
    log(f"  Reasoning cap: {REASONING_CAP} chars")
    log("")

    consecutive_empty  = 0
    rejected_retry_done = False   # tracks if we've done the rejected retry pass

    while True:

        # ── Step 1: Recover stale rows (crashed machines) ──────────────────
        recover_stale_rows()

        # ── Step 2: Fetch queued rows ──────────────────────────────────────
        rows = fetch_queued_rows()

        if not rows:
            consecutive_empty += 1

            # ── Step 3: When queue is empty, try rejected retry pass ───────
            if not rejected_retry_done:
                retried = check_for_rejected_retry()
                if retried:
                    rejected_retry_done = False  # new rows queued — keep running
                    consecutive_empty   = 0
                    time.sleep(2)
                    continue
                else:
                    rejected_retry_done = True   # nothing to retry — truly idle

            # Log idle status every 2 minutes
            if consecutive_empty == 1 or consecutive_empty % 12 == 0:
                idle_sec = consecutive_empty * POLL_INTERVAL
                idle_min = idle_sec // 60
                if idle_min > 0:
                    log(f"No queued rows. Idle for {idle_min}m {idle_sec % 60}s...")
                else:
                    log("No queued rows. Waiting...")

            time.sleep(POLL_INTERVAL)
            continue

        # New rows found — reset idle tracking
        consecutive_empty   = 0
        rejected_retry_done = False   # reset so we check rejected again when queue clears

        log(f"Found {len(rows)} queued row(s).")

        for row in rows:
            team_id = row.get("teamID")
            if not team_id:
                log("  [SKIP] Row has no teamID.")
                continue

            # ── Step 4: Atomic claim ───────────────────────────────────────
            claimed = claim_row(team_id)
            if not claimed:
                # Another worker got here first — completely normal
                log(f"  [SKIP] {team_id} already claimed by another worker.")
                continue

            # ── Step 5: Process ────────────────────────────────────────────
            process_row(row)
            time.sleep(1)   # brief pause between rows

        time.sleep(2)   # pause after batch before next poll


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        run_worker()
    except KeyboardInterrupt:
        log("\nWorker stopped by user.")
        sys.exit(0)
    except Exception as e:
        log(f"[FATAL] Worker crashed: {e}")
        traceback.print_exc()
        sys.exit(1)