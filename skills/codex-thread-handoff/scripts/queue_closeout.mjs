// Reviewed queue closeout library. No RPC client, daemon or automatic classifier.
// Reject path-bearing IDs and shared archives; uncertain mutations are never retried.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';

export const inputSHA = input => crypto.createHash('sha256').update(JSON.stringify(input)).digest('hex');
const identifier = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,128}$/.test(value);

async function pending(call,threadId) {
  let cursor; const rows=[]; const seen=new Set();
  do {
    const p=await call('thread/queue/list',{threadId,limit:100,...(cursor?{cursor}:{})});
    if(!Array.isArray(p.data)) throw Error('Adapter list contract not verified');
    rows.push(...p.data);cursor=p.nextCursor;
    if(cursor) {
      const key=JSON.stringify(cursor);
      if(seen.has(key)||seen.size>=100) throw Error('Queue pagination not bounded');
      seen.add(key);
    }
  } while(cursor);
  return rows;
}

function newArchive(directory) {
  if(typeof directory!=='string'||!path.isAbsolute(directory)||path.normalize(directory)!==directory) throw Error('Normalized absolute archive directory required');
  let p=path.dirname(directory);
  while(true) {
    if(fs.lstatSync(p).isSymbolicLink()) throw Error('symlink archive parent refused');
    const next=path.dirname(p);if(next===p) break;p=next;
  }
  fs.mkdirSync(directory,{mode:0o700}); // Exclusive; never reuse an uncertain old operation.
}
const save=(directory,name,value)=>fs.writeFileSync(path.join(directory,name),JSON.stringify(value,null,2)+'\n',{flag:'wx',mode:0o600});

export async function applyPlan(plan,{call,archiveDir,execute=false}={}) {
  if(!plan||!Array.isArray(plan.merge??[])||!Array.isArray(plan.retire??[])) throw Error('Reviewed plan required');
  const operations=[...(plan.merge??[]).map(x=>({...x,kind:'merge'})),...(plan.retire??[]).map(x=>({...x,kind:'retire'}))];
  const keys=new Set();
  for(const x of operations) {
    if(!identifier(x.threadId)||!identifier(x.id)) throw Error('Safe stable identifier required');
    if(!/^[a-f0-9]{64}$/.test(x.expectedInputSHA)||typeof x.reason!=='string'||!x.reason.trim()||!Array.isArray(x.evidence)||!x.evidence.length) throw Error('Reviewed disposition and original evidence required');
    const key=x.threadId+'|'+x.id;
    if(keys.has(key)) throw Error('Same item has two dispositions');keys.add(key);
    if(x.kind==='merge'&&(!Array.isArray(x.replacementInput)||!x.replacementInput.length)) throw Error('Merged retained input required');
  }
  if(!execute) return {execute:false,merge:plan.merge?.length??0,retire:plan.retire?.length??0};
  if(typeof call!=='function') throw Error('Verified adapter call required');
  newArchive(archiveDir);save(archiveDir,'reviewed-plan.json',plan);
  const result={startedAt:Date.now()/1000,items:[]};
  for(const x of operations) {
    const current=(await pending(call,x.threadId)).find(r=>r.id===x.id);let state;
    if(!current) state='no_longer_pending';
    else if(inputSHA(current.input)!==x.expectedInputSHA) state='changed_kept';
    else {
      save(archiveDir,x.id+'.original.json',current);save(archiveDir,x.id+'.disposition.json',x);
      const method=x.kind==='merge'?'thread/queue/update':'thread/queue/delete';
      const params={threadId:x.threadId,queuedSubmissionId:x.id,...(x.kind==='merge'?{input:x.replacementInput}:{})};
      save(archiveDir,x.id+'.intent.json',{method,params});let error=null,receipt=null;
      try {receipt=await call(method,params);} catch(e) {error=String(e.message??e);}
      const after=(await pending(call,x.threadId)).find(r=>r.id===x.id);
      if(x.kind==='merge') {
        if(!after||inputSHA(after.input)!==inputSHA(x.replacementInput)) {
          save(archiveDir,x.id+'.unresolved.json',{error,receipt,current:after??null});throw Error('Merge outcome unresolved; no repeat mutation');
        }
        state='merged_retained';
      } else {
        if(after) {save(archiveDir,x.id+'.unresolved.json',{error,receipt,current:after});throw Error('Retirement outcome unresolved; no repeat mutation');}
        state='archived_removed';
      }
      save(archiveDir,x.id+'.receipt.json',{state,error,receipt,verifiedAt:Date.now()/1000});
    }
    result.items.push({threadId:x.threadId,id:x.id,kind:x.kind,state});
  }
  result.finishedAt=Date.now()/1000;save(archiveDir,'RESULT.json',result);return result;
}

if(import.meta.url===pathToFileURL(process.argv[1]??'').href) {
  console.log('Library only: import applyPlan with a verified host adapter. Default execute=false; no connection or changes.');
  if(process.argv.includes('--execute')) {console.error('No bundled RPC adapter; execution refused.');process.exitCode=2;}
}
