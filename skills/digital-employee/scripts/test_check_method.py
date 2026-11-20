"""Real-shape failures: old Mac route, unlisted edits, self-exclusion, unsafe paths."""
import hashlib, json, os, shutil, tempfile, unittest, zipfile
from pathlib import Path
import check_method as gate

class ReleaseCheck(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir='/private/tmp' if Path('/private/tmp').exists() else None)
  self.base=Path(self.temp.name).resolve();self.root=self.base/'digital-employee'
  shutil.copytree(Path(__file__).resolve().parents[1],self.root,ignore=shutil.ignore_patterns('__pycache__'))
  self.seal()
 def tearDown(self):self.temp.cleanup()
 def seal(self):
  (self.root/'RELEASE.json').write_text(json.dumps({'version':'2026-11-20','readingPolicy':'aup-primary','files':{p:hashlib.sha256((self.root/p).read_bytes()).hexdigest()for p in gate.payload_files(self.root)}},ensure_ascii=False))
 def test_real_old_default_cannot_pass_even_with_fresh_hash(self):
  f=self.root/'references/wechat.md';s=f.read_text();a=s.index('## 默认读取来源');z=s.index('## 现有入口',a)
  # Keep the new marker and AUP keyword so a tag-only checker cannot pass.
  old='按来源类型固定主路径：**群消息、群内引用/转发、群语音和群文件优先使用本人已授权的大号 Mac 读取链；只有本人/小号私聊等大号没有的内容，才使用 AUP 小号读取。**'
  f.write_text(s[:a]+'## 默认读取来源\n<!-- reading-route: aup-primary -->\n'+old+'\n\n'+s[z:]);self.seal()
  with self.assertRaisesRegex(ValueError,'reading route'):gate.check(self.root)
 def test_changed_script_is_not_excluded_from_its_own_release(self):
  with (self.root/'scripts/check_method.py').open('a')as f:f.write('\n# unreviewed edit\n')
  with self.assertRaisesRegex(ValueError,'hash'):gate.check(self.root)
 def test_unlisted_file_cannot_hide_outside_manifest(self):
  (self.root/'references/forgotten.md').write_text('unreviewed')
  with self.assertRaisesRegex(ValueError,'file set'):gate.check(self.root)
 def test_parent_traversal_manifest_is_rejected(self):
  d=json.loads((self.root/'RELEASE.json').read_text());d['files']['../outside']='0'*64;(self.root/'RELEASE.json').write_text(json.dumps(d))
  with self.assertRaisesRegex(ValueError,'relative path'):gate.check(self.root)
 def test_external_symlink_is_never_followed(self):
  target=self.base/'private';target.write_text('keep');(self.root/'references/link.md').symlink_to(target)
  with self.assertRaisesRegex(ValueError,'symlink'):gate.check(self.root)
  self.assertEqual(target.read_text(),'keep')
 def test_relative_root_is_rejected(self):
  with self.assertRaisesRegex(ValueError,'absolute'):gate.check(Path('.'))
 def test_work_modes_cannot_replace_workbook_states(self):
  f=self.root/'scripts/workbook.py';f.write_text(f.read_text().replace("'待推进'","'主动推进'"));self.seal()
  with self.assertRaisesRegex(ValueError,'task states'):gate.check(self.root)
 def test_pack_failure_cleans_its_partial_output(self):
  from unittest.mock import patch
  target=self.base/'release.zip'
  with patch('check_method.zipfile.ZipFile',side_effect=OSError('write failed')):
   with self.assertRaises(OSError):gate.package(self.root,target)
  self.assertFalse(target.exists())
 def test_existing_output_is_not_overwritten(self):
  target=self.base/'release.zip';target.write_bytes(b'keep')
  with self.assertRaises(FileExistsError):gate.package(self.root,target)
  self.assertEqual(target.read_bytes(),b'keep')
 def test_current_release_and_pack_have_complete_safe_members(self):
  gate.check(self.root);target=self.base/'release.zip';gate.package(self.root,target)
  with zipfile.ZipFile(target)as z:
   self.assertIsNone(z.testzip());self.assertIn('digital-employee/scripts/check_method.py',z.namelist())
   self.assertEqual(set(z.namelist()),{'digital-employee/'+x for x in gate.payload_files(self.root)}|{'digital-employee/RELEASE.json'})
if __name__=='__main__':unittest.main()
