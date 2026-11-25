import json
import shutil
import tempfile
import io
from email.message import Message
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from engine import atomic_json
from serve import make_server


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copy(Path(__file__).resolve().parents[1]/'interface.html', self.root / 'interface.html')
        atomic_json(self.root / 'bank.json', {'version': 1, 'sources': {'test': {'reference': 'Test', 'url': 'https://example.org'}}, 'questions': [
            {'id': i, 'min_scope': 30, 'source': 'test', 'q': f'Question {i}', 'choices': ['un', 'deux', 'trois', 'quatre'], 'answer': 'B', 'choice_scores': [0.5, 1, 0, 0], 'why': 'Explication.'} for i in range(1, 11)]})
        self.server = make_server(self.root)
        handler = self.handler('/')
        handler.do_GET()
        self.html = handler.wfile.getvalue().decode()
        self.token = self.html.split("const token='")[1].split("'")[0]

    def tearDown(self):
        self.server.server_close()
        self.temp.cleanup()

    def handler(self, path):
        handler = object.__new__(self.server.RequestHandlerClass)
        handler.path = path
        handler.wfile = io.BytesIO()
        handler.headers = Message()
        handler.response_headers = {}
        handler.send_response = lambda status: setattr(handler, 'status_code', status)
        handler.send_header = lambda name, value: handler.response_headers.__setitem__(name.lower(), value)
        handler.end_headers = lambda: None
        return handler

    def post(self, action, value=None, token=None):
        handler = self.handler('/api/'+action)
        data = json.dumps(value or {}).encode()
        handler.headers['Content-Type'] = 'application/json'
        handler.headers['Content-Length'] = str(len(data))
        handler.headers['X-QCM-Token'] = self.token if token is None else token
        handler.rfile = io.BytesIO(data)
        handler.do_POST()
        result = json.loads(handler.wfile.getvalue())
        if handler.status_code >= 400:
            raise urllib.error.HTTPError('local-test', handler.status_code, result['error'], {}, None)
        return result

    def test_html_and_authenticated_api(self):
        self.assertIn('charset="utf-8"', self.html)
        self.assertNotIn('__QCM_TOKEN__', self.html)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post('next', token='wrong')
        self.assertEqual(caught.exception.code, 403)
        caught.exception.close()
        q = self.post('next')
        self.assertEqual(q['question_id'], 1)
        self.assertNotIn('answer', q)

    def test_favicon_exact_asset_route(self):
        handler = self.handler('/assets/favicon.png')
        handler.do_GET()
        self.assertEqual(handler.status_code, 204)
        (self.root/'assets').mkdir()
        data = b'\x89PNG\r\n\x1a\nexample'
        (self.root/'assets'/'favicon.png').write_bytes(data)
        handler = self.handler('/assets/favicon.png')
        handler.do_GET()
        self.assertEqual(handler.status_code, 200)
        self.assertEqual(handler.wfile.getvalue(), data)

    def test_print_pdf_exact_route_content_type_and_bytes(self):
        (self.root/'documents').mkdir()
        data = b'%PDF-1.7\nprintable-test\n%%EOF'
        (self.root/'documents'/'Prerogatives_FFESSM_impression.pdf').write_bytes(data)
        handler = self.handler('/documents/Prerogatives_FFESSM_impression.pdf')
        handler.do_GET()
        self.assertEqual(handler.status_code, 200)
        self.assertEqual(handler.response_headers['content-type'], 'application/pdf')
        self.assertEqual(handler.response_headers['content-length'], str(len(data)))
        self.assertIn('inline;', handler.response_headers['content-disposition'])
        self.assertEqual(handler.wfile.getvalue(), data)

    def test_print_pdf_missing_and_other_document_paths_remain_404(self):
        for path in ('/documents/Prerogatives_FFESSM_impression.pdf', '/documents/other.pdf',
                     '/documents/../preferences/progress.json', '/documents/Prerogatives_FFESSM_impression.pdf/extra'):
            handler = self.handler(path)
            handler.do_GET()
            self.assertEqual(handler.status_code, 404)

    def test_score_and_partial_retry_share_the_same_engine(self):
        self.post('next')
        partial = self.post('answer', {'letter': 'a', 'question_id': 1})
        self.assertEqual(partial['score'], .5)
        self.assertEqual(partial['status']['initial_acquired'], 0)
        retry = self.post('next')
        self.assertEqual(retry['question_id'], 1)
        self.assertEqual(retry['kind'], 'retry')
        self.assertEqual(self.post('export')['attempts'][0]['score'], .5)

    def test_session_reset_and_archived_restart(self):
        self.assertFalse(self.post('session')['has_history'])
        first = self.post('next')
        self.post('answer', {'letter': 'B', 'question_id': first['question_id']})
        self.post('next')
        self.assertEqual(self.post('session')['resume_question_id'], 2)
        self.assertEqual(self.post('resume-latest')['question_id'], 2)
        restarted = self.post('restart')
        self.assertTrue((self.root / restarted['backup_file']).exists())
        self.assertEqual(restarted['next']['question_id'], 1)
        reset = self.post('reset')
        self.assertEqual(reset['next']['status']['attempts'], 0)
        self.assertEqual(reset['next']['question_id'], 1)

    def test_no_self_grading_endpoint(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post('regrade', {'question_id': 1})
        self.assertEqual(caught.exception.code, 404)
        caught.exception.close()

    def test_multiple_answers_round_trip_and_partial_retry(self):
        bank_path = self.root/'bank.json'
        bank = json.loads(bank_path.read_text(encoding='utf-8'))
        bank['questions'][0].pop('choice_scores')
        bank['questions'][0]['answers'] = ['B', 'D']
        atomic_json(bank_path, bank)
        shown = self.post('next')
        self.assertFalse(shown['one_answer'])
        result = self.post('answer', {'question_id': 1, 'presentation_id': shown['presentation_id'], 'letter': 'B'})
        self.assertEqual(result['score'], .5)
        retry = self.post('next')
        correct = ','.join(k for k,v in retry['choices'].items() if v in ('deux','quatre'))
        result = self.post('answer', {'question_id': 1, 'presentation_id': retry['presentation_id'], 'letter': correct})
        self.assertEqual(result['score'], 1)
        self.assertEqual(result['status']['attempts'], 2)

    def test_start_review_and_resume_normal_pending_without_reset(self):
        first = self.post('next')
        self.post('answer', {'question_id': first['question_id'], 'presentation_id': first['presentation_id'], 'letter': 'B'})
        normal = self.post('next')
        session = self.post('session')
        self.assertTrue(session['review_available'])
        revision = self.post('start-review')
        self.assertEqual(revision['session_mode'], 'revision')
        self.assertEqual(revision['question_id'], first['question_id'])
        again = self.post('next')
        self.assertEqual(again['question_id'], first['question_id'])
        resumed = self.post('resume-latest')
        self.assertEqual(resumed['session_mode'], 'normal')
        self.assertEqual(resumed['question_id'], normal['question_id'])
        self.assertEqual(resumed['presentation_id'], normal['presentation_id'])
        self.assertEqual(self.post('status')['attempts'], 1)

    def test_review_requires_at_least_one_answer(self):
        self.assertFalse(self.post('session')['review_available'])
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post('start-review')
        self.assertEqual(caught.exception.code, 400)
        caught.exception.close()
        self.assertEqual(self.post('status')['attempts'], 0)

    def test_answer_date_visible_in_result_status_and_history(self):
        question = self.post('next')
        result = self.post('answer', {'question_id': question['question_id'], 'letter': 'B'})
        self.assertIsInstance(result['answered_at'], str)
        self.assertEqual(result['status']['last_answer_at'], result['answered_at'])
        self.assertEqual(self.post('history')[0]['at'], result['answered_at'])

    def test_unknown_imported_date_remains_unknown_in_api(self):
        atomic_json(self.root/'seed.json', {'answered': [{'question_id': 1, 'letter': 'B'}]})
        self.assertIsNone(self.post('status')['last_answer_at'])
        self.assertIsNone(self.post('history')[0]['at'])


if __name__ == '__main__':
    unittest.main()
