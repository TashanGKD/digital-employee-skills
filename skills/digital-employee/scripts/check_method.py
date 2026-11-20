#!/usr/bin/env python3
"""Check/package this Skill: reject old live Mac-first policy and unsealed edits.

No arguments only print help. Reads an explicit root; packaging requires an
explicit new output path. No network, scheduling, business writes or model calls.
Hashes include this checker, its tests and self-test wrapper, not RELEASE itself.
This verifies documents/package consistency, not employee behavior or live wake.
"""
import argparse, ast, hashlib, json, os, re, subprocess, sys, zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

def ordinary_root(root):
 root=Path(root)
 if not root.is_absolute() or '..' in root.parts:raise ValueError('normalized absolute root required')
 for p in (root,*root.parents):
  if p.is_symlink():raise ValueError('symlink root refused')
 if not root.is_dir():raise ValueError('Skill directory required')
 return root

def payload_files(root):
 root=ordinary_root(root);out=[]
 for base,dirs,names in os.walk(root,followlinks=False):
  dirs[:]=[n for n in dirs if n!='__pycache__']
  for n in dirs+names:
   if (Path(base)/n).is_symlink():raise ValueError('symlink payload refused')
  for name in names:
   f=Path(base)/name
   if not f.is_file():raise ValueError('ordinary payload file required')
   rel=f.relative_to(root).as_posix()
   if rel!='RELEASE.json':out.append(rel)
 return sorted(out)

def check(root):
 root=ordinary_root(root)
 if (root/'RELEASE.json').is_symlink():raise ValueError('symlink release refused')
 manifest=json.loads((root/'RELEASE.json').read_text())
 if not isinstance(manifest.get('files'),dict):raise ValueError('release files required')
 for name,digest in manifest['files'].items():
  p=PurePosixPath(name)
  if not name or p.is_absolute() or '..' in p.parts or p.as_posix()!=name or '\\' in name:raise ValueError('unsafe relative path')
  if not isinstance(digest,str) or not re.fullmatch('[a-f0-9]{64}',digest):raise ValueError('file hash required')
 files=payload_files(root)
 if set(files)!=set(manifest['files']):raise ValueError('release file set differs')
 for name in files:
  if hashlib.sha256((root/name).read_bytes()).hexdigest()!=manifest['files'][name]:raise ValueError('release hash differs: '+name)
 entry=(root/'SKILL.md').read_text()
 if '方法版本：'+str(manifest.get('version')) not in entry:raise ValueError('entry/release version differs')
 if manifest.get('readingPolicy')!='aup-primary':raise ValueError('reading route metadata differs')
 wechat=(root/'references/wechat.md').read_text();a=wechat.index('## 默认读取来源');z=wechat.index('## 现有入口',a);route=wechat[a:z]
 if '<!-- reading-route: aup-primary -->' not in route or 'AUP 小号' not in route or re.search(r'群消息[^\n]*优先[^\n]*大号\s*Mac',route):raise ValueError('reading route reintroduced old Mac primary')
 modes=(root/'references/operating-model.md').read_text()
 for mode in ['主动推进','按要求推进','等待反馈','等待来源/条件','暂不主动推进','暂停']:
  if '| '+mode+' |' not in modes:raise ValueError('work modes missing: '+mode)
 tree=ast.parse((root/'scripts/workbook.py').read_text());states=None
 for node in tree.body:
  if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name)and t.id=='STATES'for t in node.targets):states=ast.literal_eval(node.value)
 doc=(root/'references/workbook.md').read_text();m=re.search(r'^任务进度：([^\n]+)。$',doc,re.M)
 if not m or tuple(m[1].split('、'))!=states:raise ValueError('work modes must not replace workbook task states')
 if '已承接' not in entry or '不凭空制造工作' not in entry:raise ValueError('accepted task closure/idle distinction missing')
 for name in ['SKILL.md']+[x for x in files if x.startswith('references/')and x.endswith('.md')]:
  for target in re.findall(r'\]\(([^)]+)\)',(root/name).read_text()):
   target=target.split('#',1)[0]
   if not target or target.startswith('/') or ':' in target or '{{' in target:continue
   if target.startswith(('../codex-thread-handoff/','../wechat-', '../../codex-thread-handoff/','../../wechat-')):continue
   path=Path(os.path.normpath(str((root/name).parent/unquote(target))))
   if root not in path.parents or not path.is_file():raise ValueError('missing internal link: '+name+' -> '+target)
 return {'version':manifest['version'],'files':len(files)+1,'readingPolicy':'aup-primary','scope':'document and package consistency only'}

def package(root,output):
 root=ordinary_root(root);output=Path(output)
 if not output.is_absolute() or '..' in output.parts:raise ValueError('absolute package output required')
 ordinary_root(output.parent)
 if output==root or root in output.parents:raise ValueError('package output must be outside Skill')
 check(root);release=(root/'RELEASE.json').read_bytes();manifest=json.loads(release)
 # Exclusive create preserves any pre-existing package on every failure branch.
 with output.open('xb') as stream:
  try:
   with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED)as archive:
    for name in payload_files(root):
     data=(root/name).read_bytes()
     if hashlib.sha256(data).hexdigest()!=manifest['files'][name]:raise ValueError('payload changed during packaging')
     archive.writestr('digital-employee/'+name,data)
    archive.writestr('digital-employee/RELEASE.json',release)
   check(root)
   if (root/'RELEASE.json').read_bytes()!=release:raise ValueError('release changed during packaging')
  except BaseException:
   stream.close();output.unlink();raise
 return {'output':str(output),'bytes':output.stat().st_size,'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}

def main():
 ap=argparse.ArgumentParser(description=__doc__);g=ap.add_mutually_exclusive_group();g.add_argument('--check',action='store_true');g.add_argument('--package',type=Path);ap.add_argument('--root',type=Path)
 a=ap.parse_args()
 if not(a.check or a.package):ap.print_help();return
 root=a.root or Path(__file__).resolve().parents[1]
 try:
  if a.package:
   # The release path always runs the negative regression suite before export.
   tests=Path(__file__).resolve().parent
   subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(tests),'-p','test_check_method.py'],check=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
   result=package(root,a.package)
  else:result=check(root)
  print(json.dumps(result,ensure_ascii=False))
 except (OSError,ValueError,KeyError,subprocess.CalledProcessError)as e:
  print(json.dumps({'state':'failed','reason':str(e)},ensure_ascii=False));raise SystemExit(1)
if __name__=='__main__':main()
