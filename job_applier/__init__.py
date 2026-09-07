"""Public package API; optional database/browser dependencies load only on demand."""
from importlib import import_module

_EXPORTS = {
    'JobApplyAgent': ('agent', 'JobApplyAgent'),
    'JobQueue': ('db_queue', 'JobQueue'),
    'JobQueueDB': ('db_queue', 'JobQueueDB'),
    'QueuedJob': ('db_queue', 'QueuedJob'),
    'AddJobRequest': ('db_queue', 'AddJobRequest'),
    'JobStatus': ('database', 'JobStatus'),
    'JobRunner': ('runner', 'JobRunner'),
    'get_db_manager': ('database', 'get_db_manager'),
    'get_session': ('database', 'get_session'),
    'migrate_from_json': ('migrate', 'migrate_from_json'),
    'check_migration_status': ('migrate', 'check_migration_status'),
    'ApplicationTracker': ('application_tracker', 'ApplicationTracker'),
}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module, symbol = _EXPORTS[name]
    value = getattr(import_module('.'+module, __name__), symbol)
    globals()[name] = value
    return value
