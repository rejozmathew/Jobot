# Auto Job Applier

An automated job application agent powered by [browser-use](https://github.com/browser-use/browser-use). Uses AI (local LLMs or OpenAI) to navigate job application forms and submit applications automatically.

## Features

- 🌐 **Web Dashboard** - Manage job queue at `localhost:8000`
- 🤖 **AI-Powered** - Uses vision LLMs to understand and fill forms
- 📋 **Queue System** - Add jobs, track status (queued → running → applied/failed)
- 🎥 **Recordings** - Generates GIF recordings of each application attempt
- ⚙️ **Configurable** - Works with local LLMs (LM Studio) or OpenAI
- 🔒 **Profile-Based** - Store your info once, use for all applications

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
5. Check status in the dashboard

### CLI Commands

```bash
# Start the web server
python run_applier.py serve

# Add jobs to queue
python run_applier.py add "https://example.com/job/123"

# Run next job in queue
python run_applier.py run

# Run all queued jobs
python run_applier.py run --all
```

## Configuration

### Environment Variables (.env)

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_BASE` | - | API endpoint (for local LLMs) |
| `OPENAI_API_KEY` | - | API key |
| `OPENAI_MODEL` | `gpt-4o` | Model name |
| `JOB_APPLIER_PORT` | `8000` | Dashboard port |
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
│   ├── agent.py      # Core automation logic
│   ├── queue.py      # Job queue management
│   ├── runner.py     # Queue orchestration
│   └── api.py        # FastAPI server + dashboard
├── run_applier.py    # CLI entry point
├── instructions.md   # LLM prompt template
├── profile.json      # Your personal info (not committed)
├── profile.example.json
├── requirements.txt
└── .env              # Configuration (not committed)
```

## How It Works

1. **Queue a Job** - Add job URLs via dashboard or CLI
2. **Agent Starts** - browser-use opens a browser and navigates to the job
3. **Form Detection** - AI identifies form fields and buttons
4. **Auto-Fill** - Matches fields to your profile data
5. **Submit** - Clicks through multi-step forms until submission
6. **Record** - Saves a GIF recording and result JSON

## Platforms Tested

- ✅ Alvarez & Marsal (Workday)
- ✅ SuccessFactors
- ✅ Greenhouse
- ⚠️ LinkedIn Easy Apply (may need manual auth)

## Troubleshooting

### "Context size exceeded" errors
Increase context in LM Studio or reduce `JOB_APPLIER_MAX_HISTORY`.

### Agent gets stuck on dropdowns
The instructions include specific dropdown handling. Check `instructions.md`.

### Application marked "applied" but wasn't
Check `artifacts/<job-id>/result.json` for the actual agent output.

## License

MIT - See browser-use for upstream license.

## Credits

Built on top of [browser-use](https://github.com/browser-use/browser-use) - the open-source browser automation library.
