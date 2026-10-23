#!/usr/bin/env python3
"""Local TCP bench transport for I1 bytes. One frame per connection, no added wire fields.
Not the official BLE transport; calls the same file pipeline for each received frame.
"""
import argparse,json,socket,struct,subprocess,sys
from pathlib import Path

def exact(c,n):
 b=bytearray()
 while len(b)<n:
  chunk=c.recv(n-len(b))
  if not chunk:raise ValueError('Truncated frame')
  b.extend(chunk)
 return bytes(b)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--serve',type=Path,required=True)
 p.add_argument('--output',type=Path,required=True);p.add_argument('--port',type=int,default=7797)
 p.add_argument('--requests',type=int,default=1);a,extra=p.parse_known_args()
 if not 1<=a.port<=65535 or a.requests<1:p.error('Invalid port/count')
 a.output.mkdir(parents=True,exist_ok=False);rows=[]
 with socket.socket() as server:
  server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);server.bind(('127.0.0.1',a.port));server.listen(1)
  print('LISTENING 127.0.0.1:%d'%a.port,flush=True)
  for index in range(a.requests):
   conn,_=server.accept()
   with conn:
    conn.settimeout(10);row={'index':index}
    try:
     header=exact(conn,32);total=struct.unpack_from('<I',header,12)[0]
     if header[:4]!=b'I1PK' or not 36<=total<=6380:raise ValueError('Invalid envelope size/magic')
     packet=header+exact(conn,total-32)
     request=a.output/('request_%d.bin'%index);request.write_bytes(packet)
     out=a.output/('request_%d'%index)
     with (a.output/('request_%d.log'%index)).open('x') as log:
      r=subprocess.run([sys.executable,'-B',str(a.serve),'--request',str(request),'--output',str(out),*extra],stdout=log,stderr=subprocess.STDOUT,timeout=60)
     response=out/'response.bin'
     if response.is_file():conn.sendall(response.read_bytes())
     row.update(exit_code=r.returncode,response_sent=response.is_file())
    except (ValueError,OSError,subprocess.TimeoutExpired) as e:row['error']=str(e)
    rows.append(row)
    (a.output/'socket_summary.json').write_text(json.dumps({'scope':'LOCAL_TCP_BENCH_NOT_BLE','rows':rows},indent=2)+'\n')
 return 0 if all(r.get('exit_code')==0 for r in rows) else 1
if __name__=='__main__':sys.exit(main())
