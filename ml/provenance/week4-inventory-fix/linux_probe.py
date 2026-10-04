from pathlib import Path,PureWindowsPath
import json,sys,platform,hashlib,shutil,importlib.metadata
repo=Path('/mnt/c/Users/Admin/Adaptive_Split_Inference')
p=repo/'ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1'
raw=(p/'manifest.json').read_bytes()
assert hashlib.sha256(raw).hexdigest()=='a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6'
manifest=json.loads(raw)
names=[x.relative_to(p).as_posix() for x in sorted(p.rglob('*')) if x.is_file() and x.name!='manifest.json' and '__pycache__' not in x.parts]
expected=[r['path'] for r in manifest['files']]
assert len(names)==len(expected)==40
assert names!=expected and sorted(names)==sorted(expected)
assert sorted(names,key=PureWindowsPath)==expected
versions={}
for name in ['torch','numpy','onnx','onnxruntime','protobuf','ml_dtypes','flatbuffers']:
 try: versions[name]=importlib.metadata.version(name)
 except importlib.metadata.PackageNotFoundError: versions[name]='MISSING'
print(json.dumps({'platform':platform.platform(),'python':platform.python_version(),'python311':shutil.which('python3.11'),'uv':shutil.which('uv'),'conda':shutil.which('conda'),'versions':versions,'real_linux_path_order_reproduction':'PASS','legacy_list_equality':names==expected,'canonical_path_equality':sorted(names)==sorted(expected),'full_verifier':'PENDING: required Python 3.11.9 and dependencies unavailable; no runtime gate bypass','posix_paths':names,'windows_manifest_paths':expected},indent=2))
