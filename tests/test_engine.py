import copy
import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from app.engine import Quiz, QuizError, atomic_json


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.time = datetime(2026, 11, 23, 12, tzinfo=timezone.utc)
        self.bank = {"version": 1, "checked_at": "2026-11-23", "sources": {
            "test": {"reference": "source de test", "url": "https://example.org"}}, "questions": [
            {"id": n, "min_scope": 30 if n <= 10 else 31 + (n - 11) // 2,
             "source": "test", "q": f"Question {n}", "choices": ["un", "deux", "trois", "quatre"],
             "answer": "B", "why": "Règle."} for n in range(1, 15)]}
        atomic_json(self.root / "bank.json", self.bank)

    def tearDown(self):
        self.tmp.cleanup()

    def quiz(self):
        return Quiz(self.root, now=lambda: self.time)

    def good_letter(self, shown):
        return next(k for k, text in shown["choices"].items() if text == "deux")

    def finish_initial(self, quiz):
        for _ in range(10):
            shown = quiz.next()
            quiz.answer(self.good_letter(shown))

    def test_initial_ten_no_early_growth(self):
        quiz = self.quiz()
        for n in range(10):
            shown = quiz.next()
            self.assertEqual(shown["question_id"], n + 1)
            quiz.answer("B")
            self.assertEqual(quiz.status()["scope"], 30)
        self.assertTrue(quiz.status()["initial_complete"])
        self.assertEqual(quiz.status()["growth_correct"], 0)

    def test_growth_two_correct_after_initial(self):
        quiz = self.quiz()
        self.finish_initial(quiz)
        for expected_scope in (30, 31):
            shown = quiz.next()
            self.assertEqual(shown["kind"], "review")
            quiz.answer(self.good_letter(shown))
            self.assertEqual(quiz.status()["scope"], expected_scope)
        self.assertEqual(quiz.next()["question_id"], 11)

    def test_retry_mapping_and_exclusive_status(self):
        quiz = self.quiz()
        original = quiz.next()
        quiz.answer("A")
        retry = quiz.next()
        self.assertEqual(retry["question_id"], original["question_id"])
        self.assertNotEqual(retry["choices"], original["choices"])
        quiz.answer(self.good_letter(retry))
        self.assertEqual(quiz.status()["counts"]["corrected"], 1)
        self.assertEqual(quiz.status()["counts"]["first_correct"], 0)
        self.assertEqual(quiz.status()["wrong_attempts"], 1)
        self.assertEqual(quiz.status()["initial_acquired"], 1)
        self.assertEqual(quiz.history()[1]["canonical_letter"], "B")

    def test_restart_preserves_pending_and_order(self):
        quiz = self.quiz()
        original = quiz.next()
        shown = self.quiz().next()
        self.assertEqual(shown, original)
        self.assertEqual(len(self.quiz().state["presentations"]), 1)

    def test_daily_preserves_unanswered_and_requires_id(self):
        quiz = self.quiz()
        quiz.next()
        fresh = quiz.next(daily=True)
        self.assertEqual(fresh["question_id"], 2)
        self.assertEqual(quiz.status()["wrong_attempts"], 0)
        self.assertEqual(quiz.status()["pending_ids"], [1, 2])
        with self.assertRaises(QuizError):
            quiz.answer("B")
        quiz.answer("B", question_id=2)
        self.assertEqual(quiz.next()["question_id"], 1)

    def test_daily_idempotent(self):
        quiz = self.quiz()
        p = quiz.next(daily=True)
        self.assertEqual(quiz.next(daily=True), p)
        quiz.answer("B")
        self.assertIn("déjà", quiz.next(daily=True)["message"])

    def test_daily_new_question_before_ordinary_due_review(self):
        quiz = self.quiz()
        quiz.next()
        quiz.answer("B")
        self.time += timedelta(days=8)
        shown = quiz.next(daily=True)
        self.assertEqual(shown["question_id"], 2)
        self.assertEqual(shown["kind"], "new")

    def test_failure_priority_over_pending(self):
        quiz = self.quiz()
        quiz.next()
        quiz.next(daily=True)
        quiz.answer("A", question_id=1)
        self.assertEqual(quiz.next()["question_id"], 1)

    def test_invalid_answer_does_not_write(self):
        quiz = self.quiz()
        quiz.next()
        before = quiz.path.read_bytes()
        with self.assertRaises(QuizError):
            quiz.answer("AE")
        self.assertEqual(quiz.path.read_bytes(), before)
        self.assertEqual(quiz.status()["attempts"], 0)

    def test_cannot_answer_twice(self):
        quiz = self.quiz()
        quiz.next()
        quiz.answer("B")
        with self.assertRaises(QuizError):
            quiz.answer("B", question_id=1)
        self.assertEqual(quiz.status()["attempts"], 1)

    def test_seed_unknown_historical_dates(self):
        atomic_json(self.root / "seed.json", {"answered": [
            {"question_id": n, "letter": "B"} for n in range(1, 6)], "pending_question_id": 6})
        quiz = self.quiz()
        self.assertEqual(quiz.status()["initial_acquired"], 5)
        self.assertEqual(quiz.next()["question_id"], 6)
        self.assertIsNone(quiz.history()[0]["at"])
        self.assertTrue(quiz.history()[0]["date_unknown"])
        self.assertEqual(self.quiz().status()["attempts"], 5)

    def test_due_review(self):
        quiz = self.quiz()
        quiz.next()
        quiz.answer("B")
        self.time += timedelta(days=8)
        self.assertEqual(quiz.next()["question_id"], 1)
        self.assertEqual(quiz.next()["kind"], "review")

    def test_corrected_due_after_two_other_answers(self):
        quiz = self.quiz()
        quiz.next()
        quiz.answer("A")
        shown = quiz.next()
        quiz.answer(self.good_letter(shown))
        for qid in (2, 3):
            shown = quiz.next()
            self.assertEqual(shown["question_id"], qid)
            quiz.answer(self.good_letter(shown))
        self.assertEqual(quiz.next()["question_id"], 1)

    def test_concurrent_write_detected(self):
        first = self.quiz()
        second = self.quiz()
        first.next()
        with self.assertRaises(QuizError):
            second.next()

    def test_bank_change_existing_question_rejected(self):
        self.quiz()
        changed = copy.deepcopy(self.bank)
        changed["questions"][0]["answer"] = "C"
        atomic_json(self.root / "bank.json", changed)
        with self.assertRaises(QuizError):
            self.quiz()

    def test_bank_extension_allowed(self):
        self.quiz()
        extended = copy.deepcopy(self.bank)
        q = copy.deepcopy(extended["questions"][-1])
        q["id"] = 15
        extended["questions"].append(q)
        atomic_json(self.root / "bank.json", extended)
        self.assertEqual(self.quiz().status()["questions_in_bank"], 15)

    def test_no_answer_leaked_by_next(self):
        shown = self.quiz().next()
        self.assertNotIn("answer", shown)
        self.assertNotIn("why", shown)

    def test_review_requires_an_answer_and_preserves_fresh_pending(self):
        quiz=self.quiz()
        before=quiz.path.read_bytes()
        with self.assertRaises(QuizError): quiz.start_review()
        self.assertEqual(quiz.path.read_bytes(),before)
        quiz.next()
        quiz.answer('B')
        regular=quiz.next()
        self.assertEqual(regular['question_id'],2)
        revision=quiz.start_review()
        self.assertEqual(revision['question_id'],1)
        self.assertEqual(revision['session_mode'],'revision')
        self.assertEqual(quiz.status()['attempts'],1)
        self.assertEqual(quiz.start_review()['presentation_id'],revision['presentation_id'])
        self.assertEqual(self.quiz().next(daily=True)['question_id'],1)
        quiz=self.quiz()
        current=quiz.next()
        quiz.answer(self.good_letter(current),presentation_id=current['presentation_id'])
        self.assertEqual(quiz.next()['question_id'],1)
        resumed=quiz.resume_latest()
        self.assertEqual(resumed['presentation_id'],regular['presentation_id'])
        self.assertEqual(resumed['session_mode'],'normal')
        self.assertEqual(quiz.status()['attempts'],2)

    def test_review_prioritizes_failure_and_reuses_pending_retry(self):
        quiz=self.quiz()
        quiz.next(); quiz.answer('A')
        retry=quiz.next()
        current=quiz.start_review()
        self.assertEqual(current['question_id'],1)
        self.assertEqual(current['presentation_id'],retry['presentation_id'])
        self.assertIn('Révision',current['selection_reason'])
        self.assertTrue(quiz.session()['review_available'])
        quiz.reset()
        self.assertEqual(quiz.status()['session_mode'],'normal')
        self.assertFalse(quiz.session()['review_available'])

    def test_points_dates_are_actual_answer_dates(self):
        quiz=self.quiz()
        self.assertIsNone(quiz.status()['last_answer_at'])
        quiz.next()
        result=quiz.answer('B')
        self.assertEqual(result['answered_at'],self.time.isoformat())
        self.assertEqual(quiz.status()['last_answer_at'],self.time.isoformat())
        self.assertEqual(quiz.history()[0]['at'],self.time.isoformat())

    def multi_bank(self):
        self.bank['questions'][0]['answers'] = ['B', 'D']
        atomic_json(self.root / 'bank.json', self.bank)

    def revise_question(self, qid):
        bank = json.loads((self.root / 'bank.json').read_text(encoding='utf-8'))
        question = next(q for q in bank['questions'] if q['id'] == qid)
        previous = copy.deepcopy(question)
        question.update({'q': 'Question révisée', 'answers': ['B', 'D'], 'revision': 2})
        bank['revisions'] = [{'question_id': qid, 'previous_question': previous,
            'from_fingerprint': Quiz._fingerprint(previous), 'to_fingerprint': Quiz._fingerprint(question),
            'reason': 'Passage explicite aux choix multiples.'}]
        atomic_json(self.root / 'bank.json', bank)

    def test_multiple_answers_partial_then_permuted_complete(self):
        self.multi_bank()
        quiz = self.quiz()
        shown = quiz.next()
        self.assertFalse(shown['one_answer'])
        self.assertNotIn('answers', shown)
        partial = quiz.answer(' b ')
        self.assertEqual(partial['score'], .5)
        self.assertEqual(partial['correct_letters'], ['B', 'D'])
        self.assertEqual(quiz.status()['initial_acquired'], 0)
        retry = quiz.next()
        self.assertEqual(retry['question_id'], 1)
        good = ''.join(k for k,v in retry['choices'].items() if v in ('deux', 'quatre'))
        complete = quiz.answer(good.lower())
        self.assertEqual(complete['score'], 1)
        self.assertEqual(quiz.history()[-1]['canonical_letter'], 'B,D')
        self.assertEqual(quiz.status()['counts']['corrected'], 1)
        self.assertEqual(self.quiz().status()['points'], 1.5)

    def test_multiple_answers_intruder_is_zero(self):
        self.multi_bank()
        quiz = self.quiz()
        quiz.next()
        self.assertEqual(quiz.answer('A,B,D')['score'], 0)
        self.assertEqual(quiz.status()['initial_acquired'], 0)

    def test_multiple_letters_formats_and_duplicate_normalization(self):
        for value in ('bd', ' B, D ', 'b d', 'D+B', 'B;D', 'BBD'):
            self.assertEqual(Quiz._parse_letters(value), ['B', 'D'])
        for value in ('', ' , ', 'ABX', None, ['B', 'D']):
            with self.assertRaises(QuizError):
                Quiz._parse_letters(value)

    def test_added_questions_are_interleaved_by_scope_with_stable_ids(self):
        added = copy.deepcopy(self.bank['questions'][10])
        added.update({'id':15,'min_scope':31,'q':'Nouvelle question de base'})
        self.bank['questions'].append(added)
        atomic_json(self.root/'bank.json', self.bank)
        quiz = self.quiz()
        self.assertEqual(quiz.question_number(15), 13)
        self.assertEqual(quiz.question_number(13), 14)
        self.finish_initial(quiz)
        for _ in range(2):
            shown=quiz.next()
            quiz.answer(self.good_letter(shown))
        fresh=[]
        for _ in range(3):
            shown=quiz.next()
            self.assertEqual(shown['kind'],'new')
            fresh.append(shown['question_id'])
            quiz.answer(self.good_letter(shown))
        self.assertEqual(fresh,[11,12,15])
        self.assertEqual(quiz.history()[-1]['question_number'],13)
        self.assertEqual(quiz.history()[-1]['question_id'],15)

    def test_single_answer_question_allows_multi_input_but_rejects_intruder(self):
        quiz = self.quiz()
        self.assertTrue(quiz.next()['one_answer'])
        self.assertEqual(quiz.answer('AB')['score'], 0)

    def test_legacy_partial_choice_scale_does_not_reward_combining_choices(self):
        self.bank['questions'][0]['choice_scores'] = [.5, 1, 0, 0]
        atomic_json(self.root/'bank.json', self.bank)
        quiz = self.quiz()
        quiz.next()
        self.assertEqual(quiz.answer('A')['score'], .5)
        retry = quiz.next()
        combined = ','.join(k for k,v in retry['choices'].items() if v in ('un','deux'))
        self.assertEqual(quiz.answer(combined)['score'], 0)

    def test_explicit_revision_keeps_old_scores_and_backup(self):
        quiz = self.quiz()
        for _ in range(3):
            quiz.next()
            quiz.answer('B')
        original = quiz.path.read_bytes()
        self.revise_question(3)
        updated = self.quiz()
        self.assertEqual(updated.status()['attempts'], 3)
        self.assertEqual(updated.status()['points'], 3)
        self.assertEqual(updated.status()['initial_acquired'], 3)
        self.assertEqual(updated._answer_result(updated.history()[-1])['correct_letters'], ['B'])
        backups = list(self.root.glob('progress-before-qcm-*.json'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        self.assertEqual(len(self.quiz().state['bank_migrations']), 1)
        self.assertEqual(len(list(self.root.glob('progress-before-qcm-*.json'))), 1)

    def test_pending_old_revision_keeps_display_and_grading(self):
        quiz = self.quiz()
        old = quiz.next()
        self.revise_question(1)
        updated = self.quiz()
        shown = updated.next()
        self.assertEqual(shown['question'], old['question'])
        self.assertTrue(shown['previous_revision'])
        self.assertTrue(shown['one_answer'])
        self.assertEqual(updated.answer('B')['score'], 1)
        p = updated._present(1, self.time, 'review', canonical=True)
        shown = updated.public_question(p)
        self.assertEqual(shown['question'], 'Question révisée')
        self.assertFalse(shown['one_answer'])
        self.assertEqual(updated.answer('B,D')['score'], 1)

    def test_revision_metadata_must_match_previous_question(self):
        quiz = self.quiz()
        quiz.next()
        original = quiz.path.read_bytes()
        self.revise_question(1)
        bank = json.loads((self.root/'bank.json').read_text(encoding='utf-8'))
        bank['revisions'][0]['previous_question']['answer'] = 'A'
        atomic_json(self.root/'bank.json', bank)
        with self.assertRaises(QuizError):
            self.quiz()
        self.assertEqual(quiz.path.read_bytes(), original)

    def synthesis_fixture(self):
        return {"version": "test-1", "checked_at": "2026-11-23", "title": "Référentiel de test",
                "introduction": "Les sources officielles font foi.",
                "sections": [{"id": "test", "title": "Tableau de test", "columns": ["Niveau", "Règle"],
                              "rows": [["N1", "Texte <script> littéral"]], "notes": ["Note de test"],
                              "sources": ["official"]}],
                "sources": {"official": {"reference": "Source de test", "url": "https://example.org/official",
                                         "version": "version test"}},
                "audit": [{"item": "Exemple", "supplied": "Proposition", "verified": "Vérification",
                           "status": "qualified", "source_ids": ["official"]}],
                "attachments": [{"name": "proposition.pdf", "library_file_id": "test-id", "role": "document à vérifier"}]}

    def test_summary_optional_reference_keeps_current_rules(self):
        quiz = self.quiz()
        without = quiz.summary()
        self.assertNotIn("reference", without)
        reference = self.synthesis_fixture()
        atomic_json(self.root / "synthesis.json", reference)
        before = quiz.path.read_bytes()
        value = quiz.summary()
        self.assertEqual(value["reference"], reference)
        self.assertEqual(value["rules"], without["rules"])
        self.assertEqual(value["status"], without["status"])
        self.assertEqual(quiz.path.read_bytes(), before)

    def test_project_summary_loaded_from_questions_subfolder(self):
        self.projectify()
        reference = self.synthesis_fixture()
        atomic_json(self.root / "questions" / "synthesis.json", reference)
        self.assertEqual(self.quiz().summary()["reference"]["title"], reference["title"])

    def test_summary_rejects_wrong_shape_rows_and_scalar_cells(self):
        quiz = self.quiz()
        for rows in ([["N1"]], [["N1", 20]], "N1"):
            reference = self.synthesis_fixture()
            reference["sections"][0]["rows"] = rows
            atomic_json(self.root / "synthesis.json", reference)
            with self.assertRaises(QuizError):
                quiz.summary()

    def test_summary_rejects_unknown_source_in_section_or_audit(self):
        quiz = self.quiz()
        for where in ("section", "audit"):
            reference = self.synthesis_fixture()
            if where == "section":
                reference["sections"][0]["sources"] = ["missing"]
            else:
                reference["audit"][0]["source_ids"] = ["missing"]
            atomic_json(self.root / "synthesis.json", reference)
            with self.assertRaisesRegex(QuizError, "source inconnue"):
                quiz.summary()

    def test_summary_rejects_unsafe_source_url_and_invalid_json(self):
        quiz = self.quiz()
        reference = self.synthesis_fixture()
        reference["sources"]["official"]["url"] = "javascript:alert(1)"
        atomic_json(self.root / "synthesis.json", reference)
        with self.assertRaisesRegex(QuizError, "URL HTTP"):
            quiz.summary()
        (self.root / "synthesis.json").write_text("{", encoding="utf-8")
        with self.assertRaises(QuizError):
            quiz.summary()

    def test_cli_summary_renders_reference_and_keeps_current_rules(self):
        from app import cli
        atomic_json(self.root / "synthesis.json", self.synthesis_fixture())
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(cli.main(["--data-dir", str(self.root), "summary"]), 0)
        text = output.getvalue()
        self.assertIn("Synthèse vérifiée", text)
        self.assertIn("Niveau · Règle", text)
        self.assertIn("N1 · Texte <script> littéral", text)
        self.assertIn("https://example.org/official", text)
        self.assertIn("version test", text)
        self.assertIn("Rappel du périmètre courant", text)
        self.assertIn("- Règle.", text)

    def test_partial_answer_not_acquired_and_priority(self):
        quiz = self.quiz()
        quiz.next()
        result = quiz.answer("B", score=0.5, reason="Bonne lettre, restriction ajoutée incorrecte")
        self.assertFalse(result["correct"])
        self.assertTrue(result["partial"])
        self.assertEqual(result["score"], 0.5)
        self.assertEqual(quiz.status()["initial_acquired"], 0)
        self.assertEqual(quiz.status()["counts"]["partial"], 1)
        self.assertEqual(quiz.status()["points"], 0.5)
        retry = quiz.next()
        self.assertEqual(retry["question_id"], 1)
        self.assertEqual(retry["kind"], "retry")
        quiz.answer(self.good_letter(retry))
        self.assertEqual(quiz.status()["counts"]["corrected"], 1)
        self.assertEqual(quiz.status()["counts"]["partial"], 0)
        self.assertEqual(quiz.status()["points"], 1.5)
        self.assertEqual(quiz.status()["attempts"], 2)

    def test_regrade_q6_preserves_pending_q7(self):
        quiz = self.quiz()
        for _ in range(6):
            quiz.next()
            quiz.answer("B")
        q7 = quiz.next()
        result = quiz.regrade(6, 0.5, "Restriction au milieu artificiel incorrecte")
        self.assertEqual(result["old_score"], 1)
        self.assertEqual(quiz.status()["initial_acquired"], 5)
        self.assertEqual(quiz.status()["points"], 5.5)
        self.assertEqual(quiz.status()["attempts"], 6)
        self.assertEqual(quiz.status()["counts"]["partial"], 1)
        self.assertEqual(quiz.status()["pending_ids"], [7])
        self.assertEqual(quiz.state["presentations"][-1]["id"], q7["presentation_id"])
        retry = quiz.next()
        self.assertEqual(retry["question_id"], 6)
        self.assertNotEqual(self.good_letter(retry), "B")
        quiz.answer(self.good_letter(retry), question_id=6)
        self.assertEqual(quiz.status()["initial_acquired"], 6)
        self.assertEqual(quiz.status()["counts"]["corrected"], 1)
        self.assertEqual(quiz.next()["question_id"], 7)

    def test_regrade_replays_and_removes_early_growth(self):
        quiz = self.quiz()
        self.finish_initial(quiz)
        for _ in range(2):
            shown = quiz.next()
            quiz.answer(self.good_letter(shown))
        self.assertEqual(quiz.status()["scope"], 31)
        quiz.regrade(6, 0.5, "Correction rétroactive")
        self.assertFalse(quiz.status()["initial_complete"])
        self.assertEqual(quiz.status()["initial_acquired"], 9)
        self.assertEqual(quiz.status()["scope"], 30)
        self.assertEqual(quiz.status()["growth_correct"], 0)
        self.assertEqual(quiz.status()["attempts"], 12)
        self.assertEqual(self.quiz().status()["scope"], 30)

    def test_partial_does_not_advance_growth(self):
        quiz = self.quiz()
        self.finish_initial(quiz)
        shown = quiz.next()
        quiz.answer(self.good_letter(shown))
        self.assertEqual(quiz.status()["growth_correct"], 1)
        shown = quiz.next()
        quiz.answer(self.good_letter(shown), score=0.5, reason="Réponse incomplète")
        self.assertEqual(quiz.status()["growth_correct"], 1)
        self.assertEqual(quiz.status()["scope"], 30)
        shown = quiz.next()
        quiz.answer(self.good_letter(shown))
        self.assertEqual(quiz.status()["scope"], 31)

    def test_adjudications_preserve_original_and_prior_events(self):
        quiz = self.quiz()
        quiz.next()
        quiz.answer("B")
        quiz.regrade(1, 0.5, "Première réévaluation")
        first_event = copy.deepcopy(quiz.state["adjudications"][0])
        quiz.regrade(1, 0, "Seconde réévaluation")
        self.assertEqual(quiz.state["adjudications"][0], first_event)
        self.assertEqual(quiz.history()[0]["original_score"], 1)
        self.assertTrue(quiz.history()[0]["original_correct"])
        self.assertEqual(quiz.status()["adjudications_count"], 2)
        self.assertEqual(quiz.status()["attempts"], 1)
        self.assertEqual(len(quiz.history()[0]["adjudications"]), 2)
        self.assertEqual(self.quiz().history(), quiz.history())

    def test_legacy_attempts_without_scores(self):
        quiz = self.quiz()
        quiz.next()
        quiz.answer("B")
        for attempt in quiz.state["attempts"]:
            for key in ("score", "original_score", "original_correct"):
                attempt.pop(key)
        quiz.state.pop("adjudications")
        atomic_json(quiz.path, quiz.state)
        loaded = self.quiz()
        self.assertEqual(loaded.status()["points"], 1)
        loaded.regrade(1, 0.5, "Ancien historique réévalué")
        self.assertEqual(loaded.history()[0]["original_score"], 1)

    def test_invalid_manual_score_no_mutation(self):
        quiz = self.quiz()
        quiz.next()
        before = quiz.path.read_bytes()
        for score, reason in ((0.5, None), (0.3, "motif"), (True, "motif")):
            with self.assertRaises(QuizError):
                quiz.answer("B", score=score, reason=reason)
        self.assertEqual(quiz.path.read_bytes(), before)
        self.assertEqual(quiz.status()["attempts"], 0)

    def test_daily_partial_retry_before_idempotency(self):
        quiz = self.quiz()
        quiz.next(daily=True)
        quiz.answer("B", score=0.5, reason="Incomplet")
        self.assertEqual(quiz.next(daily=True)["kind"], "retry")

    def test_cli_partial_json_and_regrade_without_ansi(self):
        import cli
        for arguments in (("next",), ("answer", "B", "--question", "1", "--score", "0.5", "--reason", "À affiner"),
                          ("regrade", "--question", "1", "--score", "0", "--reason", "Incorrect")):
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                code = cli.main(["--data-dir", str(self.root), "--json", *arguments])
            self.assertEqual(code, 0)
            self.assertNotIn("\033", stream.getvalue())
            data = json.loads(stream.getvalue())
        self.assertEqual(data["result"]["score"], 0)
        self.assertEqual(data["result"]["old_score"], 0.5)
        self.assertEqual(data["result"]["status"]["attempts"], 1)

    def test_terminal_style_explicitly_disabled_or_enabled(self):
        import cli
        old = cli.ANSI
        try:
            cli.ANSI = False
            self.assertEqual(cli.styled("Correct", color="32", bold=True), "Correct")
            cli.ANSI = True
            self.assertEqual(cli.styled("Correct", color="32", bold=True), "\033[1;32mCorrect\033[0m")
        finally:
            cli.ANSI = old

    def test_session_fresh_q1_and_readonly(self):
        quiz = self.quiz()
        before = quiz.path.read_bytes()
        state = copy.deepcopy(quiz.state)
        session = quiz.session()
        self.assertFalse(session["has_history"])
        self.assertIsNone(session["resume_question_id"])
        self.assertIsNone(session["priority_question_id"])
        self.assertEqual(quiz.path.read_bytes(), before)
        self.assertEqual(quiz.state, state)
        self.assertEqual(quiz.next()["question_id"], 1)

    def prepare_partial_q6(self):
        quiz = self.quiz()
        for _ in range(6):
            quiz.next()
            quiz.answer("B")
        quiz.next()
        quiz.regrade(6, 0.5, "Restriction incorrecte")
        return quiz

    def test_resume_explicit_latest_preserves_priority(self):
        quiz = self.prepare_partial_q6()
        before = quiz.path.read_bytes()
        session = quiz.session()
        self.assertEqual(session["resume_question_id"], 7)
        self.assertEqual(session["priority_question_id"], 6)
        self.assertIn("0,5", session["priority_reason"])
        latest = quiz.resume_latest()
        self.assertEqual(latest["question_id"], 7)
        self.assertIn("Q6", latest["selection_reason"])
        self.assertEqual(quiz.path.read_bytes(), before)
        normal = quiz.next()
        self.assertEqual(normal["question_id"], 6)
        self.assertIn("incomplète", normal["selection_reason"])
        self.assertEqual(quiz.session()["resume_question_id"], 6)
        self.assertEqual(quiz.session()["last_fresh_pending_question_id"], 7)
        self.assertEqual(self.quiz().resume_latest()["question_id"], 6)

    def test_restart_archives_exact_bytes_ignores_seed(self):
        atomic_json(self.root / "seed.json", {"answered": [
            {"question_id": n, "letter": "B"} for n in range(1, 6)], "pending_question_id": 6})
        quiz = self.quiz()
        old_bytes = quiz.path.read_bytes()
        result = quiz.restart()
        backup = Path(result["backup_file"])
        self.assertEqual(backup.read_bytes(), old_bytes)
        self.assertEqual(result["next"]["question_id"], 1)
        self.assertEqual(quiz.status()["attempts"], 0)
        self.assertEqual(quiz.status()["initial_acquired"], 0)
        self.assertEqual(self.quiz().next()["question_id"], 1)
        second = quiz.restart()
        self.assertNotEqual(second["backup_file"], str(backup))
        self.assertEqual(backup.read_bytes(), old_bytes)

    def test_bank_extension_preserves_progress_bytes(self):
        quiz = self.quiz()
        quiz.next()
        quiz.answer("B")
        quiz.next()
        old_bytes = quiz.path.read_bytes()
        extended = copy.deepcopy(self.bank)
        q = copy.deepcopy(extended["questions"][-1])
        q["id"] = 15
        extended["questions"].append(q)
        atomic_json(self.root / "bank.json", extended)
        loaded = self.quiz()
        self.assertEqual(loaded.session()["resume_question_id"], 2)
        self.assertEqual(loaded.status()["attempts"], 1)
        self.assertEqual(loaded.path.read_bytes(), old_bytes)

    def projectify(self, bank=None):
        (self.root / "questions").mkdir(exist_ok=True)
        atomic_json(self.root / "questions" / "bank.json", bank or self.bank)

    def test_project_layout_new_install_starts_q1_without_frozen_root_seed(self):
        self.projectify()
        atomic_json(self.root / "seed.json", {"answered": [
            {"question_id": n, "letter": "B"} for n in range(1, 6)], "pending_question_id": 6})
        quiz = self.quiz()
        self.assertEqual(quiz.root, self.root)
        self.assertEqual(quiz.directory, self.root / "preferences")
        self.assertEqual(quiz.bank_path, self.root / "questions" / "bank.json")
        self.assertEqual(quiz.status()["attempts"], 0)
        self.assertEqual(quiz.next()["question_id"], 1)
        self.assertTrue((self.root / "preferences" / "legacy" / "seed.json").exists())

    def test_project_migrates_legacy_progress_exactly_and_preserves_5_5_points(self):
        quiz = self.prepare_partial_q6()
        previous = quiz.path.read_bytes()
        self.projectify()
        loaded = self.quiz()
        self.assertEqual(loaded.path, self.root / "preferences" / "progress.json")
        self.assertEqual(loaded.path.read_bytes(), previous)
        self.assertFalse((self.root / "progress.json").exists())
        self.assertEqual(loaded.status()["points"], 5.5)
        self.assertEqual(loaded.status()["initial_acquired"], 5)
        self.assertEqual(loaded.status()["counts"]["partial"], 1)
        self.assertEqual(loaded.status()["pending_ids"], [7])
        self.assertEqual(loaded.next()["question_id"], 6)

    def test_project_two_different_histories_prefer_preferences_archive_legacy(self):
        quiz = self.quiz()
        quiz.next()
        quiz.answer("B")
        legacy = quiz.path.read_bytes()
        quiz.next()
        quiz.answer("B")
        preferred = quiz.path.read_bytes()
        self.projectify()
        (self.root / "preferences").mkdir()
        (self.root / "preferences" / "progress.json").write_bytes(preferred)
        (self.root / "progress.json").write_bytes(legacy)
        loaded = self.quiz()
        self.assertEqual(loaded.status()["attempts"], 2)
        self.assertEqual(loaded.path.read_bytes(), preferred)
        archives = list((self.root / "preferences").glob("progress-legacy-*.json"))
        self.assertEqual(len(archives), 1)
        self.assertEqual(archives[0].read_bytes(), legacy)
        self.assertIn(archives[0].name, loaded.session()["migration_notice"])
        self.assertIn("reste active", loaded.status()["migration_notice"])
        self.assertFalse((self.root / "progress.json").exists())
        reloaded = self.quiz()
        self.assertEqual(reloaded.session()["migration_notice"], loaded.session()["migration_notice"])
        self.assertEqual(len(list((self.root / "preferences").glob("progress-legacy-*.json"))), 1)

    def test_project_identical_legacy_duplicate_not_extra_archive(self):
        quiz = self.quiz()
        quiz.next()
        old = quiz.path.read_bytes()
        self.projectify()
        (self.root / "preferences").mkdir()
        (self.root / "preferences" / "progress.json").write_bytes(old)
        loaded = self.quiz()
        self.assertEqual(loaded.path.read_bytes(), old)
        self.assertFalse((self.root / "progress.json").exists())
        self.assertFalse(list((self.root / "preferences").glob("progress-legacy-*.json")))

    def test_project_legacy_bank_cannot_mask_new_bank(self):
        extended = copy.deepcopy(self.bank)
        question = copy.deepcopy(extended["questions"][-1])
        question["id"] = 15
        extended["questions"].append(question)
        self.projectify(extended)
        loaded = self.quiz()
        self.assertEqual(loaded.status()["questions_in_bank"], 15)
        self.assertFalse((self.root / "bank.json").exists())
        old = list((self.root / "questions" / "legacy").glob("bank-*.json"))
        self.assertEqual(len(old), 1)
        self.assertEqual(json.loads(old[0].read_text(encoding="utf-8")), self.bank)

    def test_project_archives_restart_and_reset_stay_in_preferences(self):
        quiz = self.quiz()
        quiz.next()
        quiz.answer("B")
        (self.root / "progress-old.json").write_bytes(quiz.path.read_bytes())
        self.projectify()
        loaded = self.quiz()
        self.assertTrue((self.root / "preferences" / "progress-old.json").exists())
        self.assertFalse((self.root / "progress-old.json").exists())
        result = loaded.restart()
        self.assertEqual(Path(result["backup_file"]).parent, self.root / "preferences")
        self.assertEqual(result["next"]["question_id"], 1)
        prior_backups = set((self.root / "preferences").glob("progress-*.json"))
        loaded.reset()
        self.assertEqual(loaded.path.parent, self.root / "preferences")
        self.assertEqual(set((self.root / "preferences").glob("progress-*.json")), prior_backups)
        self.assertFalse((self.root / "progress.json").exists())

    def test_project_legacy_history_prevents_seed_reimport(self):
        quiz = self.quiz()
        quiz.next()
        quiz.answer("B")
        self.projectify()
        (self.root / "preferences").mkdir()
        atomic_json(self.root / "preferences" / "seed.json", {"answered": [
            {"question_id": n, "letter": "B"} for n in range(1, 6)], "pending_question_id": 6})
        loaded = self.quiz()
        self.assertEqual(loaded.status()["attempts"], 1)
        self.assertEqual(loaded.next()["question_id"], 2)

    def test_reset_forgets_active_results_without_new_archive_or_seed(self):
        atomic_json(self.root / "seed.json", {"answered": [
            {"question_id": 1, "letter": "B"}], "pending_question_id": 2})
        quiz = self.quiz()
        quiz.answer("B", question_id=2, score=0.5, reason="Partielle")
        quiz.state["scope"] = 100
        quiz._save()
        existing_archive = self.root / "progress-old.json"
        existing_archive.write_text("ancienne archive intacte", encoding="utf-8")
        result = quiz.reset()
        self.assertEqual(result["next"]["question_id"], 1)
        self.assertNotIn("backup_file", result)
        self.assertEqual(quiz.status()["scope"], 30)
        self.assertEqual(quiz.status()["attempts"], 0)
        self.assertEqual(quiz.status()["points"], 0)
        self.assertEqual(quiz.status()["adjudications_count"], 0)
        self.assertEqual(quiz.status()["pending_ids"], [1])
        self.assertEqual(list(self.root.glob("progress-*.json")), [existing_archive])
        self.assertEqual(existing_archive.read_text(encoding="utf-8"), "ancienne archive intacte")
        self.assertEqual(self.quiz().next()["question_id"], 1)
        self.assertEqual(self.quiz().status()["attempts"], 0)

    def test_cli_reset_json(self):
        import cli
        quiz = self.quiz()
        quiz.next()
        quiz.answer("B")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(cli.main(["--data-dir", str(self.root), "--json", "reset"]), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["next"]["question_id"], 1)
        self.assertEqual(result["next"]["status"]["points"], 0)
        self.assertFalse(list(self.root.glob("progress-*.json")))

    def test_choice_scores_follow_remapped_choices(self):
        self.bank["questions"][0]["choice_scores"] = [0.5, 1, 0, 0]
        atomic_json(self.root / "bank.json", self.bank)
        quiz = self.quiz()
        quiz.next()
        first = quiz.answer("A")
        self.assertEqual(first["score"], 0.5)
        retry = quiz.next()
        letter = next(k for k, text in retry["choices"].items() if text == "un")
        self.assertEqual(quiz.answer(letter)["score"], 0.5)
        self.assertEqual(quiz.status()["initial_acquired"], 0)
        self.assertEqual(quiz.status()["adjudications_count"], 0)

    def test_invalid_choice_scores(self):
        for scores in ([0.5, 0, 1, 0], [1, 1, 0, 0], [0, 1], [False, 1, 0, 0]):
            self.bank["questions"][0]["choice_scores"] = scores
            atomic_json(self.root / "bank.json", self.bank)
            with self.assertRaises(QuizError):
                self.quiz()

    def test_interactive_lowercase_a_on_pending_q6_retry(self):
        import cli
        quiz = self.prepare_partial_q6()
        shown = quiz.next()
        self.assertEqual(shown["question_id"], 6)
        self.assertEqual(self.good_letter(shown), "A")
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch("builtins.input", side_effect=["  a  ", "quitter"]):
            self.assertEqual(cli.main(["--data-dir", str(self.root)]), 0)
        loaded = self.quiz()
        self.assertEqual(loaded.status()["attempts"], 7)
        self.assertEqual(loaded.status()["initial_acquired"], 6)
        self.assertEqual(loaded.session()["resume_question_id"], 7)
        self.assertIn("Correct", output.getvalue())

    def test_interactive_uppercase_a_on_pending_q6_retry(self):
        import cli
        quiz = self.prepare_partial_q6()
        quiz.next()
        with contextlib.redirect_stdout(io.StringIO()), patch("builtins.input", side_effect=["A", "quitter"]):
            self.assertEqual(cli.main(["--data-dir", str(self.root)]), 0)
        self.assertEqual(self.quiz().status()["initial_acquired"], 6)

    def test_interactive_other_interface_already_answered_no_double_count(self):
        import cli
        quiz = self.prepare_partial_q6()
        shown = quiz.next()
        count = 0

        def concurrent_input(_prompt):
            nonlocal count
            count += 1
            if count == 1:
                other = self.quiz()
                other.answer("A", question_id=6, presentation_id=shown["presentation_id"])
                other.next()
                return "a"
            return "quitter"

        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch("builtins.input", side_effect=concurrent_input):
            self.assertEqual(cli.main(["--data-dir", str(self.root)]), 0)
        self.assertEqual(self.quiz().status()["attempts"], 7)
        self.assertEqual(self.quiz().status()["initial_acquired"], 6)
        self.assertIn("Réponse non comptée", output.getvalue())

    def test_interactive_no_self_rating_shortcut(self):
        import cli
        with contextlib.redirect_stdout(io.StringIO()), patch("builtins.input", side_effect=["B/2", "quitter"]):
            self.assertEqual(cli.main(["--data-dir", str(self.root)]), 0)
        self.assertEqual(self.quiz().status()["attempts"], 0)

    def test_invalid_bank_error(self):
        self.bank["questions"][0]["answer"] = None
        atomic_json(self.root / "bank.json", self.bank)
        with self.assertRaises(QuizError):
            self.quiz()


if __name__ == "__main__":
    unittest.main()
