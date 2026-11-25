import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from pack import build
from engine import Quiz


class DistributionTests(unittest.TestCase):
    def test_no_personal_answers_and_executable_unix_scripts(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)/'distribution.zip'
            build(output)
            with ZipFile(output) as archive:
                names = archive.namelist()
                self.assertFalse(any(Path(n).name.startswith(('progress', 'seed')) for n in names))
                top_files = {n.split('/', 1)[1] for n in names if n.count('/') == 1}
                self.assertEqual(top_files, {'interface.html', 'README.md', 'Lancer-QCM.cmd', 'Lancer-QCM-Terminal.cmd', 'lancer-qcm.sh', 'Lancer-QCM.command', 'Lancer-QCM-Terminal.command'})
                self.assertFalse(any(n.count('/') == 1 and n.endswith(('.py', '.json', '.js')) for n in names))
                bank = json.loads(archive.read('ffessm-qcm/questions/bank.json'))
                self.assertTrue(archive.read('ffessm-qcm/assets/favicon.png').startswith(b'\x89PNG\r\n\x1a\n'))
                self.assertEqual(len(bank['questions']), 140)
                self.assertEqual(len({q['id'] for q in bank['questions']}), len(bank['questions']))
                batch=json.loads(archive.read('ffessm-qcm/questions/questions-101-140.json'))['questions']
                self.assertEqual({q['id'] for q in batch},set(range(101,141)))
                self.assertTrue(all(2 <= len(q['answers']) <= 3 for q in batch))
                self.assertTrue(all(31 <= q['min_scope'] <= 96 for q in batch))
                self.assertTrue(archive.read('ffessm-qcm/documents/Prerogatives_FFESSM_impression.pdf').startswith(b'%PDF'))
                import io
                with ZipFile(io.BytesIO(archive.read('ffessm-qcm/documents/Prerogatives_FFESSM_impression.docx'))) as word:
                    self.assertNotIn(b'/hyperlink',word.read('word/_rels/document.xml.rels'))
                    self.assertIn('Coche blanche sur fond vert',word.read('word/document.xml').decode())
                    self.assertTrue(word.read('word/media/green-check.png').startswith(b'\x89PNG'))
                for name in ['lancer-qcm.sh', 'Lancer-QCM.command', 'Lancer-QCM-Terminal.command']:
                    info = archive.getinfo('ffessm-qcm/'+name)
                    self.assertEqual((info.external_attr >> 16) & 0o777, 0o755)
                    self.assertNotIn(b'\r\n', archive.read(info))
                archive.extractall(temp)
            fresh = Quiz(Path(temp)/'ffessm-qcm')
            reference = fresh.summary()['reference']
            self.assertEqual(reference['checked_at'], '2026-11-23')
            self.assertEqual(len(reference['sections']), 6)
            self.assertTrue(any(row['status'] == 'unresolved' for row in reference['audit']))
            self.assertEqual(fresh.next()['question_id'], 1)
            self.assertEqual(fresh.status()['attempts'], 0)
            self.assertTrue((Path(temp)/'ffessm-qcm'/'preferences'/'progress.json').exists())


if __name__ == '__main__':
    unittest.main()
