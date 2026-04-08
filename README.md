# OreHack Evaluation Engine

An automated AI-powered hackathon project scoring system that evaluates GitHub repositories and produces a structured 100-point score using static code analysis and a local LLM.

---

## Table of Contents

- [Overview](#overview)
- [How It Works](#how-it-works)
- [Scoring System](#scoring-system)
- [Project Structure](#project-structure)
- [Tech Stack](#tech-stack)
- [Setup & Installation](#setup--installation)
- [Usage](#usage)
- [Multi-Machine Setup](#multi-machine-setup)
- [Configuration](#configuration)
- [Database Schema](#database-schema)

---

## Overview

OreHack Evaluation Engine is the backend scoring system for the OreHack hackathon platform. It connects to a Supabase database, picks up submitted GitHub repositories, runs a full analysis pipeline, and writes the results back — all automatically, without any human intervention.

Teams submit their project through the frontend portal. The engine picks it up, evaluates it, and the leaderboard updates in real time.

It also supports a standalone CLI mode for manual testing and evaluation without any database connection.

---

## How It Works

The evaluation runs as an 8-stage pipeline:
```
Clone Repository      →  git clone into a temp directory
Scan Files            →  collect all file paths, ignore .git / node_modules / venv
Classify Files        →  categorize into backend / frontend / docs / config / binary
Static Analysis       →  AST parsing for functions, classes, loops, conditionals
Build Graphs          →  module dependency graph + function call graph
Build Context         →  folder structure, security scan, tech stack detection
LLM Evaluation        →  project understanding, technical rating, problem alignment
Final Scoring         →  2-pass LLM evaluation → 100-point score
```

---

## Scoring System

Total: **100 points**

### Technical — 65 pts

| Criterion | Max |
|---|---|
| Functionality | 10 |
| Tech Stack Efficiency | 8 |
| Code Quality & Modularity | 15 |
| Code Readability | 10 |
| Error Handling | 7 |
| Documentation | 10 |
| Security | 5 |

### Innovation — 25 pts

| Criterion | Max |
|---|---|
| Feasibility | 8 |
| Novelty | 6 |
| Problem Alignment | 6 |
| Scalability | 3 |
| Product Features | 2 |

### Completeness — 10 pts

| Criterion | Max |
|---|---|
| Feature Completeness | 5 |
| Project Polish | 3 |
| Deployment Readiness | 2 |

### Anchor Scores (Deterministic)

Some scores are computed purely from static analysis and cannot be changed by the LLM:

- **Security** — deducted per hardcoded secret, dangerous call, unsafe deserialization
- **Error Handling** — based on ratio of functions missing try/except blocks
- **Modularity** — function count base + folder structure bonus + module graph connectivity
- **Problem Alignment** — derived from the dedicated alignment module score

---

## Project Structure
```
OREHACKCLI/
├── main.py                        # Pipeline orchestrator + CLI entry point
├── worker.py                      # Supabase polling worker
├── supabase_client.py             # DB connection singleton
├── .env                           # Supabase credentials (not committed)
│
├── repo_handler/
│   ├── clone_repo.py              # git clone to temp dir
│   ├── repo_scanner.py            # recursive file discovery
│   └── file_classifier.py        # categorize files by type
│
├── static_analysis/
│   ├── ast_parser.py              # Python AST analysis
│   └── metrics_extractor.py      # aggregate metrics across all files
│
├── analysis/
│   └── multilang_analyzer.py     # multi-language analysis for JS/TS/Java/Go/Rust/etc.
│
├── graph_builder/
│   ├── module_graph.py            # import dependency graph
│   └── call_graph.py             # function call graph
│
├── context_engine/
│   ├── context_extractor.py      # build full evaluation context + folder structure
│   └── snippet_selector.py       # select representative code snippets
│
├── evaluation/
│   ├── project_understanding.py  # LLM: understand project type and purpose
│   ├── technical_evaluation.py   # LLM: code quality, complexity, architecture
│   ├── problem_alignment.py      # LLM: how well project matches problem statement
│   ├── final_evaluator.py        # 2-pass scoring engine (main scorer)
│   ├── security/
│   │   └── security_analyzer.py  # detect secrets, dangerous calls, missing handlers
│   └── techstack/
│       └── tech_stack_analyzer.py # detect frameworks, languages, categories
│
├── llm/
│   ├── ollama_client.py           # Ollama API wrapper
│   └── prompt_builder.py         # compact prompt builder
│
└── utils/
├── kv_parser.py               # key=value LLM response parser
└── json_utils.py              # JSON extraction fallback
```
---

## Tech Stack

| Component | Tool |
|---|---|
| Language | Python 3.11 |
| LLM | Ollama (local) — deepseek-coder:6.7b |
| Database | Supabase (PostgreSQL) |
| AST Parsing | Python `ast` module + `tree-sitter-languages` |
| DB Client | `supabase-py` |

> **Note:** Python 3.11 specifically — `tree-sitter-languages` is not compatible with Python 3.13.

---

## Supported Languages

The engine supports static analysis, dependency graphing, and security scanning across all major languages used in hackathons:

| Language | Static Analysis | Dependency Graph | Security Scan |
|---|---|---|---|
| Python | ✓ | ✓ | ✓ |
| JavaScript / JSX | ✓ | ✓ | ✓ |
| TypeScript / TSX | ✓ | ✓ | ✓ |
| Java | ✓ | ✓ | ✓ |
| Go | ✓ | ✓ | ✓ |
| Rust | ✓ | ✓ | ✓ |
| C / C++ | ✓ | ✓ | ✓ |
| PHP | ✓ | ✓ | ✓ |
| Ruby | ✓ | ✓ | ✓ |
| C# | ✓ | ✓ | ✓ |
| Dart | ✓ | ✓ | ✓ |
---

## Setup & Installation

### Prerequisites

- Python 3.11
- [Ollama](https://ollama.com) installed and running
- deepseek-coder:6.7b pulled
- Git installed
- Supabase project with the `Submissions` table (for worker mode only)

### Install
```bash
# Clone the repo
git clone https://github.com/your-org/orehack-evaluation-engine
cd orehack-evaluation-engine/evaluation_engine1

# Create virtual environment with Python 3.11
py -3.11 -m venv venv

# Activate
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS / Linux

# Install dependencies
pip install -r requirements.txt

# Pull the LLM model
ollama pull deepseek-coder:6.7b
```

---

## Usage

### CLI Mode (Manual / Testing)

Run directly from the terminal — no database connection needed. Useful for testing a single repo or evaluating outside the hackathon workflow.
```bash
# Make sure Ollama is running
ollama serve

# Run
python main.py
```

You will be prompted for:
Enter GitHub repository URL: https://github.com/username/repo
Enter problem statement: A full-stack web application for...

The full evaluation runs and prints the score breakdown to the terminal.

---

### Worker Mode (Automated / Hackathon)

Connects to Supabase, polls for queued submissions, evaluates them automatically, and writes scores back to the database. This is what runs during the actual hackathon.

Create a `.env` file in `OREHACKCLI/`:
```env
VITE_SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...
```

> Use the **service_role** key from Supabase → Project Settings → API. Not the anon key.

Then run:
```bash
python worker.py
```

The worker will:
- Poll every 10 seconds for rows where `Progress = 'queued'`
- Claim each row atomically (`queued → processing`)
- Run the full evaluation pipeline
- Write scores back to the DB (`processing → completed`)
- Reset to `queued` on failure for automatic retry

### Status Flow
```
Team submits    →  Progress = 'queued'
Worker picks up →  Progress = 'processing'
Evaluation done →  Progress = 'completed'  (scores written)
Error / failure →  Progress = 'queued'     (retried next poll)
```
---

## Multi-Machine Setup

To run on multiple machines simultaneously, just run `python worker.py` on each machine. No extra configuration needed.

The atomic claim logic prevents double-processing — even if 6 machines poll at the same second, only one will successfully claim each row.

---

## Configuration

Key settings in `worker.py`:
```python
TABLE          = "Submissions"   # Supabase table name (case-sensitive)
POLL_INTERVAL  = 10              # seconds between polls when idle
BATCH_SIZE     = 5               # rows fetched per poll
ERROR_BEHAVIOR = "queued"        # status on failure: 'queued' (retry) or 'rejected' (give up)
```

Key settings in `ollama_client.py`:
```python
PRIMARY_MODEL  = "deepseek-coder:6.7b"
REVIEWER_MODEL = "deepseek-coder:6.7b"
num_predict    = 512    # max output tokens per call
timeout        = 180    # seconds per attempt
retries        = 2      # total attempts before giving up
```

---

## Database Schema

The worker reads from and writes to the `Submissions` table in Supabase:

| Column | Type | Description |
|---|---|---|
| `teamID` | varchar | Primary key |
| `Team_Name` | varchar | Team display name |
| `Problem_Statement` | varchar | Problem statement submitted by team |
| `Repo_URL` | varchar | GitHub repository URL |
| `Progress` | varchar | `queued` / `processing` / `completed` |
| `Total_Scores` | float4 | Final score (0–100) |
| `Tech_Scores` | float4 | Technical score (0–65) |
| `Innov_Scores` | float4 | Innovation score (0–25) |
| `Completeness_Scores` | float4 | Completeness score (0–10) |
| `Reasoning` | varchar | LLM-generated summary text |

---

## Known Limitations

- No REST API wrapper — CLI and worker only
- LLM scores may vary by ±2–3 points between runs (anchor scores are always consistent)
- One repo evaluated at a time per worker instance