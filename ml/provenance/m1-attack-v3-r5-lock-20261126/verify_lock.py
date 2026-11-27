# Checks the protocol lock of attack v3 r5 without loading any array, model or MITDB file: hashes of r5, of its draft
# SHA256SUMS entries, of the SV1 evidence and of the earlier protocol versions; the key-level diff r4 -> r5 holds only
# the keys SV1 confirmed; the lock grants no run and no DS2. Negative controls must be rejected. Run from the worktree root.
import hashlib
import json
import sys
from pathlib import Path

LOCK = Path('ml/provenance/m1-attack-v3-r5-lock-20261126/m1_attack_v3_r5_protocol_lock.json')
R4 = Path('ml/configs/mitdb_m1_attack_protocol_v3_r4.json')
R4_MESSAGE_SHA = 'eafcebf68feb42a44d1981d4d1b7094f412b82610880013601e2ccf01fc84489'
ALLOWED = ('revision', 'supersedes_draft', 'changes_from_revision_4',
           'part_c_rho2_and_s0c_noise_control.action_set_rules_declared_before_run.DS2_confirmation',
           'part_c_rho2_and_s0c_noise_control.noise_generator.DS2',
           'official_DS2_privacy_round.DS2_macro_F1_rule')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def leaves(d, prefix=''):
    if not isinstance(d, dict):
        return {prefix: json.dumps(d, sort_keys=True, ensure_ascii=False)}
    out = {}
    for k, v in d.items():
        out.update(leaves(v, f'{prefix}.{k}' if prefix else k))
    return out


def changed_keys(old, new):
    a, b = leaves(old), leaves(new)
    return sorted(k for k in a.keys() | b.keys() if a.get(k) != b.get(k))


def outside(keys):
    return [k for k in keys if not any(k == a or k.startswith(a + '.') for a in ALLOWED)]


def check(lock, protocol_bytes):
    if lock.get('type') != 'M1_ATTACK_V3_R5_PROTOCOL_LOCK' or lock.get('protocol_locked') is not True:
        raise ValueError('type or protocol_locked')
    if lock.get('allow_attack_runs') is not False or lock.get('allow_DS2') is not False:
        raise ValueError('this lock must not grant runs or DS2')
    if not lock.get('approved_by') or lock.get('review_evidence_author') != 'SV1':
        raise ValueError('approval fields')
    if hashlib.sha256(protocol_bytes).hexdigest() != lock['protocol_sha256']:
        raise ValueError('protocol hash')
    if sha(lock['review_evidence_path']) != lock['review_evidence']:
        raise ValueError('review evidence hash')
    if sha(lock['draft_sums_path']) != lock['draft_sums_sha256']:
        raise ValueError('draft SHA256SUMS hash')
    for line in Path(lock['draft_sums_path']).read_text(encoding='utf-8').splitlines():
        h, p = line.split(maxsplit=1)
        if sha(p.lstrip('*')) != h:
            raise ValueError(f'draft entry differs: {p}')
    for path, h in lock['previous_versions_unchanged'].items():
        if sha(path) != h:
            raise ValueError(f'previous version changed: {path}')
    extra = outside(changed_keys(json.loads(R4.read_bytes()), json.loads(protocol_bytes)))
    if extra:
        raise ValueError(f'keys outside the confirmed diff: {extra}')


lock = json.loads(LOCK.read_text(encoding='utf-8'))
proto = Path(lock['protocol_path']).read_bytes()
check(lock, proto)
print('lock: ACCEPTED', lock['protocol_sha256'], lock['review_evidence'])
print('draft SHA256SUMS entries: MATCH; previous versions v1, v2, v3, r2, r3, r4: MATCH')
for k in changed_keys(json.loads(R4.read_bytes()), json.loads(proto)):
    print('changed r4 -> r5:', k)
p = json.loads(proto)
p_extra = dict(p, limitations=p['limitations'] + ['extra'])
b_extra = json.dumps(p_extra, ensure_ascii=False).encode('utf-8')
controls = {
    'allow_attack_runs=true': (dict(lock, allow_attack_runs=True), proto),
    'allow_DS2=true': (dict(lock, allow_DS2=True), proto),
    'protocol_sha256=r4': (dict(lock, protocol_sha256=sha(R4)), proto),
    'review_evidence=SV1 r4 message': (dict(lock, review_evidence=R4_MESSAGE_SHA), proto),
    'approved_by empty': (dict(lock, approved_by=''), proto),
    'protocol with a changed key outside the diff': (dict(lock, protocol_sha256=hashlib.sha256(b_extra).hexdigest()), b_extra),
}
for name, (bad, data) in controls.items():
    try:
        check(bad, data)
    except ValueError as e:
        print(f'negative control {name}: REJECTED ValueError: {e}')
    else:
        print(f'negative control {name}: ACCEPTED (unexpected)')
        sys.exit(1)
