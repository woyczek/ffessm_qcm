"""Le site public doit fonctionner sous /depot/ et exclure les données privées."""
from pathlib import Path
import tempfile
import unittest

from tools.build_pages import ROOT, PUBLIC_FILES, build


class PagesTests(unittest.TestCase):
    def test_public_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = build(Path(tmp) / 'site')
            files = {p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}
            self.assertEqual(files, set(PUBLIC_FILES) | {'index.html', '.nojekyll'})
            self.assertFalse(any('preferences' in name or 'progress' in name for name in files))
            html = (output / 'index.html').read_text(encoding='utf-8')
            self.assertIn('window.pagesApi(action,data)', html)
            self.assertNotIn("fetch('/api/", html)
            self.assertNotIn('href="/assets/', html)
            self.assertNotIn("link.href='/documents/", html)
            self.assertIn('src="web/pages.js"', html)
            self.assertIn('href="assets/favicon.png"', html)
            self.assertIn("link.href='documents/Prerogatives_FFESSM_impression.pdf'", html)

    def test_build_preserves_existing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / 'personal.txt'
            marker.write_text('conserver', encoding='utf-8')
            with self.assertRaises(ValueError):
                build(tmp)
            self.assertEqual(marker.read_text(encoding='utf-8'), 'conserver')
        with self.assertRaises(ValueError):
            build(ROOT)


if __name__ == '__main__':
    unittest.main()
