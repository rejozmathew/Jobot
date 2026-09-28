"""Retain verified main-document history across short-lived helper connections."""
import asyncio
import json
from urllib.parse import urlsplit

from .cdp_client import _public_destination
from .managed_identity import canonical_url, explicit_job_conflict, job_key
from .managed_sessions import local_session
from .managed_shared import ProtocolError, dumps


def _owned(service, db, ownership, target_id):
    attempt = service._owner(db, **ownership)
    session = local_session(db, attempt['id'])
    if not session or session['target_id'] != target_id:
        return None
    target = db.execute("SELECT * FROM owned_targets WHERE attempt_id=? AND target_id=? AND state='open'",
                        (attempt['id'], target_id)).fetchone()
    if not target:
        return None
    metadata = json.loads(session['metadata_json'])
    binding = {'session_id': session['id'], 'attempt_id': attempt['id'], 'fence': attempt['fence'],
               'target_id': target_id,
               'browser_id': (metadata.get('browser_attachment') or {}).get('browser_id')}
    identity_url = metadata.get('application_identity_url') or service._get(db, 'jobs', attempt['job_id'])['url']
    return session, target, metadata, binding, identity_url


async def reconcile_history(page, service, ownership, target_id, live_url, *, verified):
    """Add continuity evidence; absence of it leaves ordinary recovery unchanged.

    CDP history is top-level browser evidence, not a network redirect chain.
    An entry ID survives replaceState even when its verified URL is overwritten.
    Cross-origin transitions continue to use the existing Apply mechanism.
    """
    connection = getattr(page, '_session', None)
    if not connection or not _public_destination(live_url):
        return False
    with service.tx() as db:
        state = _owned(service, db, ownership, target_id)
    if not state:
        return False
    _, initial_target, metadata, binding, identity_url = state
    anchor = metadata.get('route_history_anchor') or {}
    try:
        history = await connection.call('Page.getNavigationHistory')
        entries = history.get('entries', [])
        index = history.get('currentIndex')
        if type(index) is not int or not 0 <= index < len(entries):
            return False
        entry = entries[index]
        if type(entry.get('id')) is not int or canonical_url(entry.get('url')) != canonical_url(live_url):
            return False
        # A document change between the history and URL reads is retried by the
        # next ordinary observation, never interpreted as evidence for this URL.
        if canonical_url(await page.evaluate('location.href')) != canonical_url(live_url):
            return False
    except (RuntimeError, asyncio.TimeoutError, ProtocolError, TypeError, ValueError):
        return False

    value = dict(binding, entry_id=entry['id'], source_url=canonical_url(live_url))
    if not verified:
        if not isinstance(anchor, dict) or any(anchor.get(k) != v for k, v in binding.items()):
            return False
        source = anchor.get('source_url')
        positions = [i for i, item in enumerate(entries[:index + 1]) if item.get('id') == anchor.get('entry_id')]
        if len(positions) != 1 or not _public_destination(source):
            return False
        segment = [item.get('url') for item in entries[positions[0]:index + 1]]
        origin = urlsplit(source)[:2]
        if any(not _public_destination(url) or urlsplit(url)[:2] != origin or
               any(explicit_job_conflict(base, url) for base in (source, identity_url)) for url in segment):
            return False
        try:
            handoff = service.handoff_target(**ownership, current_target_id=target_id, new_target_id=target_id,
                url=live_url, source_url=source,
                _history_proof={'expected': anchor, 'replacement': value,
                                'target_identity': initial_target['identity_key'], 'identity_url': identity_url},
                evidence='Observed same-origin main-document history from a retained verified entry')
        except ProtocolError as exc:
            if exc.code == 'target_job_mismatch': return False
            raise
        return handoff is not None

    with service.tx() as db:
        current = _owned(service, db, ownership, target_id)
        if current and current[3] == binding and (current[2].get('route_history_anchor') or {}) == anchor:
            current_session, target, current_meta, _, _ = current
            # For verified child routes the existing matcher can authorize a
            # source whose exact key is not yet the target's stored key.
            from .managed_identity import is_same_application_scope
            if (target['identity_key'] == job_key(live_url) or
                    is_same_application_scope(target['url'], live_url)):
                if current_meta.get('route_history_anchor') != value:
                    current_meta['route_history_anchor'] = value
                    db.execute('UPDATE application_sessions SET metadata_json=? WHERE id=?',
                               (dumps(current_meta), current_session['id']))
    return False
