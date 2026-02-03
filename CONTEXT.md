# Auto Job Applier - Development Context

## Project History

This project was extracted from a fork of [browser-use](https://github.com/browser-use/browser-use) to be a standalone application that uses `browser-use` as a dependency.

**Original fork**: `github.com/rejozmathew/browser-use` (branch: `job-applier`)
**Standalone repo**: `github.com/rejozmathew/auto-job-applier`

---

## Current State (as of 2026-02-02)

### What Works
- ✅ **Web dashboard** at `localhost:8000` - add jobs, run queue, view status
- ✅ **Job queue system** - queued → running → applied/failed/needs_review
- ✅ **Profile-based form filling** - loads user data from `profile.json`
- ✅ **Multi-step form handling** - successfully completed 8-step Workday application
- ✅ **GIF recordings** - saves recording of each application attempt
- ✅ **Local LLM support** - optimized for `qwen3-vl-8b` via LM Studio

### Configuration
```env
OPENAI_API_BASE=http://192.168.1.27:1234/v1
OPENAI_API_KEY=local
OPENAI_MODEL=qwen/qwen3-vl-8b
JOB_APPLIER_MAX_STEPS=100
JOB_APPLIER_MAX_HISTORY=10
```

### Tested Platforms
- ✅ Alvarez & Marsal (Workday) - **Successfully submitted** (170 steps)
- ✅ SuccessFactors
- ✅ CBOE Careers

---

## Optimizations Already Implemented

### 1. Context Window Management
- **Problem**: LLM context overflowed during long applications
- **Solution**: `max_history_items=10` keeps only recent 10 steps in context
- **File**: `job_applier/agent.py` line 215

### 2. Screenshot Size Reduction
- **Problem**: Vision tokens were too high
- **Solution**: `llm_screenshot_size=(800, 600)` reduces token usage
- **File**: `job_applier/agent.py` line 214

### 3. Shorter Instructions
- **Problem**: Base prompt was ~5000 bytes
- **Solution**: Rewrote `instructions.md` to ~2400 bytes with focused directives
- **Key changes**: "Navigate FIRST", "Batch fill", "Keep thinking SHORT"

### 4. Success Detection Fix
- **Problem**: Agent saying "cannot complete" was marked as "applied"
- **Solution**: Check for failure phrases BEFORE success phrases
- **File**: `job_applier/agent.py` lines 252-263

---

## Known Issues / Planned Enhancements

### High Priority
1. **Heuristic form filler** - Parse DOM, match labels to profile, fill without LLM
2. **Dropdown handling** - Fuzzy match for country codes, partial text input
3. **Batch operations** - Fill multiple fields in one step instead of one-by-one

### Medium Priority
4. **Navigate first, think later** - Hardcode initial navigation, skip LLM reasoning
5. **Evidence/screenshot in dashboard** - Show final screenshot in job table
6. **Better error recovery** - Retry logic for stale element errors

### Nice to Have
7. **Parallel job processing** - Run multiple browsers simultaneously
8. **Resume from failed state** - Checkpoint and resume partially-filled forms
9. **Job deduplication** - Detect if already applied to same job

---

## Architecture

```
auto-job-applier/
├── job_applier/
│   ├── agent.py      # Core: JobApplyAgent uses browser-use Agent
│   ├── queue.py      # JobQueue: JSON-based job storage
│   ├── runner.py     # JobRunner: Orchestrates agent execution
│   └── api.py        # FastAPI server + HTML dashboard
├── run_applier.py    # CLI: serve, run, add commands
├── instructions.md   # LLM prompt template (with placeholders)
└── profile.json      # User data (not committed)
```

### Key Classes
- `JobApplyAgent` - Wraps browser-use Agent, builds prompts, interprets results
- `JobQueue` - Manages job_queue.json, tracks status
- `JobRunner` - Claims jobs from queue, runs agent, updates status
- FastAPI app - `/queue` GET/POST, `/run` POST, `/` serves dashboard

---

## User Feedback from Testing

> "When the browser opens, there are many LLM calls before the first page loads. You should navigate to URL first, then inspect DOM and fill forms."

> "For each form field, there's a screenshot and LLM call. Inefficient - should parse all DOM fields, match to profile heuristically, call LLM only for ambiguous fields."

> "Dropdown typed 'US' but dropdown showed 'United States (+1)' - got stuck in infinite loop."

---

## Files to Review

| File | Purpose | Key Lines |
|------|---------|-----------|
| `job_applier/agent.py` | Core agent logic | Lines 168-218 (Agent creation) |
| `job_applier/agent.py` | Status detection | Lines 248-305 (result parsing) |
| `instructions.md` | LLM prompt | Entire file (keep SHORT) |
| `.env` | Configuration | MAX_STEPS, MAX_HISTORY |

---

## How to Run

```bash
cd C:\GitClone\auto-job-applier
python run_applier.py serve
# Open http://127.0.0.1:8000
```

## How to Test a Job

1. Add URL to dashboard
2. Click "Run Next"
3. Watch browser automation
4. Check `artifacts/<job-id>/result.json` for details

---

## Next Steps

Start a new session with:
> "I'm working on auto-job-applier. Read CONTEXT.md for background. I want to implement [specific enhancement]."
