from pathlib import Path
import json,subprocess,sys,hashlib,os
root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'], text=True).strip())
label=sys.argv[1]; command=sys.argv[2:]
folder=root/'ml/provenance/week4-inventory-fix'
r=subprocess.run(command,cwd=root,capture_output=True,text=True,encoding='utf-8',errors='replace')
log=folder/(label+'.txt'); log.write_bytes((r.stdout+r.stderr).replace('\r\n','\n').encode())
record={'name':label,'command':command,'commit_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'exit_status':r.returncode,'log_path':log.relative_to(root).as_posix(),'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
(folder/(label+'.json')).write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print(json.dumps(record)); print((r.stdout+r.stderr)[-4000:]);sys.exit(r.returncode)
