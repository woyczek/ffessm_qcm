"""Fabrique une distribution du QCM sans aucune progression personnelle."""
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
import argparse
import stat

ROOT = Path(__file__).resolve().parent.parent
FILES = ['app/engine.py', 'app/cli.py', 'app/serve.py', 'app/layout.py', 'interface.html', 'README.md',
         'Lancer-QCM.cmd', 'Lancer-QCM-Terminal.cmd', 'lancer-qcm.sh',
         'Lancer-QCM.command', 'Lancer-QCM-Terminal.command', 'questions/bank.json',
         'questions/catalog.json', 'questions/questions-081-100.json', 'questions/questions-101-140.json',
         'questions/synthesis.json', 'assets/favicon.png', 'preferences/signalement.schema.json',
         'documents/Prerogatives_FFESSM_impression.docx', 'documents/Prerogatives_FFESSM_impression.pdf',
         'tests/__init__.py', 'tests/test_engine.py', 'tests/test_web.py', 'tests/test_ui.js', 'tests/test_launchers.py',
         'tests/test_distribution.py', 'tests/test_layout.py', 'tools/pack.py']


def build(output):
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        for name in FILES:
            source = ROOT/name
            info = ZipInfo.from_file(source, arcname='ffessm-qcm/'+name)
            info.create_system = 3
            mode = 0o755 if name.endswith(('.sh', '.command')) else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.compress_type = ZIP_DEFLATED
            data = source.read_bytes()
            if name.endswith(('.sh', '.command')):
                data = data.replace(b'\r\n', b'\n')
            archive.writestr(info, data)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT.parent/'FFESSM-QCM-1.7.0.zip')
    args = parser.parse_args()
    build(args.output)
    print(args.output)
