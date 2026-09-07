"""Small shared protocol primitives; no runtime initialization."""
import json
import uuid
from functools import wraps


class ProtocolError(ValueError):
    def __init__(self, code, detail=''):
        self.code = code
        super().__init__(code + (': ' + detail if detail else ''))


def legacy_writer(method):
    """Legacy entrypoints cannot bypass managed ownership or overwrite its history."""
    @wraps(method)
    def guarded(self, *args, **kwargs):
        manager = getattr(self, 'db_manager', None) or getattr(self, 'db', None)
        manager.require_legacy()
        return method(self, *args, **kwargs)
    return guarded


def uid():
    return str(uuid.uuid4())


def dumps(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
