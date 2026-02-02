"""FastAPI Application - REST API and Web UI for job application management."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .queue import JobQueue, JobStatus, AddJobRequest, QueuedJob
from .runner import JobRunner

load_dotenv()

app = FastAPI(
    title="Job Applier",
    description="Automated job application system with queue management",
    version="1.0.0",
)



# Initialize queue and runner
_queue = JobQueue(os.getenv("JOB_APPLIER_QUEUE_PATH", "./job_queue.json"))
_runner = JobRunner()

# Track background task
_background_task_running = False


# ----- Request/Response Models -----

class AddUrlsRequest(BaseModel):
    """Request to add multiple URLs."""
    urls: List[str]


class BulkAddResponse(BaseModel):
    """Response for bulk add operation."""
    added: int
    jobs: List[dict]


class RunResponse(BaseModel):
    """Response for run operation."""
    message: str
    job: Optional[dict] = None


# ----- API Endpoints -----

@app.get("/health")
def health():
    """Health check endpoint."""
    return {"ok": True, "service": "job-applier"}


@app.get("/queue")
def list_queue():
    """List all jobs in the queue."""
    jobs = _queue.list_all()
    return {
        "count": len(jobs),
        "jobs": [job.model_dump_json_safe() for job in jobs],
        "stats": _queue.get_stats(),
    }


@app.post("/queue")
def add_to_queue(request: AddJobRequest):
    """Add a single job to the queue."""
    job = _queue.add(request)
    return {"ok": True, "job": job.model_dump_json_safe()}


@app.post("/queue/bulk")
def add_bulk_to_queue(request: AddUrlsRequest):
    """Add multiple URLs to the queue."""
    jobs = _queue.add_urls(request.urls)
    return BulkAddResponse(
        added=len(jobs),
        jobs=[job.model_dump_json_safe() for job in jobs],
    )


@app.get("/queue/{job_id}")
def get_job(job_id: str):
    """Get details of a specific job."""
    job = _queue.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job": job.model_dump_json_safe()}


@app.delete("/queue/{job_id}")
def delete_job(job_id: str):
    """Remove a job from the queue."""
    if _queue.delete(job_id):
        return {"ok": True, "deleted": job_id}
    raise HTTPException(status_code=404, detail="Job not found")


@app.post("/queue/{job_id}/retry")
def retry_job(job_id: str):
    """Retry a failed or needs_review job."""
    job = _queue.retry(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True, "job": job.model_dump_json_safe()}


@app.get("/status")
def get_status():
    """Get current processing status."""
    return _runner.get_status()


@app.post("/run")
async def run_one(background_tasks: BackgroundTasks):
    """Process the next job in the queue."""
    global _background_task_running
    
    if _runner.is_running:
        return RunResponse(
            message="Already processing a job",
            job=_runner.current_job.model_dump_json_safe() if _runner.current_job else None,
        )
    
    # Run in foreground for immediate feedback
    result = await _runner.run_one()
    
    if result is None:
        return RunResponse(message="Queue is empty", job=None)
    
    return RunResponse(message=f"Job completed: {result.get('status')}", job=result)


@app.post("/run/all")
async def run_all(background_tasks: BackgroundTasks):
    """Process all jobs in the queue (runs in background after first job)."""
    global _background_task_running
    
    if _runner.is_running or _background_task_running:
        return {"message": "Already processing jobs", "status": _runner.get_status()}
    
    # Run first job immediately
    result = await _runner.run_one()
    
    if result is None:
        return {"message": "Queue is empty", "results": []}
    
    # Queue remaining jobs in background
    stats = _queue.get_stats()
    remaining = stats.get("queued", 0)
    
    if remaining > 0:
        _background_task_running = True
        
        async def process_remaining():
            global _background_task_running
            try:
                await _runner.run_all()
            finally:
                _background_task_running = False
        
        background_tasks.add_task(lambda: asyncio.run(process_remaining()))
    
    return {
        "message": f"Started processing. First job: {result.get('status')}. {remaining} remaining.",
        "first_result": result,
        "remaining": remaining,
    }


# ----- Web UI -----

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Job Applier</title>
    <style>
        :root {
            --bg-primary: #0f0f23;
            --bg-secondary: #1a1a2e;
            --bg-card: #16213e;
            --accent: #00d4ff;
            --accent-hover: #00a8cc;
            --success: #00ff88;
            --warning: #ffaa00;
            --error: #ff4757;
            --text: #e8e8e8;
            --text-muted: #a0a0a0;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: var(--bg-primary);
            color: var(--text);
            min-height: 100vh;
            padding: 2rem;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        
        header {
            text-align: center;
            margin-bottom: 2rem;
        }
        
        h1 {
            font-size: 2.5rem;
            background: linear-gradient(135deg, var(--accent), var(--success));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }
        
        .subtitle {
            color: var(--text-muted);
        }
        
        .card {
            background: var(--bg-card);
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            border: 1px solid rgba(255,255,255,0.1);
        }
        
        .card h2 {
            margin-bottom: 1rem;
            font-size: 1.2rem;
            color: var(--accent);
        }
        
        .form-group {
            margin-bottom: 1rem;
        }
        
        label {
            display: block;
            margin-bottom: 0.5rem;
            color: var(--text-muted);
        }
        
        textarea, input[type="text"] {
            width: 100%;
            padding: 0.75rem;
            background: var(--bg-secondary);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 8px;
            color: var(--text);
            font-size: 1rem;
            resize: vertical;
        }
        
        textarea:focus, input:focus {
            outline: none;
            border-color: var(--accent);
        }
        
        .btn {
            padding: 0.75rem 1.5rem;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1rem;
            font-weight: 600;
            transition: all 0.2s;
        }
        
        .btn-primary {
            background: linear-gradient(135deg, var(--accent), var(--accent-hover));
            color: var(--bg-primary);
        }
        
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 20px rgba(0, 212, 255, 0.3);
        }
        
        .btn-success {
            background: var(--success);
            color: var(--bg-primary);
        }
        
        .btn-danger {
            background: var(--error);
            color: white;
        }
        
        .btn-small {
            padding: 0.4rem 0.8rem;
            font-size: 0.85rem;
        }
        
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
            gap: 1rem;
            margin-bottom: 1rem;
        }
        
        .stat {
            text-align: center;
            padding: 1rem;
            background: var(--bg-secondary);
            border-radius: 8px;
        }
        
        .stat-value {
            font-size: 2rem;
            font-weight: bold;
        }
        
        .stat-label {
            color: var(--text-muted);
            font-size: 0.85rem;
        }
        
        .stat.queued .stat-value { color: var(--accent); }
        .stat.running .stat-value { color: var(--warning); }
        .stat.applied .stat-value { color: var(--success); }
        .stat.needs_review .stat-value { color: var(--warning); }
        .stat.failed .stat-value { color: var(--error); }
        
        table {
            width: 100%;
            border-collapse: collapse;
        }
        
        th, td {
            padding: 0.75rem;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        
        th {
            color: var(--text-muted);
            font-weight: 500;
        }
        
        .status-badge {
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-size: 0.8rem;
            font-weight: 600;
        }
        
        .status-queued { background: var(--accent); color: var(--bg-primary); }
        .status-running { background: var(--warning); color: var(--bg-primary); }
        .status-applied { background: var(--success); color: var(--bg-primary); }
        .status-needs_review { background: var(--warning); color: var(--bg-primary); }
        .status-failed { background: var(--error); color: white; }
        
        .actions {
            display: flex;
            gap: 0.5rem;
        }
        
        .url-cell {
            max-width: 300px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        
        .url-cell a {
            color: var(--accent);
            text-decoration: none;
        }
        
        .url-cell a:hover {
            text-decoration: underline;
        }
        
        .message {
            padding: 1rem;
            border-radius: 8px;
            margin-bottom: 1rem;
            display: none;
        }
        
        .message.success {
            background: rgba(0, 255, 136, 0.1);
            border: 1px solid var(--success);
            color: var(--success);
        }
        
        .message.error {
            background: rgba(255, 71, 87, 0.1);
            border: 1px solid var(--error);
            color: var(--error);
        }
        
        .button-group {
            display: flex;
            gap: 0.5rem;
            flex-wrap: wrap;
        }
        
        .loading {
            opacity: 0.6;
            pointer-events: none;
        }
        
        @media (max-width: 768px) {
            body { padding: 1rem; }
            h1 { font-size: 1.8rem; }
            .stats { grid-template-columns: repeat(3, 1fr); }
            table { font-size: 0.9rem; }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🚀 Job Applier</h1>
            <p class="subtitle">Automated job application system</p>
        </header>
        
        <div id="message" class="message"></div>
        
        <div class="card">
            <h2>📋 Add Jobs to Queue</h2>
            <div class="form-group">
                <label for="urls">Job URLs (one per line)</label>
                <textarea id="urls" rows="4" placeholder="https://example.com/job/123&#10;https://another.com/apply/456"></textarea>
            </div>
            <div class="button-group">
                <button class="btn btn-primary" onclick="addJobs()">Add to Queue</button>
                <button class="btn btn-success" onclick="runNext()">▶ Run Next</button>
                <button class="btn btn-success" onclick="runAll()">▶▶ Run All</button>
            </div>
        </div>
        
        <div class="card">
            <h2>📊 Queue Status</h2>
            <div class="stats" id="stats">
                <div class="stat queued"><div class="stat-value">-</div><div class="stat-label">Queued</div></div>
                <div class="stat running"><div class="stat-value">-</div><div class="stat-label">Running</div></div>
                <div class="stat applied"><div class="stat-value">-</div><div class="stat-label">Applied</div></div>
                <div class="stat needs_review"><div class="stat-value">-</div><div class="stat-label">Review</div></div>
                <div class="stat failed"><div class="stat-value">-</div><div class="stat-label">Failed</div></div>
            </div>
            <button class="btn btn-primary btn-small" onclick="refreshQueue()">🔄 Refresh</button>
        </div>
        
        <div class="card">
            <h2>📝 Job Queue</h2>
            <table>
                <thead>
                    <tr>
                        <th>Status</th>
                        <th>URL</th>
                        <th>Title</th>
                        <th>Updated</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody id="queue-table">
                    <tr><td colspan="6" style="text-align:center;color:var(--text-muted);">Loading...</td></tr>
                </tbody>
            </table>
        </div>
    </div>
    
    <script>
        const API_BASE = '';
        
        function showMessage(text, type = 'success') {
            const el = document.getElementById('message');
            el.textContent = text;
            el.className = 'message ' + type;
            el.style.display = 'block';
            setTimeout(() => { el.style.display = 'none'; }, 5000);
        }
        
        async function api(endpoint, options = {}) {
            try {
                const res = await fetch(API_BASE + endpoint, {
                    headers: { 'Content-Type': 'application/json' },
                    ...options,
                });
                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.detail || 'Request failed');
                }
                return await res.json();
            } catch (e) {
                showMessage(e.message, 'error');
                throw e;
            }
        }
        
        async function addJobs() {
            const textarea = document.getElementById('urls');
            const urls = textarea.value.split(/\\n/).map(u => u.trim()).filter(u => u);
            if (urls.length === 0) {
                showMessage('Please enter at least one URL', 'error');
                return;
            }
            
            const res = await api('/queue/bulk', {
                method: 'POST',
                body: JSON.stringify({ urls }),
            });
            
            showMessage(`Added ${res.added} job(s) to queue`);
            textarea.value = '';
            refreshQueue();
        }
        
        async function runNext() {
            showMessage('Starting job...', 'success');
            const res = await api('/run', { method: 'POST' });
            showMessage(res.message);
            refreshQueue();
        }
        
        async function runAll() {
            showMessage('Starting all jobs...', 'success');
            const res = await api('/run/all', { method: 'POST' });
            showMessage(res.message);
            refreshQueue();
        }
        
        async function retryJob(jobId) {
            await api(`/queue/${jobId}/retry`, { method: 'POST' });
            showMessage('Job queued for retry');
            refreshQueue();
        }
        
        async function deleteJob(jobId) {
            if (!confirm('Delete this job?')) return;
            await api(`/queue/${jobId}`, { method: 'DELETE' });
            showMessage('Job deleted');
            refreshQueue();
        }
        
        async function refreshQueue() {
            try {
                const res = await api('/queue');
                
                // Update stats
                const stats = res.stats;
                document.querySelector('.stat.queued .stat-value').textContent = stats.queued;
                document.querySelector('.stat.running .stat-value').textContent = stats.running;
                document.querySelector('.stat.applied .stat-value').textContent = stats.applied;
                document.querySelector('.stat.needs_review .stat-value').textContent = stats.needs_review;
                document.querySelector('.stat.failed .stat-value').textContent = stats.failed;
                
                // Update table
                const tbody = document.getElementById('queue-table');
                if (res.jobs.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-muted);">No jobs in queue</td></tr>';
                    return;
                }
                
                tbody.innerHTML = res.jobs.map(job => {
                    const retryBtn = ['failed', 'needs_review'].includes(job.status) ? 
                        `<button class="btn btn-primary btn-small" onclick="retryJob('${job.id}')">Retry</button>` : '';
                    
                    return `
                    <tr>
                        <td><span class="status-badge status-${job.status}">${job.status}</span></td>
                        <td class="url-cell"><a href="${job.url}" target="_blank">${job.url}</a></td>
                        <td>${job.title || '-'}</td>
                        <td>${new Date(job.updated_at).toLocaleString()}</td>
                        <td class="actions">
                            ${retryBtn}
                            <button class="btn btn-danger btn-small" onclick="deleteJob('${job.id}')">Delete</button>
                        </td>
                    </tr>
                `}).join('');
            } catch (e) {
                console.error('Failed to refresh queue:', e);
                const tbody = document.getElementById('queue-table');
                if (tbody) {
                    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:var(--error);">Error loading data: ${e.message}</td></tr>`;
                }
            }
        }
        
        // Initial load and auto-refresh
        refreshQueue();
        setInterval(refreshQueue, 5000);
    </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def web_ui():
    """Serve the web UI."""
    return HTML_TEMPLATE


# ----- Debug Endpoints -----

@app.get("/queue/{job_id}/debug")
def debug_job(job_id: str):
    """Get debug information for a job including artifacts."""
    job = _queue.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    artifacts_dir = Path(os.getenv("JOB_APPLIER_ARTIFACTS_DIR", "./artifacts")) / job_id
    files = []
    if artifacts_dir.exists():
        files = [p.name for p in artifacts_dir.iterdir() if p.is_file()]
    
    return {
        "job": job.model_dump_json_safe(),
        "artifacts_dir": str(artifacts_dir),
        "files": sorted(files),
    }
