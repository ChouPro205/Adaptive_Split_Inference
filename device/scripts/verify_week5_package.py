"""Read-only preflight of the exact prepared ZIP/ELF/HEX and current source."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
from week5_common import ROOT, authenticate, firmware_binding, source_hashes, sha, need
from inspect_week5_memory import hex_image

def package_metadata(directory):
    directory = Path(directory).resolve()
    z = directory / 'build/zephyr'
    archive_path = directory / 'adaptive_split_week5.zip'
    image = hex_image(z / 'zephyr.hex')
    with zipfile.ZipFile(archive_path) as archive:
        need(archive.testzip() is None, 'ZIP CRC invalid')
        names = archive.namelist()
        need(len(names) == len(set(names)), 'ZIP duplicate member')
        manifest = json.loads(archive.read('manifest.json'))
        need(set(manifest) == {'manifest'} and set(manifest['manifest']) == {'application'}, 'DFU must be application only')
        app = manifest['manifest']['application']
        need(set(app) == {'bin_file','dat_file'}, 'Unexpected DFU application metadata')
        need(set(names) == {'manifest.json', app['bin_file'], app['dat_file']}, 'Unexpected DFU members')
        binary = archive.read(app['bin_file'])
        init = archive.read(app['dat_file'])
        need(binary == (z / 'zephyr.bin').read_bytes(), 'DFU application differs from built binary')
        need(len(binary) == max(image)-0x1000+1 and len(init) > 0, 'DFU application length/init invalid')
        need(all(binary[address-0x1000] == byte for address,byte in image.items()), 'HEX differs from packaged application')
        need(all(binary[i] == 0xff for i in range(len(binary)) if i+0x1000 not in image), 'Unexpected data in HEX gaps')
        application = {'bin_file':app['bin_file'], 'dat_file':app['dat_file'], 'bytes':len(binary),
                       'sha256':hashlib.sha256(binary).hexdigest(), 'init_sha256':hashlib.sha256(init).hexdigest()}
    artifacts = {name:{'path':str(path), 'sha256':sha(path), 'bytes':path.stat().st_size} for name,path in
                 [('elf',z/'zephyr.elf'),('hex',z/'zephyr.hex'),('bin',z/'zephyr.bin'),('zip',archive_path),
                  ('map',z/'zephyr.map'),('config',z/'.config'),('linker',z/'linker.cmd'),('devicetree',z/'zephyr.dts')]}
    return {'artifacts':artifacts,'application':application}

def verify_artifacts(preparation):
    need(preparation['firmware_binding'] == firmware_binding(), 'Current firmware source differs from build')
    for name, expected in preparation['source_sha256'].items():
        need(sha(ROOT / name) == expected, f'Prepared source changed: {name}')
    for name, entry in preparation['artifacts'].items():
        path = Path(entry['path'])
        need(path.stat().st_size == entry['bytes'] and sha(path) == entry['sha256'], f'Prepared artifact changed: {name}')
    metadata = package_metadata(Path(preparation['artifacts']['zip']['path']).parent)
    need(metadata['application'] == preparation['application'], 'DFU application changed')
    for p, expected in preparation.get('build_metadata_sha256', {}).items():
        need(sha(p) == expected, f'Build metadata changed: {p}')
    return preparation

def verify_package(path):
    authenticate()
    preparation = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    need(preparation['status'] == 'READY_TO_FLASH' and preparation['scope'] == 'SV1_WEEK5_PREPARATION', 'Preparation gates incomplete')
    need(preparation['flash'] == 'NOT_RUN' and preparation['mcu_validation'] == 'PENDING', 'Wrong preparation stage')
    return verify_artifacts(preparation)

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--preparation', type=Path, required=True)
    a = p.parse_args()
    r = verify_package(a.preparation)
    print(f'PACKAGE PREFLIGHT PASS: {r["artifacts"]["zip"]["path"]}; SHA256={r["artifacts"]["zip"]["sha256"]}')
