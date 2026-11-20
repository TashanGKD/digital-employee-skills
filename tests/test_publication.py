"""Reject leaked identities, escaping links, symlink payloads and unsealed edits.

Fixtures are deliberately synthetic. This suite never contacts a real account.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/check_publication.py'
spec = importlib.util.spec_from_file_location('publication', SCRIPT)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve() / 'bundle'
        self.root.mkdir()
        for name in gate.SKILLS:
            d = self.root / 'skills' / name
            d.mkdir(parents=True)
            (d / 'SKILL.md').write_text('---\nname: '+name+'\ndescription: test fixture\n---\n# Fixture\n')
            (d / 'README.md').write_text('# Fixture\n')
        (self.root / 'README.md').write_text('# Fixture\n')
        (self.root / 'LICENSE').write_text('MIT License\n')
        (self.root / 'scripts').mkdir()
        (self.root / 'scripts/check_publication.py').write_text('# fixture checker\n')
        self.seal()

    def tearDown(self):
        self.tmp.cleanup()

    def seal(self):
        files = {p.relative_to(self.root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in self.root.rglob('*') if p.is_file() and p.name != 'MANIFEST.json'}
        (self.root / 'MANIFEST.json').write_text(json.dumps({'files': files}))

    def test_private_identity_is_rejected_even_after_sealing(self):
        (self.root / 'README.md').write_text('wx'+'id_'+'synthetic-private-account')
        self.seal()
        with self.assertRaisesRegex(ValueError, 'private identity'):
            gate.check(self.root)

    def test_link_cannot_escape_repository(self):
        (self.root / 'README.md').write_text('[outside](../private.md)')
        self.seal()
        with self.assertRaisesRegex(ValueError, 'link'):
            gate.check(self.root)

    def test_symlink_payload_is_not_followed(self):
        private = self.root.parent / 'private'
        private.write_text('untouched')
        (self.root / 'outside').symlink_to(private)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            gate.check(self.root)
        self.assertEqual(private.read_text(), 'untouched')

    def test_checker_cannot_exclude_itself_from_manifest(self):
        (self.root / 'scripts/check_publication.py').write_text('# changed\n')
        with self.assertRaisesRegex(ValueError, 'hash'):
            gate.check(self.root)

    def test_duplicate_frontmatter_name_is_rejected(self):
        f = self.root / 'skills' / gate.SKILLS[0] / 'SKILL.md'
        f.write_text('---\nname: '+gate.SKILLS[1]+'\ndescription: duplicate\n---\n')
        self.seal()
        with self.assertRaisesRegex(ValueError, 'name'):
            gate.check(self.root)

    def test_missing_sibling_skill_reference_is_rejected(self):
        (self.root / 'README.md').write_text('[missing](skills/missing/SKILL.md)')
        self.seal()
        with self.assertRaisesRegex(ValueError, 'link'):
            gate.check(self.root)

    def test_complete_fixture_passes(self):
        result = gate.check(self.root)
        self.assertEqual(result['skills'], 6)


if __name__ == '__main__':
    unittest.main()
