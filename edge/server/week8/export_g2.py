#!/usr/bin/env python3
"""Extract the final 200 requests from a sealed 212-request SV1 session."""
import argparse
import json
from pathlib import Path
from common import file_sha, save, seal
from summarize import verify
from sv1_log import stage_for


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--session', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    verify(a.session)
    rows = [json.loads(x) for x in (a.session/'peer.jsonl').read_text().splitlines()]
    if len(rows) != 212:
        raise ValueError('Need all 212 requests; preserve partial session for review')
    for i, row in enumerate(rows):
        if (row.get('stage') != stage_for(i) or row.get('result') != 'OK'
                or not row.get('response_sent') or row.get('cache_hit')
                or row.get('t_tx_done_ms') is None):
            raise ValueError('Invalid/error/retry request at index '+str(i))
    if len({r.get('connection') for r in rows}) != 1:
        raise ValueError('Connection changed; SV1 requested a single continuous connection')
    if [r['rho'] for r in rows[:2]] != ['P0', 'P1']:
        raise ValueError('Expected ONE 0 P0 then ONE 0 P1')
    a.output.mkdir(parents=True, exist_ok=False)
    (a.output/'peer.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows[12:]))
    save(a.output/'run.json', {
        'scope': 'FINAL_200_FROM_SV1_212_REQUEST_SESSION_NOT_G2_ACCEPTANCE',
        'session_inventory_sha256': file_sha(a.session/'sha256sum_results.txt'),
        'session': str(a.session), 'rows_selected': '12..211 (zero-based)',
    })
    seal(a.output)
    print('EXPORTED_FINAL_200_REVIEW_REQUIRED')


if __name__ == '__main__':
    main()
