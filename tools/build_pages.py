"""Construit le site statique Pages sans copier les progressions personnelles."""
from pathlib import Path
import argparse
import shutil

ROOT = Path(__file__).resolve().parent.parent
PUBLIC_FILES = (
    'app/engine.py', 'app/layout.py', 'questions/bank.json',
    'questions/synthesis.json', 'assets/favicon.png',
    'documents/Prerogatives_FFESSM_impression.pdf', 'web/pages.js',
)


def build(output):
    output = Path(output).resolve()
    if output == ROOT or ROOT.is_relative_to(output):
        raise ValueError('Le dossier de sortie doit être distinct du projet.')
    if output.exists() and any(output.iterdir()):
        raise ValueError('Le dossier de sortie doit être vide : ' + str(output))
    html = (ROOT / 'interface.html').read_text(encoding='utf-8')
    old = "async function api(action,data={}){const r=await fetch('/api/'+action,{method:'POST',headers:{'Content-Type':'application/json','X-QCM-Token':token},body:JSON.stringify(data)});const v=await r.json();if(!r.ok||v.error)throw Error(v.error||'Action impossible.');return v;}"
    if html.count(old) != 1:
        raise ValueError("L'interface a changé : vérifier l'adaptateur Pages.")
    html = html.replace(old, 'async function api(action,data={}){return window.pagesApi(action,data);}')
    html = html.replace('href="/assets/', 'href="assets/')
    html = html.replace("link.href='/documents/", "link.href='documents/")
    html = html.replace('<script>', '<script src="web/pages.js"></script>\n<script>', 1)
    html = html.replace('Chargement de ta progression…', 'Chargement du moteur du QCM…')
    html = html.replace('Ton ancien historique est conservé dans un fichier de sauvegarde.',
                        'Ton ancien historique est conservé dans ce navigateur.')
    html = html.replace('<footer>', '<p class="hint">Version en ligne : progression conservée dans ce navigateur uniquement. '
                        'Utilise « Exporter la progression » pour en garder une copie. '
                        'Le premier chargement du moteur peut prendre quelques instants et nécessite Internet.</p>\n<footer>')
    output.mkdir(parents=True, exist_ok=True)
    for name in PUBLIC_FILES:
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    (output / 'index.html').write_text(html, encoding='utf-8')
    (output / '.nojekyll').touch()
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '_site')
    print(build(parser.parse_args().output))
