"""Structured telemetry filter. Raw tool/model/mail payloads are never persisted."""
import re

PAYLOAD_FIELDS = frozenset({
    'category', 'error_type', 'tool', 'tool_name', 'status', 'page', 'evidence',
    'phase', 'helper_id', 'helper_version', 'lesson_id', 'field', 'resolution',
    'reason_code', 'provider', 'model', 'response_model', 'input_tokens', 'output_tokens', 'operation',
    'source', 'fallback_reason', 'residual_fields', 'field_key', 'field_label', 'elapsed_seconds',
    'field_attribution', 'activity', 'next_step',
    'dispatch_id','document_id','frame_id',
    'stage_id','task_id','parent_id','task_state','handler','execution','verification_result',
})
SECRET = re.compile(r'''(?ix)(?:\b(?:password|passwd|otp|(?:access_|refresh_|reset_)?token|api[_-]?key|cookie|authorization|secret)[\\"']*\s*[=:]|\bbearer\s+\S+)''')


def safe_text(value, limit=300):
    if not isinstance(value, str): return ''
    # Reject the entire secret-bearing text, including quoted/escaped JSON values.
    if SECRET.search(value): return '[REDACTED]'
    if re.search(r'(?i)(?:security|verification|authentication)[\s_-]*code\s*(?::|=|is\b)\s*[\w-]+',value):return '[REDACTED]'
    value=re.sub(r'\b\d{4,8}\b','[NUMBER]',value)
    value=re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}','[EMAIL]',value)
    return value[:limit]


def safe_payload(payload):
    if not isinstance(payload,dict): return {}
    # Values submitted in explicit secret fields are also removed from allowed fields.
    secrets=[str(v) for k,v in payload.items() if k not in PAYLOAD_FIELDS and isinstance(v,(str,int)) and str(v)]
    result={}
    for key,value in payload.items():
        if key not in PAYLOAD_FIELDS: continue
        if key in ('input_tokens','output_tokens'):
            if isinstance(value,int) and not isinstance(value,bool) and value>=0: result[key]=value
            continue
        if key == 'residual_fields' and isinstance(value, list):
            result[key] = [safe_text(x)[:60] for x in value if isinstance(x, str)]
            continue
        if key == 'elapsed_seconds' and isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
            result[key] = round(float(value), 4)
            continue
        if not isinstance(value,str): continue
        for secret in secrets: value=value.replace(secret,'[REDACTED]')
        # Correlation IDs are structured identifiers, not prose or mailbox codes.
        # Masking numeric UUID segments breaks linkage between the captured
        # browser dispatch and its event. Other strings still use redaction.
        if key in ('dispatch_id','document_id','frame_id') and re.fullmatch(
                r'(?:[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}|[0-9a-fA-F]{16,64}|root)',value):
            result[key]=value
            continue
        result[key]=safe_text(value)
    return result


def reject_secrets(value):
    """Profile/config snapshots accept facts and references, not credential material."""
    from .managed_shared import ProtocolError
    if isinstance(value, dict):
        for key, item in value.items():
            normalized=re.sub(r'[^a-z]', '', str(key).lower())
            if normalized.endswith(('token','privatekey')) or normalized in ('token','authorization','credentials','rawmessages','mailbody') or any(term in normalized for term in ('password','passwd','cookie','apikey','secret','accesstoken','refreshtoken','otp','rawreasoning')):
                raise ProtocolError('secret_in_snapshot')
            reject_secrets(item)
    elif isinstance(value, list):
        for item in value: reject_secrets(item)
    elif isinstance(value, str) and SECRET.search(value):
        raise ProtocolError('secret_in_snapshot')
