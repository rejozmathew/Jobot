"""Convert a saved Job Harvester JSON/CSV export to discovery leads, offline."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import tempfile

from .managed_identity import canonical_url
from .managed_redaction import reject_secrets
from .managed_shared import ProtocolError


def convert_export(payload):
    rows = payload.get('items') if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError('Expected a JSON array or an object containing items')
    leads, errors, seen = [], [], set()
    duplicates = 0
    for index, row in enumerate(rows):
        try:
            if not isinstance(row, dict):
                raise ValueError('Invalid row')
            options = row.get('serpapi_apply_options') or []
            if isinstance(options, str):
                options = json.loads(options)
            if not isinstance(options, list):
                raise ValueError('Invalid apply options')
            urls = []
            for value in [row.get('url'), row.get('serpapi_share_link'),
                          *(opt.get('link') for opt in options if isinstance(opt, dict))]:
                if not value:
                    continue
                try:
                    normalized = canonical_url(value)
                except (ProtocolError, TypeError, ValueError, AttributeError):
                    continue
                if normalized not in urls:
                    urls.append(normalized)
            if not urls:
                raise ValueError('No usable URL')
            provider = row.get('source') or 'unknown'
            reference = row.get('id') or row.get('serpapi_job_id') or hashlib.sha256(urls[0].encode()).hexdigest()
            if not isinstance(provider, str) or not isinstance(reference, str):
                raise ValueError('Invalid source identity')
            lead = {'source_type': 'job_harvester:' + provider, 'source_id': reference,
                    'candidate_urls': urls}
            for source, target in [('company', 'company'), ('title', 'title'), ('location', 'location'),
                                   ('created_at', 'harvester_added_at'), ('posted_at', 'reported_posted_at'),
                                   ('run_id', 'harvester_run_id'), ('status', 'harvester_status')]:
                value = row.get(source)
                if isinstance(value, str) and value.strip():
                    lead[target] = value.strip()
            reject_secrets(lead)
            key = (lead['source_type'], reference)
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            leads.append(lead)
        except (ValueError, TypeError, ProtocolError):
            errors.append({'index': index, 'error': 'invalid_harvester_record'})
    return {'kind': 'unverified_discovery_leads', 'received': len(rows),
            'duplicate_records': duplicates, 'leads': leads, 'errors': errors}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, help='Saved /latest JSON response or Harvester CSV export')
    parser.add_argument('--output', required=True, help='Private lead file for the discovery executor')
    args = parser.parse_args(argv)
    temporary = None
    try:
        source = Path(args.input)
        with source.open(encoding='utf-8-sig', newline='') as stream:
            payload = list(csv.DictReader(stream)) if source.suffix.lower() == '.csv' else json.load(stream)
        result = convert_export(payload)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=output.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(result, stream, ensure_ascii=False, indent=2)
        temporary.replace(output)
        print(json.dumps({'leads': len(result['leads']), 'errors': len(result['errors']),
                          'duplicate_records': result['duplicate_records']}))
        return 1 if result['errors'] else 0
    except (OSError, ValueError, TypeError):
        print(json.dumps({'error': 'harvester_export_unavailable'}))
        return 2
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


if __name__ == '__main__':
    raise SystemExit(main())
