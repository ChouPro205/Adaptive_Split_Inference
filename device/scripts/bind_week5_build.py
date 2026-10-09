"""Authenticate assets and create source-bound build identity outside Git."""
import argparse
from pathlib import Path
from week5_common import authenticate, firmware_binding, write_json

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    _, proof, history = authenticate()
    binding = firmware_binding()
    a.output.mkdir(parents=True, exist_ok=True)
    (a.output / 'week5_build.h').write_text(
        '/* Source/artifact identity only; no golden outputs. */\n' +
        f'#define WEEK5_FIRMWARE_ID "{binding["firmware_id"]}"\n' +
        f'#define WEEK5_MODEL_ANCHOR "{binding["model_anchor"]}"\n' +
        f'#define WEEK5_QUANT_ANCHOR "{binding["quant_anchor"]}"\n', encoding='ascii')
    write_json(a.output / 'binding.json', {'firmware_binding': binding, 'handoff_authentication': proof, 'accepted_r3_provenance': history})
    print(f'BUILD BINDING: {binding["firmware_id"]}')
