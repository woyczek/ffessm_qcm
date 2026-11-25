import json
import tempfile
import unittest
from pathlib import Path
from layout import tidy_legacy_root


class LayoutTests(unittest.TestCase):
    def test_legacy_files_preserved_and_current_bank_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'questions').mkdir()
            (root/'questions'/'bank.json').write_text('new bank', encoding='utf-8')
            (root/'bank.json').write_text('old bank', encoding='utf-8')
            (root/'seed.json').write_text('old seed', encoding='utf-8')
            (root/'cli.py').write_text('old cli', encoding='utf-8')
            (root/'progress.json').write_text('personal answers', encoding='utf-8')
            tidy_legacy_root(root)
            self.assertEqual((root/'questions'/'bank.json').read_text(), 'new bank')
            self.assertEqual((root/'preferences'/'legacy'/'seed.json').read_text(), 'old seed')
            self.assertEqual((root/'progress.json').read_text(), 'personal answers')
            self.assertFalse((root/'bank.json').exists())
            self.assertFalse((root/'cli.py').exists())
            self.assertTrue(list((root/'questions'/'legacy').glob('bank-*.json')))
            marker = (root/'preferences'/'layout.json').read_bytes()
            self.assertEqual(tidy_legacy_root(root), [])
            self.assertEqual((root/'preferences'/'layout.json').read_bytes(), marker)

    def test_old_bank_moved_if_new_bank_does_not_exist(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'bank.json').write_text('bank', encoding='utf-8')
            tidy_legacy_root(root)
            self.assertEqual((root/'questions'/'bank.json').read_text(), 'bank')


if __name__ == '__main__':
    unittest.main()
