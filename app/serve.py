"""Interface HTML locale du QCM ; moteur commun au terminal et au navigateur."""
from __future__ import annotations

import argparse
import json
import secrets
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from engine import Quiz, QuizError


def make_server(directory, port=0):
    directory = Path(directory).resolve()
    token = secrets.token_urlsafe(32)
    lock = threading.RLock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, value, status=200):
            data = json.dumps(value, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == '/documents/Prerogatives_FFESSM_impression.pdf':
                document = directory / 'documents' / 'Prerogatives_FFESSM_impression.pdf'
                if not document.is_file():
                    return self.reply({'error': 'PDF à imprimer indisponible.'}, 404)
                data = document.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', 'application/pdf')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Content-Disposition', 'inline; filename="Prerogatives_FFESSM_impression.pdf"')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                self.wfile.write(data)
                return
            if self.path == '/assets/favicon.png':
                icon = directory / 'assets' / 'favicon.png'
                if not icon.is_file():
                    self.send_response(204)
                    self.end_headers()
                    return
                data = icon.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', 'image/png')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                self.wfile.write(data)
                return
            if self.path not in ('/', '/interface.html'):
                return self.reply({'error': 'Page introuvable.'}, 404)
            html = (directory / 'interface.html').read_text(encoding='utf-8').replace('__QCM_TOKEN__', token)
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))

        def do_POST(self):
            if self.headers.get('X-QCM-Token') != token:
                return self.reply({'error': 'Recharge la page du QCM.'}, 403)
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.reply({'error': 'Requête JSON attendue.'}, 415)
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 <= size <= 16384:
                    raise QuizError('Requête trop longue.')
                body = json.loads(self.rfile.read(size) or b'{}')
                if not isinstance(body, dict):
                    raise QuizError('Requête invalide.')
                with lock:
                    quiz = Quiz(directory)
                    if self.path == '/api/next':
                        value = quiz.next()
                    elif self.path == '/api/session':
                        value = quiz.session()
                    elif self.path == '/api/resume-latest':
                        value = quiz.resume_latest()
                    elif self.path == '/api/start-review':
                        value = quiz.start_review()
                    elif self.path == '/api/restart':
                        value = quiz.restart()
                    elif self.path == '/api/reset':
                        value = quiz.reset()
                    elif self.path == '/api/answer':
                        value = quiz.answer(body.get('letter', ''), body.get('question_id'),
                                            presentation_id=body.get('presentation_id'))
                    elif self.path == '/api/status':
                        value = quiz.status()
                    elif self.path == '/api/summary':
                        value = quiz.summary()
                    elif self.path == '/api/history':
                        value = quiz.history()
                    elif self.path == '/api/export':
                        value = quiz.state
                    else:
                        return self.reply({'error': 'Action inconnue.'}, 404)
                self.reply(value)
            except (QuizError, ValueError, TypeError, OSError) as exc:
                self.reply({'error': str(exc)}, 400)

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--data-dir', type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    try:
        Quiz(args.data_dir)
        server = make_server(args.data_dir, args.port)
        url = f'http://127.0.0.1:{server.server_port}/'
        print(f'QCM ouvert : {url}\nTu peux garder cette fenêtre réduite. Ferme-la pour arrêter le QCM.', flush=True)
        if not args.no_browser:
            threading.Timer(0.4, lambda: webbrowser.open(url)).start()
        server.serve_forever()
    except (OSError, QuizError) as exc:
        print(f'Impossible de lancer le QCM : {exc}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        if 'server' in locals():
            server.server_close()


if __name__ == '__main__':
    raise SystemExit(main())
