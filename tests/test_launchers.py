"""Contrôle des scripts POSIX dans un chemin comportant des espaces."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SHELL = shutil.which('sh')


@unittest.skipUnless(SHELL, 'Shell POSIX indisponible sur cette machine')
class LauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        probe = subprocess.run([SHELL, '-c', 'exit 0'], capture_output=True, timeout=10)
        if probe.returncode:
            raise unittest.SkipTest('Le shell installé ne peut pas démarrer dans cet environnement Windows restreint ; test natif macOS/Linux restant à faire.')

    def test_scripts_and_fresh_install_in_directory_with_spaces(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='qcm portable ') as temp:
            target = Path(temp) / 'dossier avec espaces'
            target.mkdir()
            for name in ['app/engine.py', 'app/cli.py', 'app/layout.py', 'questions/bank.json', 'lancer-qcm.sh', 'Lancer-QCM.command', 'Lancer-QCM-Terminal.command']:
                (target/name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(source/name, target/name)
            env = dict(os.environ, QCM_PYTHON=Path(sys.executable).as_posix())
            for name in ['lancer-qcm.sh', 'Lancer-QCM.command', 'Lancer-QCM-Terminal.command']:
                subprocess.run([SHELL, '-n', (target/name).as_posix()], check=True, capture_output=True, timeout=10)
            run = subprocess.run([SHELL, (target/'lancer-qcm.sh').as_posix(), '--terminal', '--json', 'next'], env=env, capture_output=True, text=True, encoding='utf-8', timeout=15)
            self.assertEqual(run.returncode, 0, run.stderr)
            first = json.loads(run.stdout)
            self.assertEqual(first['question_id'], 1)
            self.assertEqual(first['status']['attempts'], 0)
            run = subprocess.run([SHELL, (target/'Lancer-QCM-Terminal.command').as_posix(), '--json', 'next'], env=env, capture_output=True, text=True, encoding='utf-8', timeout=15)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout)['presentation_id'], first['presentation_id'])


if __name__ == '__main__':
    unittest.main()
