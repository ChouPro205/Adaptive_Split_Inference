import json,sys,importlib.util,pathlib
spec=importlib.util.spec_from_file_location('cc',sys.argv[1]);cc=importlib.util.module_from_spec(spec);spec.loader.exec_module(cc)
sp=pathlib.Path(sys.argv[2]);a=json.loads((cc.ROOT/cc.ANALYZE).read_text(encoding='utf-8'))
cases={'seed':lambda x:x['selected'].__setitem__('seed',20261031),
       'gate':lambda x:x['configurations'][5]['seeds'][0]['gates'].__setitem__('V',True)}
for name,mut in cases.items():
    b=json.loads(json.dumps(a));mut(b);p=sp/f'neg-{name}.json';p.write_text(json.dumps(b),encoding='utf-8')
    cc.ANALYZE=str(p);sys.argv=['cc','--out',str(sp/f'neg-{name}-out.json')]
    try:cc.main();print(name,'UNEXPECTED_PASS')
    except SystemExit as e:print(name,'REJECTED:',e)
