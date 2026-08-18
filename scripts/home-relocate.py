#!/usr/bin/env python3
"""Fail-closed, operator-invoked home relocation helper; never deletes source backups."""
import argparse,fcntl,json,os,shutil,subprocess,sys,time
from pathlib import Path
EXPECTED_TARGET='/mnt/zer0models'; EXPECTED_UUID='3c8b6c35-4d36-4a69-b5f3-df88f07cbd82'
def fail(msg): raise SystemExit(f'REFUSED: {msg}')
def mount(path):
 p=subprocess.run(['findmnt','-J','-o','TARGET,UUID,FSTYPE','--target',str(path)],text=True,capture_output=True,check=True);return json.loads(p.stdout)['filesystems'][0]
def preflight(src,dst,expected_uuid,allow_open=False,min_free=10*1024**3):
 m=mount(dst.parent); 
 if m['target']!=EXPECTED_TARGET or m.get('uuid')!=expected_uuid or m.get('fstype')!='btrfs': fail('wrong/absent target mount identity')
 if shutil.disk_usage(dst.parent).free<min_free: fail('target reserve violated')
 if src.is_symlink():
  if dst.exists() and src.resolve()==dst.resolve(): return 'already-cut-over'
  fail('source is an unexpected symlink')
 if not src.is_dir(): fail('source must be a directory')
 if dst.exists(): fail('destination already exists')
 if not allow_open:
  q=subprocess.run(['lsof','+D',str(src)],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
  if q.stdout.strip(): fail('source has open files')
 return 'ready'
def main():
 ap=argparse.ArgumentParser();ap.add_argument('action',choices=['dry-run','commit','rollback']);ap.add_argument('source',type=Path);ap.add_argument('destination',type=Path);ap.add_argument('--expected-uuid',default=EXPECTED_UUID);ap.add_argument('--receipt',type=Path,required=True);a=ap.parse_args();a.source=a.source.expanduser().absolute();a.destination=a.destination.absolute();a.receipt=a.receipt.absolute();a.receipt.mkdir(parents=True,exist_ok=True);lock=a.receipt/'.lock'
 with lock.open('w') as f:
  try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:fail('concurrent invocation')
  backup=a.source.with_name(a.source.name+'.migration-backup.'+a.receipt.name)
  if a.action=='rollback':
   if not a.source.is_symlink() or not backup.is_dir():fail('rollback state mismatch')
   a.source.unlink();os.replace(backup,a.source);print('rollback=PASS');return
  state=preflight(a.source,a.destination,a.expected_uuid)
  if state=='already-cut-over':print(state);return
  print(json.dumps({'state':state,'source':str(a.source),'destination':str(a.destination),'backup':str(backup)}))
  if a.action=='dry-run':return
  incoming=a.destination.with_name('.'+a.destination.name+'.incoming.'+a.receipt.name)
  if incoming.exists():fail('incoming destination exists')
  incoming.mkdir(mode=0o700,parents=True)
  cmd=['rsync','-aAXHSx','--numeric-ids',str(a.source)+'/ ',str(incoming)+'/']
  cmd[-2]=str(a.source)+'/'
  subprocess.run(cmd,check=True)
  verify=subprocess.run(['rsync','-aAXHSxnc','--numeric-ids','--itemize-changes',str(a.source)+'/',str(incoming)+'/'],text=True,capture_output=True,check=True)
  if verify.stdout:fail('checksum verification mismatch')
  os.replace(incoming,a.destination);os.replace(a.source,backup);os.symlink(a.destination,a.source)
  (a.receipt/'receipt.json').write_text(json.dumps({'source':str(a.source),'destination':str(a.destination),'backup':str(backup),'backup_retained':True,'time_ns':time.time_ns()},sort_keys=True)+'\n')
  print('commit=PASS; source backup retained')
if __name__=='__main__':main()
