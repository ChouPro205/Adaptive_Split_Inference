"""Static ELF/map/config/HEX audit; runtime MCU RAM/stack/timing remain PENDING."""
import argparse
import re
import subprocess
from pathlib import Path
from week5_common import need, sha, write_json

def hex_image(path):
    base, image, eof = 0, {}, False
    for line in Path(path).read_text(encoding='ascii').splitlines():
        need(line.startswith(':') and not eof, 'Invalid/trailing Intel HEX record')
        r = bytes.fromhex(line[1:])
        need(len(r) >= 5 and len(r) == r[0]+5 and sum(r)%256 == 0, 'HEX length/checksum invalid')
        count, low, kind, data = r[0], int.from_bytes(r[1:3], 'big'), r[3], r[4:-1]
        if kind == 0:
            for offset, byte in enumerate(data):
                address = base + low + offset
                need(0x1000 <= address < 0xe0000, f'HEX outside application: {address:#x}')
                need(address not in image, 'Overlapping HEX records')
                image[address] = byte
        elif kind in (2, 4):
            need(count == 2 and low == 0, 'Bad extended HEX address')
            base = int.from_bytes(data, 'big') << (4 if kind == 2 else 16)
        elif kind == 1:
            need(count == 0 and low == 0, 'Bad HEX EOF')
            eof = True
        elif kind in (3, 5):
            need(count == 4 and low == 0, 'Bad HEX entry point')
            entry = int.from_bytes(data, 'big') if kind == 5 else (int.from_bytes(data[:2], 'big') << 4)+int.from_bytes(data[2:], 'big')
            need(0x1000 <= entry < 0xe0000, 'HEX entry point outside application')
        else:
            raise ValueError(f'Unknown HEX record type {kind}')
    need(eof and image and min(image) == 0x1000, 'Missing EOF or invalid first application address')
    return image

def audit(build, output, toolchain):
    z = build / 'zephyr'
    config = dict(re.findall(r'^(CONFIG_\w+)=(.*)$', (z / '.config').read_text(), re.M))
    for key in ['CONFIG_FPU', 'CONFIG_INIT_STACKS', 'CONFIG_UART_USE_RUNTIME_CONFIGURE', 'CONFIG_UART_LINE_CTRL',
                'CONFIG_USB_DEVICE_STACK_NEXT', 'CONFIG_CDC_ACM_SERIAL_INITIALIZE_AT_BOOT']:
        need(config.get(key) == 'y', f'Required Dongle configuration missing: {key}')
    need(config.get('CONFIG_BOARD_TARGET') == '"nrf52840dongle/nrf52840"', 'Wrong board target')
    origin = int(config['CONFIG_FLASH_BASE_ADDRESS'], 0)+int(config['CONFIG_FLASH_LOAD_OFFSET'], 0)
    need(origin == 0x1000 and int(config['CONFIG_FLASH_LOAD_SIZE'], 0) == 0xdf000, 'Wrong DFU partition')
    need(config.get('CONFIG_USE_DT_CODE_PARTITION') != 'y' and config.get('CONFIG_BOOTLOADER_MCUBOOT') != 'y', 'Wrong bootloader configuration')
    need(int(config['CONFIG_HEAP_MEM_POOL_SIZE'], 0) == 0 and int(config['CONFIG_MAIN_STACK_SIZE'], 0) == 4096, 'Unexpected heap/stack allocation')
    linker = (z / 'linker.cmd').read_text()
    need(re.search(r'FLASH \(rx\).*ORIGIN = .*0x1000.*LENGTH = .*0xdf000', linker, re.I), 'Linker partition differs')
    dts = (z / 'zephyr.dts').read_text()
    need(re.search(r'zephyr,console\s*=\s*&board_cdc_acm_uart', dts), 'DTS console differs')
    bin_dir = toolchain / 'opt/zephyr-sdk/gnu/arm-zephyr-eabi/bin'
    outputs = {}
    for command, args in [('nm', ['-S','--size-sort']), ('size', ['-A']), ('objdump', ['-h']), ('readelf', ['-l'])]:
        outputs[command] = subprocess.check_output([str(bin_dir / f'arm-zephyr-eabi-{command}.exe'), *args, str(z / 'zephyr.elf')], text=True)
        (output / f'elf-{command}.txt').write_text(outputs[command], encoding='utf-8')
    load_segments = []
    for m in re.finditer(r'^\s*LOAD\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)', outputs['readelf'], re.M):
        offset, virtual, physical, filesz, memsz = (int(v, 16) for v in m.groups())
        if filesz:
            need(0x1000 <= physical and physical+filesz <= 0xe0000, 'ELF LOAD writes outside application')
        need((0x1000 <= virtual and virtual+memsz <= 0xe0000) or
             (0x20000000 <= virtual and virtual+memsz <= 0x20040000), 'ELF memory segment exceeds Flash/RAM')
        load_segments.append({'offset':offset,'virtual_address':virtual,'physical_address':physical,'file_bytes':filesz,'memory_bytes':memsz})
    need(load_segments, 'No ELF LOAD segments')
    map_text = (z / 'zephyr.map').read_text()
    map_regions = {name:(int(address,16),int(size,16)) for name,address,size in
                   re.findall(r'^(FLASH|RAM)\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)', map_text, re.M)}
    need(map_regions == {'FLASH':(0x1000,0xdf000),'RAM':(0x20000000,0x40000)}, 'Map memory limits differ')
    parsed = [m.groups() for m in re.finditer(r'^([0-9a-f]+)\s+([0-9a-f]+)\s+(\w)\s+(\S+)$', outputs['nm'], re.M)]
    symbols = {name:{'address':int(address,16), 'bytes':int(size,16), 'type':kind} for address,size,kind,name in parsed}
    weight_rows = [r for r in parsed if r[3].startswith('sv3_')]
    need(len(weight_rows) == 20 and len({r[3] for r in weight_rows}) == 20 and sum(int(r[1],16) for r in weight_rows) == 438612, 'Missing/duplicated FP32 weights')
    need(all(kind.lower() == 'r' and 0x1000 <= int(address,16) < 0xe0000 for address,size,kind,name in weight_rows), 'Weights must reside in const Flash')
    for name, size, kind in [('activation_a',23040,'b'), ('activation_b',23040,'b'), ('week4_inputs',28800,'r'), ('quantized',5760,'b'), ('scale_le',128,'b')]:
        matches = [r for r in parsed if r[3] == name]
        need(len(matches) == 1 and symbols[name]['bytes'] == size and symbols[name]['type'].lower() == kind, f'Buffer allocation mismatch: {name}')
    regions = {}
    for m in re.finditer(r'^\s*(FLASH|RAM):\s+([\d.]+)\s+(B|KB|MB)\s+([\d.]+)\s+(B|KB|MB)', (output / 'build.log').read_text(encoding='utf-8-sig'), re.M):
        name, used, u, limit, lu = m.groups()
        units = {'B':1,'KB':1024,'MB':1048576}
        regions[name] = {'used_bytes':int(float(used)*units[u]), 'limit_bytes':int(float(limit)*units[lu])}
        regions[name]['remaining_bytes'] = regions[name]['limit_bytes']-regions[name]['used_bytes']
    need(set(regions) == {'FLASH','RAM'} and regions['FLASH']['limit_bytes'] == 0xdf000 and regions['RAM']['limit_bytes'] == 262144,
         'Authoritative linker memory usage missing or limits differ')
    need(all(r['remaining_bytes'] >= 0 for r in regions.values()), 'Static memory overflow')
    image = hex_image(z / 'zephyr.hex')
    stacks = {name:entry for name,entry in symbols.items() if 'stack' in name and entry['type'].lower() == 'b'}
    result = {'status':'PASS', 'scope':'STATIC_BUILD_ONLY', 'board':'nrf52840dongle/nrf52840',
              'flash_origin':origin, 'flash_limit_exclusive':0xe0000, 'hex_first_address':min(image),
              'hex_end_exclusive':max(image)+1, 'hex_payload_bytes':len(image), 'regions':regions,
              'weight_arrays':{r[3]:symbols[r[3]] for r in weight_rows},
              'buffers':{n:symbols[n] for n in ('activation_a','activation_b','week4_inputs','quantized','scale_le')},
              'stack_symbols':stacks, 'configured_stacks':{k:int(v,0) for k,v in config.items() if k.endswith('STACK_SIZE')},
              'elf_load_segments':load_segments, 'map_regions':map_regions,
              'heap_pool_bytes':0, 'artifacts_sha256':{name:sha(z/name) for name in ('zephyr.elf','zephyr.hex','zephyr.map','.config','linker.cmd','zephyr.dts')},
              'runtime_ram':'PENDING','runtime_stack':'PENDING','mcu_timing':'PENDING','mcu_validation':'PENDING'}
    result['audit_source_sha256'] = sha(__file__)
    write_json(output / 'memory.json', result)
    print(f'STATIC MEMORY PASS: {regions}; HEX [{min(image):#x},{max(image)+1:#x}); weights=438612; q+scale=5888 B')

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--toolchain', type=Path, required=True)
    a = p.parse_args()
    audit(a.build, a.output, a.toolchain)
