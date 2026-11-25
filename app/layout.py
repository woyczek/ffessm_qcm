"""Range les anciens fichiers sans écraser les données d'une installation existante."""
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid


def tidy_legacy_root(root):
    root = Path(root).resolve()
    marker = root/'preferences'/'layout.json'
    if marker.exists() and not any((root/n).exists() for n in ('engine.py', 'bank.json', 'catalog.json', 'seed.json')):
        return []
    mapping = {
        'engine.py': 'app/engine.py', 'cli.py': 'app/cli.py', 'serve.py': 'app/serve.py',
        'pack.py': 'tools/pack.py', 'bank.json': 'questions/bank.json',
        'catalog.json': 'questions/catalog.json', 'questions-081-100.json': 'questions/questions-081-100.json',
        'bank-extension.json': 'questions/legacy/bank-extension.json',
        'seed.json': 'preferences/legacy/seed.json',
        'signalement.schema.json': 'preferences/signalement.schema.json',
        'test_engine.py': 'tests/test_engine.py', 'test_web.py': 'tests/test_web.py',
        'test_launchers.py': 'tests/test_launchers.py', 'test_distribution.py': 'tests/test_distribution.py',
        'test_ui.js': 'tests/test_ui.js', '__pycache__': 'app/legacy/__pycache__',
    }
    moved = []
    for name, relative in mapping.items():
        source = root/name
        if not source.exists():
            continue
        destination = root/relative
        if not source.resolve().is_relative_to(root) or not destination.resolve().is_relative_to(root):
            raise ValueError('Un ancien fichier pointe hors du dossier du QCM : '+name)
        if destination.exists():
            destination = destination.parent/'legacy'/f'{source.stem}-{uuid.uuid4().hex[:10]}{source.suffix}'
        if not destination.resolve().is_relative_to(root):
            raise ValueError('Destination de migration hors du QCM.')
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            source.rename(destination)
        except FileNotFoundError:
            continue  # Un second lancement a déjà rangé ce fichier.
        moved.append({'from': name, 'to': destination.relative_to(root).as_posix()})
    marker.parent.mkdir(parents=True, exist_ok=True)
    if not marker.exists() or moved:
        previous = []
        if marker.exists():
            try:
                previous = json.loads(marker.read_text(encoding='utf-8')).get('moved', [])
            except (ValueError, OSError):
                pass
        payload = {'layout_version': 1, 'updated_at': datetime.now(timezone.utc).isoformat(), 'moved': previous+moved}
        temporary = marker.with_name('layout-'+uuid.uuid4().hex+'.tmp')
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        temporary.replace(marker)
    return moved
