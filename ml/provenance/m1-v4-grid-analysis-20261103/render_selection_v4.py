"""Render the M1 v4 grid selection tables and checkpoint hash list from analyze + cross-check JSON; reads no slot files."""
import argparse
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
RUN='ml/data/runs/mitdb-baseline-v4-20261103'
MODES={'weighted_ce':'weighted CE','balanced_sampler':'K-balanced sampler'}


def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))


def r4(x):return Decimal(str(x)).quantize(Decimal('0.0001'),rounding=ROUND_HALF_UP)


def vn(x,d=4):return f'{x:.{d}f}'.replace('.',',')


def g(v):return 'đạt' if v else '**không**'


def render():
    an=read(HERE/'logs/analyze-normal.stdout.json');cc=read(HERE/'crosscheck-normal.json')
    order={c['id']:c for c in read(ROOT/'ml/configs/mitdb_m1_baseline_protocol_v4.json')['baseline']['configuration_order']}
    sel=an['selected'];slots={(s['configuration'],s['seed']):s for s in cc['slots']}
    out=['## Bảng 1. Sáu cấu hình (mean và SD trên 3 seed, SD mẫu ddof=1)','',
         '| Cấu hình | Chế độ | cap | lr | Mean macro-F1 (thô) | Mean làm tròn 4 | SD ddof=1 | Seed triển khai | Gate N / V / S tại seed triển khai |',
         '|---|---|---:|---:|---:|---:|---:|---:|---|']
    for c in an['configurations']:
        o=order[c['configuration']];b=next(s for s in c['seeds'] if s['seed']==c['best_seed'])['gates']
        name=f"**{c['configuration']}** (chọn)" if c['configuration']==sel['configuration'] else c['configuration']
        out.append(f"| {name} | {MODES[o['mode']]} | {o['cap'] if o['cap'] is not None else '—'} | {vn(o['lr'],4 if o['lr']<.001 else 3)} | "
                   f"{vn(c['mean_macro_f1'],6)} | {vn(float(r4(c['mean_macro_f1'])))} | {vn(c['sd_sample'],6)} | {c['best_seed']} | "
                   f"{g(b['N'])} / {g(b['V'])} / {g(b['S'])} |")
    out+=['','## Bảng 2. 18 slot: epoch chọn, macro-F1, gate N/V/S của cả 3 seed','',
          'Số liệu trên toàn bộ validation DS1 cố định (9.523 nhịp), checkpoint của epoch được chọn, giá trị chưa làm tròn. '
          'ΔN = tỉ lệ dự đoán N − tỉ lệ N thật (gate N: ΔN ≤ 0,10). Chỉ gate tại seed triển khai quyết định chọn cấu hình; gate của hai seed còn lại chỉ để báo.','',
          '| Cấu hình | Seed | Epoch chạy | Epoch chọn | Macro-F1 K (thô) | Làm tròn 4 | N | V | S | ΔN | Se S | +P S | Se V | +P V |',
          '|---|---:|---:|---:|---:|---:|---|---|---|---:|---:|---:|---:|---:|']
    for c in an['configurations']:
        for s in c['seeds']:
            x=slots[(c['configuration'],s['seed'])];mark=' ★' if s['seed']==c['best_seed'] else ''
            out.append(f"| {c['configuration']} | {s['seed']}{mark} | {x['epochs_run']} | {x['selected_epoch']} | {vn(x['score'],6)} | {x['score_r4'].replace('.',',')} | "
                       f"{g(x['gates']['N'])} | {g(x['gates']['V'])} | {g(x['gates']['S'])} | {vn(x['predN_minus_trueN_fraction'])} | "
                       f"{vn(x['SeS'])} | {vn(x['PS'])} | {vn(x['SeV'])} | {vn(x['PV'])} |")
    out+=['','★ = seed triển khai của cấu hình (macro-F1 làm tròn 4 cao nhất, hòa thì seed nhỏ hơn).','',
          '## Bảng 3. SHA-256 checkpoint được chọn của 18 slot','',
          'Đường dẫn tương đối từ gốc repo, nằm trong `ml/data/` (bị Git bỏ qua, không có trong ZIP). Danh sách đầy đủ dạng `sha256sum -c`: `selected-checkpoints.sha256`.','',
          '| Slot | Vai trò | Checkpoint | Bytes | SHA-256 |','|---|---|---|---:|---|']
    lines=[]
    for c in an['configurations']:
        for s in c['seeds']:
            x=slots[(c['configuration'],s['seed'])];need_role=c['configuration']==sel['configuration']
            role=('**checkpoint triển khai**' if s['seed']==sel['seed'] else 'seed của cấu hình chọn') if need_role else '—'
            out.append(f"| {x['slot_id']} | {role} | `{Path(x['checkpoint']).relative_to(RUN).as_posix()}` | {x['checkpoint_bytes']} | `{x['checkpoint_sha256']}` |")
            lines.append(f"{x['checkpoint_sha256']}  {x['checkpoint']}")
    return '\n'.join(out)+'\n','\n'.join(lines)+'\n'


def main():
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--tables',type=Path,required=True);a.add_argument('--sums',type=Path,required=True)
    o=a.parse_args();tables,sums=render()
    for path,text in ((o.tables,tables),(o.sums,sums)):
        with path.open('x',encoding='utf-8',newline='\n') as f:f.write(text)


if __name__=='__main__':main()
