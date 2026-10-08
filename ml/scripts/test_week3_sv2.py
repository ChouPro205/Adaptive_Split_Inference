"""Reason-specific rejection tests on disposable copies of the SV2 package."""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
from pathlib import Path
import shutil
import tempfile

import numpy as np
import onnx

from week3_common import need, read_json, sha, write_json
from week3_sv2_common import inventory
from verify_week3_sv2 import verify
from verify_week3_sv2 import LEGACY, POLICIES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package",type=Path,required=True)
    parser.add_argument("--expected-manifest-sha256",required=True)
    parser.add_argument("--recomputation-policy", choices=POLICIES, default=LEGACY)
    args = parser.parse_args()
    package = args.package.resolve()
    before = {p.relative_to(package).as_posix():sha(p) for p in package.rglob("*") if p.is_file()}
    verify(package,args.expected_manifest_sha256,args.recomputation_policy)

    def manifest_field(p,key,value):
        m = read_json(p / "manifest.json"); m[key]=value
        write_json(p / "manifest.json",m)

    def split(p):
        m = read_json(p / "manifest.json"); m["splits"][2]["head_endpoint"]="features.2"
        write_json(p / "manifest.json",m)

    def tensor(p,kind):
        path = p / "golden/z_s9.npy"; a = np.load(path,allow_pickle=False)
        if kind=="shape": a=a[:,:-1]
        if kind=="dtype": a=a.astype(np.float64)
        if kind=="nan": a[0,0]=np.nan
        if kind=="inf": a[0,0]=np.inf
        if kind=="tiny": a[0,0]+=np.float32(1e-6)
        if kind=="value": a[0,0]+=1
        np.save(path,a,allow_pickle=False)

    def graph(p,kind):
        path=p / "models/tail_9.onnx"; m=onnx.load(path)
        if kind=="opset": m.opset_import[0].version=14
        if kind=="name":
            old=m.graph.input[0].name; m.graph.input[0].name="wrong_input"
            for node in m.graph.node:
                for i,name in enumerate(node.input):
                    if name==old: node.input[i]="wrong_input"
        if kind=="weights":
            t=m.graph.initializer[-1]
            a=onnx.numpy_helper.to_array(t).copy()+np.float32(100)
            t.CopyFrom(onnx.numpy_helper.from_array(a,name=t.name))
        onnx.save(m,path)

    cases=[
        ("missing external trust anchor",lambda p:None,"Independently trusted", "none"),
        ("manifest metadata mutation",lambda p:manifest_field(p,"preprocessing","wrong"),"Manifest SHA-256 mismatch","original"),
        ("manifest plus rebuilt inventory",lambda p:manifest_field(p,"preprocessing","wrong"),"Manifest SHA-256 mismatch","original_rehash"),
        ("changed model_version",lambda p:manifest_field(p,"model_version","wrong"),"Frozen model identity mismatch","semantic"),
        ("wrong split endpoint",split,"Authoritative split mapping mismatch","semantic"),
        ("missing verifier test",lambda p:(p / "scripts/test_week3_sv2.py").unlink(),"Required package file set differs","semantic"),
        ("missing tail",lambda p:(p / "models/tail_4.onnx").unlink(),"Required package file set differs","semantic"),
        ("forbidden tail10",lambda p:shutil.copyfile(p / "models/tail_9.onnx",p / "models/tail_10.onnx"),"Required package file set differs","semantic"),
        ("sample identity corruption",lambda p:(p / "samples.csv").write_bytes((p / "samples.csv").read_bytes().replace(b'MIT-BIH:105:197',b'MIT-BIH:105:198')),"Frozen sample identities/order mismatch","semantic"),
        ("wrong activation shape",lambda p:tensor(p,"shape"),"Golden shape mismatch: s=9","semantic"),
        ("wrong dtype with matching hashes",lambda p:tensor(p,"dtype"),"Wrong tensor dtype","raw_semantic"),
        ("NaN with matching hashes",lambda p:tensor(p,"nan"),"Non-finite or non-contiguous","raw_semantic"),
        ("Inf with matching hashes",lambda p:tensor(p,"inf"),"Non-finite or non-contiguous","raw_semantic"),
        ("tiny golden mutation with original anchor",lambda p:tensor(p,"tiny"),"File hash/size mismatch","original"),
        ("activation value corruption",lambda p:tensor(p,"value"),"Recomputed golden bits differ: s=9" if args.recomputation_policy == LEGACY else "Recomputed golden tolerance failure: s=9","semantic"),
        ("wrong ONNX opset",lambda p:graph(p,"opset"),"ONNX opset mismatch","semantic"),
        ("wrong ONNX input name",lambda p:graph(p,"name"),"ONNX input contract mismatch","semantic"),
        ("changed ONNX weights",lambda p:graph(p,"weights"),"ONNX FP32 tolerance failure","semantic"),
    ]
    for name,mutate,message,mode in cases:
        with tempfile.TemporaryDirectory(prefix="week3_sv2_negative_") as tmp:
            fixture=Path(tmp) / package.name
            shutil.copytree(package,fixture)
            mutate(fixture)
            if mode not in ("original","none"):
                m=read_json(fixture / "manifest.json")
                if mode=="raw_semantic":
                    # Test-only builder: allow invalid dtype/finite data through
                    # the hash layer, so the production semantic gate is tested.
                    for row in m["files"]:
                        p=fixture / row["path"]
                        row.update(sha256=sha(p),size_bytes=p.stat().st_size)
                        if p.suffix==".npy":
                            a=np.load(p,allow_pickle=False)
                            row.update(shape=list(a.shape),dtype=a.dtype.str)
                else:
                    m["files"]=inventory(fixture)
                write_json(fixture / "manifest.json",m)
            expected = None if mode=="none" else args.expected_manifest_sha256 if mode.startswith("original") else sha(fixture / "manifest.json")
            try:
                verify(fixture,expected,args.recomputation_policy)
            except ValueError as exc:
                need(message in str(exc),f"Wrong rejection for {name}: {exc}")
            else:
                raise ValueError(f"Mutation accepted: {name}")
            print(f"PASS expected rejection: {name}")
    from export_week3_sv2 import export
    try:
        export(Path('.'),package.name,package.parent)
    except ValueError as exc:
        need("Immutable revision already exists" in str(exc),f"Wrong overwrite failure: {exc}")
    else:
        raise ValueError("Immutable overwrite accepted")
    after={p.relative_to(package).as_posix():sha(p) for p in package.rglob("*") if p.is_file()}
    need(before==after,"Source package changed")
    print(f"PASS: {len(cases)+1} expected rejections; immutable source package unchanged")


if __name__ == "__main__":
    main()
