"""SV1 handoff 2026-10-26 log adapter; preserve the canonical peer.jsonl."""
STAGES = (('one_p0', 1), ('one_p1', 1), ('pairs_5', 10), ('pairs_100', 200))


def stage_for(index):
    for name, count in STAGES:
        if index < count:
            return name
        index -= count
    raise ValueError('SV1 session exceeds 212 requests')


def sv1_row(row):
    """Use response FP32 numbers and the sender's FP16 scale hash convention."""
    result = row['result']
    if result == 'OK' and not row.get('response_sent'):
        result = 'SEND_FAILED'
    return {
        'ev': 'request', 'request_id': row.get('request_id'),
        'rho': row.get('rho'), 'sequence': row.get('sequence'),
        'result': result, 'q_sha256': row.get('q_sha256'),
        'scale_sha256': row.get('scale_fp16_sha256'),
        'logits': row.get('logits_float'), 'label': row.get('label'),
        't_rx_ms': row.get('t_rx_ms'), 't_tx_done_ms': row.get('t_tx_done_ms'),
        'len': row.get('len'), 'response_sent': row.get('response_sent', False),
        'connection': row.get('connection'),
        'clock': 'EDGE_MONOTONIC_MS',
    }
