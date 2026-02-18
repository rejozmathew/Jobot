# Auto Job Applier

An automated job application agent powered by [browser-use](https://github.com/browser-use/browser-use). Uses AI (local LLMs or OpenAI) to navigate job application forms and submit applications automatically.

## Features

- 🌐 **Web Dashboard** - Manage job queue at `localhost:8000` with expandable step details and rich diagnostics
- ⏸️ **Human-in-the-Loop** - Pause/Resume control to manually intervene when the agent gets stuck (Co-Browsing)
- ⏹️ **Stop & Cleanup** - Terminate jobs instantly and auto-recover from stuck states
- 🤖 **AI-Powered** - Uses vision LLMs to understand and fill forms
- ⚡ **Smart Fill** - Heuristic auto-filling of common fields (Name, Email, etc.) for speed
- 📋 **Queue System** - Add jobs, track status (queued → running → applied/failed)
- 🗄️ **SQLite Database** - Persistent storage with step tracking and deep diagnostics (memory, reasoning)
- 🎥 **Recordings** - Generates GIF recordings of each application attempt
- ⚙️ **Configurable** - Works with local LLMs (LM Studio) or OpenAI
- 🔒 **Profile-Based** - Store your info once, use for all applications
- 🚀 **Optimized** - Programmatic navigation and resume-first strategy for efficiency

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure Environment

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

For **local LLM** (LM Studio):
```env
OPENAI_API_BASE=http://localhost:1234/v1
OPENAI_API_KEY=local
OPENAI_MODEL=qwen/qwen3-vl-8b
```

For **OpenAI**:
```env
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4o
```

### 3. Create Your Profile

Copy `profile.example.json` to `profile.json` and fill in your details:

```bash
cp profile.example.json profile.json
```

Edit `profile.json` with your real information (name, email, work history, etc.)

### 4. Add Your Resume

Place your resume PDF in the project directory and update the path in `profile.json`:

```json
{
  "resume": {
    "path": "./your-resume.pdf"
  }
}
```

### 5. Run the Dashboard

```bash
python run_applier.py serve
```

Open http://127.0.0.1:8000 in your browser.

## Usage

### Web Dashboard

1. Paste job URLs into the text area (one per line)
2. Click "Add to Queue"
3. Click "Run Next" to start applying
4. Watch the browser automation in action
5. Check status in the dashboard - click the + icon to expand and see step details

### CLI Commands

```bash
# Start the web server
python run_applier.py serve

# Quick apply to a single job (adds and runs immediately)
python run_applier.py apply "https://example.com/job/123"

# Add jobs to queue
python run_applier.py add "https://example.com/job/123"

# View queue status
python run_applier.py status
python run_applier.py status -v  # Verbose with job details

# Run all queued jobs
python run_applier.py run-all

# Database migration (from older JSON-based versions)
python run_applier.py migrate --check  # Check if migration needed
python run_applier.py migrate           # Run migration
```

## Configuration

### Environment Variables (.env)

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_BASE` | - | API endpoint (for local LLMs) |
| `OPENAI_API_KEY` | - | API key |
| `OPENAI_MODEL` | `gpt-4o` | Model name |
| `JOB_APPLIER_PORT` | `8000` | Dashboard port |
| `JOB_APPLIER_DB_PATH` | `./job_applier.db` | SQLite database path |
| `JOB_APPLIER_MAX_STEPS` | `100` | Max agent steps per job |
| `JOB_APPLIER_MAX_HISTORY` | `10` | Context history limit |

### Local LLM Recommendations

For best results with local models:
- Use a **vision-capable** model (e.g., `qwen3-vl-8b`, `llava`)
- Set context size to **32K+** in LM Studio
- Ensure GPU acceleration is enabled

## Project Structure

```
auto-job-applier/
├── job_applier/
│   ├── __init__.py
│   ├── agent.py           # Core automation logic with programmatic navigation
│   ├── element_handlers.py # Wrapper for browser-use built-in actions
│   ├── step_tracker.py    # Parse browser-use history into readable steps
│   ├── database.py        # SQLAlchemy models (Job, ApplicationStep, Screenshot)
│   ├── db_queue.py        # Database-backed job queue
│   ├── queue.py           # [Deprecated] JSON-based queue
│   ├── runner.py          # Queue orchestration
│   ├── migrate.py         # JSON to SQLite migration
│   └── api.py             # FastAPI server + dashboard
├── run_applier.py         # CLI entry point
├── job_applier.db         # SQLite database (auto-created)
├── instructions.md        # LLM prompt template
├── CONTEXT.md             # Development context for contributors
├── profile.json           # Your personal info (not committed)
├── profile.example.json
├── requirements.txt
└── .env                   # Configuration (not committed)
```

## How It Works

1. **Queue a Job** - Add job URLs via dashboard or CLI
2. **Programmatic Navigation** - Browser opens and navigates to job URL immediately
3. **Resume Upload** - Agent uploads resume first to leverage auto-fill
4. **Form Detection** - AI identifies remaining empty form fields
5. **Auto-Fill** - Matches fields to your profile data
6. **Step Tracking** - Each action is logged to the database
7. **Submit** - Clicks through multi-step forms until submission
8. **Record** - Saves a GIF recording, screenshots, and result to database

## Platforms Tested

- ✅ TCW (iCIMS) - 62 steps
- ✅ Alvarez & Marsal (Workday) - 170 steps
- ✅ SuccessFactors
- ✅ Greenhouse
- ⚠️ LinkedIn Easy Apply (may need manual auth)

## Troubleshooting

### "Context size exceeded" errors
Increase context in LM Studio or reduce `JOB_APPLIER_MAX_HISTORY`.

### Agent gets stuck on dropdowns
The system uses browser-use's built-in `select_dropdown` action. If issues persist, check if the dropdown is a standard `<select>` element or a custom component.

### Steps showing as "unknown" in dashboard
Ensure the step tracker is parsing actions correctly. Check `artifacts/job-<seq_id>/result.json` (or legacy `artifacts/<job-id>/result.json`) for raw action data.

### Application marked "applied" but wasn't
Check `artifacts/job-<seq_id>/result.json` (or legacy `artifacts/<job-id>/result.json`) for the actual agent output. The result includes the agent's final message.

## Development

For development context and architecture details, see [CONTEXT.md](CONTEXT.md).

## License

MIT - See browser-use for upstream license.

## Credits

Built on top of [browser-use](https://github.com/browser-use/browser-use) - the open-source browser automation library.
