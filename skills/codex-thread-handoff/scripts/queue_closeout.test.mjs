import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { applyPlan, inputSHA } from './queue_closeout.mjs';

const item = () => ({threadId:'demo-thread', id:'demo-queue', expectedInputSHA:inputSHA(['original']), reason:'already verified complete', evidence:['local-receipt']});
test('traversal IDs are rejected before any call', async () => {
  await assert.rejects(applyPlan({retire:[{...item(), id:'../../escape'}]},{}),/identifier/);
});
test('duplicate dispositions cannot execute', async () => {
  await assert.rejects(applyPlan({retire:[item(),item()]},{}),/two dispositions/);
});
test('dry-run never connects or creates an archive', async () => {
  const r = await applyPlan({retire:[item()]},{call:()=>{throw Error('must not call')}});
  assert.equal(r.execute,false);
});
test('symlink archive parent is refused', async () => {
  const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'queue-test-')));
  try {
    fs.mkdirSync(path.join(root,'real')); fs.symlinkSync(path.join(root,'real'),path.join(root,'link'));
    await assert.rejects(applyPlan({retire:[item()]},{execute:true,call:()=>{},archiveDir:path.join(root,'link','new')}),/symlink/);
    assert.deepEqual(fs.readdirSync(path.join(root,'real')),[]);
  } finally { fs.rmSync(root,{recursive:true,force:true}); }
});
test('changed original remains pending without a mutation', async () => {
  const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'queue-test-')));const calls=[];
  try {
    const r=await applyPlan({retire:[item()]},{execute:true,archiveDir:path.join(root,'archive'),call:async(m)=>{calls.push(m);return {data:[{id:'demo-queue',input:['changed']}]}}});
    assert.equal(r.items[0].state,'changed_kept'); assert.deepEqual(calls,['thread/queue/list']);
  } finally { fs.rmSync(root,{recursive:true,force:true}); }
});
test('successful retirement preserves the original and receipt', async () => {
  const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'queue-test-')));let rows=[{id:'demo-queue',input:['original']}];
  try {
    const r=await applyPlan({retire:[item()]},{execute:true,archiveDir:path.join(root,'archive'),call:async(m)=>{
      if(m==='thread/queue/delete'){rows=[];return {ok:true}} return {data:rows};
    }});
    assert.equal(r.items[0].state,'archived_removed');
    assert.deepEqual(JSON.parse(fs.readFileSync(path.join(root,'archive','demo-queue.original.json'))).input,['original']);
  } finally { fs.rmSync(root,{recursive:true,force:true}); }
});
test('uncertain mutation is checked once and never replayed', async () => {
  const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'queue-test-')));let writes=0;
  try {
    await assert.rejects(applyPlan({retire:[item()]},{execute:true,archiveDir:path.join(root,'archive'),call:async(m)=>{
      if(m==='thread/queue/delete'){writes++;throw Error('timeout')} return {data:[{id:'demo-queue',input:['original']}]};
    }}),/outcome unresolved/);
    assert.equal(writes,1);assert.ok(fs.existsSync(path.join(root,'archive','demo-queue.unresolved.json')));
  } finally { fs.rmSync(root,{recursive:true,force:true}); }
});
