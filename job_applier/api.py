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

from .db_queue import JobQueue, QueuedJob, AddJobRequest
from .database import JobStatus
from .runner import JobRunner

load_dotenv()

app = FastAPI(
    title="Job Applier",
    description="Automated job application system with queue management",
    version="1.0.0",
)



# Initialize database-backed queue and runner
_queue = JobQueue()  # Uses SQLite database
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


@app.post("/queue/{job_id}/fail")
def force_fail_job(job_id: str):
    """Manually mark a job as failed (Force Stop)."""
    job = _queue.update_status(job_id, JobStatus.FAILED, error="Manually stopped by user")
    if not job:
         raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True, "job": job.model_dump_json_safe()}


@app.get("/queue/{job_id}/steps")
def get_job_steps(job_id: str):
    """Get all steps recorded for a job."""
    job = _queue.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    steps = _queue.get_steps(job_id)
    return {
        "job_id": job_id,
        "step_count": len(steps),
        "steps": steps,
    }


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


@app.post("/run/pause")
def pause_execution():
    """Pause the current job execution."""
    _runner.pause_current()
    return {"ok": True, "status": "paused"}


@app.post("/run/resume")
def resume_execution():
    """Resume the current job execution."""
    _runner.resume_current()
    return {"ok": True, "status": "running"}


@app.post("/run/stop")
def stop_execution():
    """Stop the current job execution."""
    _runner.stop_current()
    return {"ok": True, "status": "stopped"}

@app.post("/run/{job_id}")
async def run_specific_job(job_id: str, background_tasks: BackgroundTasks):
    """Run a specific job."""
    if _runner.is_running:
        raise HTTPException(status_code=400, detail="Already processing a job")
    
    # Run in background to return quickly? Or foreground?
    # User expects immediate feedback usually, but run_one uses await.
    # We'll use background task to avoid blocking API
    background_tasks.add_task(_runner.run_specific, job_id)
    return {"ok": True, "message": "Job started"}

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
        
        /* Expandable row styles */
        .expand-btn {
            background: none;
            border: none;
            color: var(--accent);
            cursor: pointer;
            font-size: 1.2rem;
            padding: 0.25rem;
            transition: transform 0.2s;
        }
        
        .expand-btn:hover {
            color: var(--success);
        }
        
        .expand-btn.expanded {
            transform: rotate(45deg);
        }
        
        .job-row {
            cursor: pointer;
        }
        
        .job-row:hover {
            background: rgba(255,255,255,0.03);
        }
        
        .detail-row {
            display: none;
        }
        
        .detail-row.visible {
            display: table-row;
        }
        
        .detail-cell {
            background: var(--bg-secondary);
            padding: 1rem !important;
        }
        
        .error-box {
            background: rgba(255, 71, 87, 0.1);
            border: 1px solid var(--error);
            border-radius: 8px;
            padding: 0.75rem;
            margin-bottom: 1rem;
            color: var(--error);
        }
        
        .error-box strong {
            display: block;
            margin-bottom: 0.5rem;
        }
        
        .steps-timeline {
            list-style: none;
            padding: 0;
            margin: 0;
        }
        
        .step-item {
            display: flex;
            align-items: flex-start;
            padding: 0.5rem 0;
            border-left: 2px solid var(--accent);
            padding-left: 1rem;
            margin-left: 0.5rem;
            position: relative;
        }
        
        .step-item::before {
            content: '';
            position: absolute;
            left: -5px;
            top: 0.75rem;
            width: 8px;
            height: 8px;
            background: var(--accent);
            border-radius: 50%;
        }
        
        .step-item.step-error {
            border-left-color: var(--error);
        }
        
        .step-item.step-error::before {
            background: var(--error);
        }
        
        .step-item.step-success {
            border-left-color: var(--success);
        }
        
        .step-item.step-success::before {
            background: var(--success);
        }
        
        .step-order {
            background: var(--bg-card);
            color: var(--text-muted);
            font-size: 0.75rem;
            padding: 0.2rem 0.4rem;
            border-radius: 4px;
            margin-right: 0.5rem;
            min-width: 24px;
            text-align: center;
        }
        
        .step-content {
            flex: 1;
        }
        
        .step-summary {
            color: var(--text);
        }
        
        .no-steps {
            color: var(--text-muted);
            font-style: italic;
        }
        
        @media (max-width: 768px) {
            body { padding: 1rem; }
            h1 { font-size: 1.8rem; }
            .stats { grid-template-columns: repeat(3, 1fr); }
            table { font-size: 0.9rem; }
        }
        
        /* New Table Styles */
        .table-container {
            overflow-x: auto;
        }
        table {
            table-layout: fixed;
            width: 100%;
        }
        .url-cell {
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        
        /* Icon Buttons */
        .btn-icon {
            background: rgba(255,255,255,0.1);
            border: none;
            cursor: pointer;
            padding: 6px;
            border-radius: 6px;
            color: var(--text);
            display: inline-flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s;
            min-width: 32px;
            height: 32px;
        }
        .btn-icon:hover { background: rgba(255,255,255,0.2); transform: translateY(-1px); }
        .btn-icon svg { width: 18px; height: 18px; fill: currentColor; }
        
        .btn-icon.run:hover { color: var(--success); background: rgba(0,255,136,0.15); }
        .btn-icon.pause:hover { color: var(--warning); background: rgba(255,170,0,0.15); }
        .btn-icon.stop:hover { color: var(--error); background: rgba(255,71,87,0.15); }
        .btn-icon.delete:hover { color: var(--error); background: rgba(255,71,87,0.15); }
        
        .actions {
            display: flex;
            gap: 4px;
            align-items: center;
        }
        
        /* Queue filters */
        .queue-controls {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
            flex-wrap: wrap;
            margin: 0.75rem 0 1rem;
        }
        
        .filter-group {
            display: flex;
            gap: 0.5rem;
            flex-wrap: wrap;
        }
        
        .filter-input,
        .filter-select {
            background: var(--bg-secondary);
            border: 1px solid rgba(255,255,255,0.1);
            color: var(--text);
            padding: 0.5rem 0.7rem;
            border-radius: 8px;
            font-size: 0.9rem;
        }
        
        .filter-input:focus,
        .filter-select:focus {
            outline: none;
            border-color: var(--accent);
        }
        
        .table-meta {
            color: var(--text-muted);
            font-size: 0.85rem;
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
            <div style="margin-top: 1rem; text-align: right;">
                 <button class="btn btn-primary btn-small" onclick="refreshQueue()">🔄 Refresh</button>
            </div>
        </div>
        
        <div class="card">
            <h2>📝 Job Queue</h2>
            <div class="queue-controls">
                <div class="filter-group">
                    <input id="job-search" class="filter-input" type="text" placeholder="Search URL, title, company" />
                    <select id="status-filter" class="filter-select">
                        <option value="all" selected>All statuses</option>
                        <option value="queued">Queued</option>
                        <option value="running">Running</option>
                        <option value="applied">Applied</option>
                        <option value="needs_review">Needs review</option>
                        <option value="failed">Failed</option>
                    </select>
                    <select id="sort-by" class="filter-select">
                        <option value="updated_at" selected>Sort: Updated</option>
                        <option value="created_at">Sort: Created</option>
                        <option value="status">Sort: Status</option>
                        <option value="seq_id">Sort: Seq</option>
                        <option value="title">Sort: Title</option>
                    </select>
                    <select id="sort-dir" class="filter-select">
                        <option value="desc" selected>Desc</option>
                        <option value="asc">Asc</option>
                    </select>
                </div>
                <div id="table-meta" class="table-meta">Showing 0 of 0</div>
            </div>
            <div class="table-container">
            <table>
                <col style="width: 40px;" />
                <col style="width: 100px;" />
                <col style="width: auto;" />
                <col style="width: 150px;" />
                <col style="width: 160px;" />
                <col style="width: 160px;" />
                <thead>
                    <tr>
                        <th></th>
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
    </div>
    
    <script>
        const API_BASE = '';
        
        const filterState = {
            search: '',
            status: 'all',
            sortBy: 'updated_at',
            sortDir: 'desc',
        };
        
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

        async function pauseJob() {
            await api('/run/pause', { method: 'POST' });
            showMessage('Job Paused. Check browser window.');
            refreshQueue();
        }

        async function resumeJob() {
            await api('/run/resume', { method: 'POST' });
            showMessage('Job Resumed.');
            refreshQueue();
        }
        
        async function runJob(jobId) {
            await api(`/run/${jobId}`, { method: 'POST' });
            showMessage('Job started');
            refreshQueue();
        }

        async function stopJob() {
             if (!confirm('Stop the current job?')) return;
             await api('/run/stop', { method: 'POST' });
             showMessage('Job stopped');
             refreshQueue();
        }

        async function forceFailJob(jobId) {
             if (!confirm('Force mark this job as FAILED? (Use if stuck)')) return;
             await api(`/queue/${jobId}/fail`, { method: 'POST' });
             showMessage('Job marked as failed');
             refreshQueue();
        }
        
        // Track which rows are expanded
        const expandedJobs = new Set();
        
        async function toggleDetails(jobId) {
            const btn = document.getElementById(`expand-btn-${jobId}`);
            const detailRow = document.getElementById(`detail-row-${jobId}`);
            
            if (expandedJobs.has(jobId)) {
                expandedJobs.delete(jobId);
                btn.classList.remove('expanded');
                detailRow.classList.remove('visible');
            } else {
                expandedJobs.add(jobId);
                btn.classList.add('expanded');
                detailRow.classList.add('visible');
                await loadSteps(jobId);
            }
        }
        
        async function loadSteps(jobId) {
            const container = document.getElementById(`steps-${jobId}`);
            if (!container) {
                return;
            }
            container.innerHTML = '<p class="no-steps">Loading steps...</p>';
            
            try {
                const res = await api(`/queue/${jobId}/steps`);
                
                if (res.steps.length === 0) {
                    container.innerHTML = '<p class="no-steps">No steps recorded yet</p>';
                    return;
                }
                
                    const stepsHtml = res.steps.map((step, i) => {
                    // Use element_description or action_type for display
                    const description = step.element_description || step.action_type || 'Unknown action';
                    const isError = step.result === 'failed' || (step.error_message && step.error_message.length > 0);
                    const isSuccess = step.result === 'success' && !isError;
                    const stepClass = isError ? 'step-error' : (isSuccess ? 'step-success' : '');
                    
                    // Build display text
                    let displayText = description;
                    if (step.error_message) {
                        displayText += ` ⚠️ ${step.error_message.substring(0, 100)}`;
                    }
                    
                    // Rich Details (Eval, Memory, Goal)
                    let detailsHtml = '';
                    if (step.evaluation || step.step_memory || step.next_goal) {
                        detailsHtml = `
                            <div style="margin-top:0.5rem; font-size:0.85rem; color:#aaa; background:rgba(0,0,0,0.2); padding:0.5rem; border-radius:4px; line-height: 1.4;">
                                ${step.evaluation ? `<div style="margin-bottom:4px;"><strong>🤔 Eval:</strong> ${step.evaluation}</div>` : ''}
                                ${step.next_goal ? `<div style="margin-bottom:4px;"><strong>🎯 Goal:</strong> ${step.next_goal}</div>` : ''}
                                ${step.step_memory ? `<div><strong>🧠 Memory:</strong> ${step.step_memory}</div>` : ''}
                            </div>
                        `;
                    }
                    
                    return `
                        <li class="step-item ${stepClass}">
                            <span class="step-order">${step.step_number !== undefined ? step.step_number : i + 1}</span>
                            <div class="step-content">
                                <span class="step-summary">${displayText}</span>
                                ${detailsHtml}
                            </div>
                        </li>
                    `;
                }).join('');
                
                container.innerHTML = `<ul class="steps-timeline">${stepsHtml}</ul>`;
            } catch (e) {
                container.innerHTML = `<p class="no-steps">Failed to load steps: ${e.message}</p>`;
            }
        }
        
        async function refreshQueue() {
            try {
                const [res, status] = await Promise.all([
                     api('/queue'),
                     api('/status')
                ]);
                
                // Add status to res for mapping
                res.is_running = status.is_running;
                res.is_paused = status.is_paused;

                // Update Controls (Global) - Optional, since we have row controls now
                // But keep them for visibility
                const controls = document.getElementById('controls-area');
                if (controls) {
                    if (status.is_running) {
                        controls.style.display = 'flex';
                        const btnPause = document.getElementById('btn-pause');
                        const btnResume = document.getElementById('btn-resume');
                        if (status.is_paused) {
                            btnPause.style.display = 'none';
                            btnResume.style.display = 'block';
                        } else {
                            btnPause.style.display = 'block';
                            btnResume.style.display = 'none';
                        }
                    } else {
                        controls.style.display = 'none';
                    }
                }
                
                // Update stats
                const stats = res.stats;
                document.querySelector('.stat.queued .stat-value').textContent = stats.queued;
                document.querySelector('.stat.running .stat-value').textContent = stats.running;
                document.querySelector('.stat.applied .stat-value').textContent = stats.applied;
                document.querySelector('.stat.needs_review .stat-value').textContent = stats.needs_review;
                document.querySelector('.stat.failed .stat-value').textContent = stats.failed;
                
                // Update table
                const tbody = document.getElementById('queue-table');
                const allJobs = res.jobs || [];
                
                // Apply search + status filter
                let jobs = allJobs.slice();
                const search = filterState.search.trim().toLowerCase();
                if (search) {
                    jobs = jobs.filter(job => {
                        const haystack = [
                            job.url,
                            job.title,
                            job.company,
                        ].filter(Boolean).join(' ').toLowerCase();
                        return haystack.includes(search);
                    });
                }
                if (filterState.status !== 'all') {
                    jobs = jobs.filter(job => job.status === filterState.status);
                }
                
                // Sort
                const dir = filterState.sortDir === 'desc' ? -1 : 1;
                const statusOrder = {
                    running: 0,
                    queued: 1,
                    needs_review: 2,
                    failed: 3,
                    applied: 4,
                };
                
                jobs.sort((a, b) => {
                    const sortBy = filterState.sortBy;
                    if (sortBy === 'updated_at' || sortBy === 'created_at') {
                        const aVal = a[sortBy] ? new Date(a[sortBy]).getTime() : 0;
                        const bVal = b[sortBy] ? new Date(b[sortBy]).getTime() : 0;
                        return (aVal - bVal) * dir;
                    }
                    if (sortBy === 'status') {
                        const aVal = statusOrder[a.status] ?? 99;
                        const bVal = statusOrder[b.status] ?? 99;
                        return (aVal - bVal) * dir;
                    }
                    if (sortBy === 'seq_id') {
                        const aHas = typeof a.seq_id === 'number';
                        const bHas = typeof b.seq_id === 'number';
                        if (aHas && bHas) return (a.seq_id - b.seq_id) * dir;
                        if (aHas) return -1;
                        if (bHas) return 1;
                        return 0;
                    }
                    if (sortBy === 'title') {
                        const aTitle = a.title;
                        const bTitle = b.title;
                        if (!aTitle && !bTitle) return 0;
                        if (!aTitle) return 1;
                        if (!bTitle) return -1;
                        return aTitle.localeCompare(bTitle) * dir;
                    }
                    return 0;
                });
                
                const meta = document.getElementById('table-meta');
                if (meta) {
                    meta.textContent = `Showing ${jobs.length} of ${allJobs.length}`;
                }
                
                if (allJobs.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted);">No jobs in queue</td></tr>';
                    return;
                }
                if (jobs.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted);">No matching jobs</td></tr>';
                    return;
                }
                
                tbody.innerHTML = jobs.map(job => {
                    const retryBtn = ['failed', 'needs_review'].includes(job.status) ? 
                        `<button class="btn btn-primary btn-small" onclick="event.stopPropagation(); retryJob('${job.id}')">Retry</button>` : '';
                    
                    const isExpanded = expandedJobs.has(job.id);
                    const expandClass = isExpanded ? 'expanded' : '';
                    const visibleClass = isExpanded ? 'visible' : '';
                    
                    // Show error/intervention reason if present
                    let errorHtml = '';
                    if (job.error || job.intervention_reason) {
                        const reason = job.intervention_reason || job.error;
                        errorHtml = `
                            <div class="error-box">
                                <strong>❌ ${job.status === 'needs_review' ? 'Needs Review' : 'Error'}:</strong>
                                ${reason}
                            </div>
                        `;
                    }
                    
                    return `
                        <tr class="job-row" onclick="toggleDetails('${job.id}')">
                            <td class="expand-cell">
                                <button class="expand-btn ${expandClass}" id="expand-btn-${job.id}" onclick="event.stopPropagation(); toggleDetails('${job.id}')">+</button>
                            </td>
                            <td><span class="status-badge status-${job.status}">${job.status}</span></td>
                            <td class="url-cell"><a href="${job.url}" target="_blank" onclick="event.stopPropagation()">${job.url}</a></td>
                            <td>${job.title || '-'}</td>
                            <td>${new Date(job.updated_at).toLocaleString()}</td>
                            <td class="actions">
                                ${['queued', 'failed', 'needs_review'].includes(job.status) && !res.is_running ? 
                                    `<button class="btn-icon run" title="Run" onclick="event.stopPropagation(); runJob('${job.id}')"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg></button>` : ''}
                                
                                ${job.status === 'running' && res.is_running ? 
                                    (res.is_paused ? 
                                        `<button class="btn-icon run" title="Resume" onclick="event.stopPropagation(); resumeJob()"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg></button>` : 
                                        `<button class="btn-icon pause" title="Pause" onclick="event.stopPropagation(); pauseJob()"><svg viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg></button>`
                                    ) : ''}
                                
                                ${job.status === 'running' && res.is_running ? 
                                     `<button class="btn-icon stop" title="Stop" onclick="event.stopPropagation(); stopJob()"><svg viewBox="0 0 24 24"><path d="M6 6h12v12H6z"/></svg></button>` : ''}

                                ${job.status === 'running' && !res.is_running ? 
                                     `<button class="btn-icon stop" title="Force Stop (Stuck)" onclick="event.stopPropagation(); forceFailJob('${job.id}')"><svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/></svg></button>` : ''}
                                
                                <button class="btn-icon delete" title="Delete" onclick="event.stopPropagation(); deleteJob('${job.id}')"><svg viewBox="0 0 24 24"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg></button>
                            </td>
                        </tr>
                        <tr class="detail-row ${visibleClass}" id="detail-row-${job.id}">
                            <td colspan="6" class="detail-cell">
                                ${errorHtml}
                                <strong>📋 Application Steps:</strong>
                                <div id="steps-${job.id}">
                                    <p class="no-steps">Click to load steps...</p>
                                </div>
                            </td>
                        </tr>
                    `;
                }).join('');
                
                // Re-load steps for expanded jobs
                for (const jobId of expandedJobs) {
                    loadSteps(jobId);
                }
            } catch (e) {
                console.error('Failed to refresh queue:', e);
                const tbody = document.getElementById('queue-table');
                if (tbody) {
                    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--error);">Error loading data: ${e.message}</td></tr>`;
                }
            }
        }
        
        // Initial load and auto-refresh
        const searchInput = document.getElementById('job-search');
        const statusFilter = document.getElementById('status-filter');
        const sortBySelect = document.getElementById('sort-by');
        const sortDirSelect = document.getElementById('sort-dir');
        
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                filterState.search = e.target.value || '';
                refreshQueue();
            });
        }
        if (statusFilter) {
            statusFilter.addEventListener('change', (e) => {
                filterState.status = e.target.value || 'all';
                refreshQueue();
            });
        }
        if (sortBySelect) {
            sortBySelect.addEventListener('change', (e) => {
                filterState.sortBy = e.target.value || 'updated_at';
                refreshQueue();
            });
        }
        if (sortDirSelect) {
            sortDirSelect.addEventListener('change', (e) => {
                filterState.sortDir = e.target.value || 'desc';
                refreshQueue();
            });
        }
        
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
