"""Moteur local de QCM : banque indépendante, journal des tentatives et reprises."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit


class QuizError(ValueError):
    pass


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise QuizError(f"Lecture impossible de {path}: {exc}") from exc


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=".progress-", suffix=".tmp", delete=False) as f:
            name = f.name
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def parse_time(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError("fuseau horaire manquant")
        return result
    except (ValueError, AttributeError) as exc:
        raise QuizError(f"Date ISO avec fuseau invalide : {value}") from exc


class Quiz:
    INITIAL_IDS = tuple(range(1, 11))

    def __init__(self, data_dir, now=None):
        self.root = Path(data_dir)
        self.clock = now or (lambda: datetime.now(timezone.utc))
        self.project_layout = ((self.root / "questions" / "bank.json").is_file()
                               or ((self.root / "questions").is_dir()
                                   and (self.root / "app" / "engine.py").is_file()))
        self.directory = self.root / "preferences" if self.project_layout else self.root
        self.path = self.directory / "progress.json"
        self.bank_path = (self.root / "questions" / "bank.json" if self.project_layout
                          else self.root / "bank.json")
        self.migration_notes = []
        self.migration_notice = None
        if self.project_layout:
            self.directory.mkdir(parents=True, exist_ok=True)
            self._migrate_legacy_progress()
            try:
                from .layout import tidy_legacy_root
            except ImportError:
                try:
                    from layout import tidy_legacy_root
                except ImportError:
                    tidy_legacy_root = None
            if tidy_legacy_root is not None:
                tidy_legacy_root(self.root)
            notice_path = self.directory / "migration-notice.json"
            if notice_path.exists():
                try:
                    self.migration_notice = read_json(notice_path).get("notice")
                except QuizError:
                    pass
        self.bank = read_json(self.bank_path)
        self.questions = {}
        self._validate_bank()
        self.question_numbers = {q['id']: n for n, q in enumerate(
            sorted(self.questions.values(), key=lambda q: (q['min_scope'], q['id'])), 1)}
        self._disk_hash = self._current_hash()
        if self.path.exists():
            self.state = read_json(self.path)
            original = copy.deepcopy(self.state)
            migrated = self._migrate_question_revisions()
            self._validate_state()
            self._rebuild_results()
            if migrated:
                self._backup_before_revision(original)
                self._save()
            if self.state.get("bank_migrations"):
                self.migration_notice = self.state["bank_migrations"][-1]["notice"]
        else:
            self.state = self._blank_state()
            if (self.directory / "seed.json").exists():
                self._seed(read_json(self.directory / "seed.json"))
            self._save()

    def _migrate_legacy_progress(self):
        """Move known legacy histories without overwriting the preferred active history."""
        candidates = [self.root / "progress.json"]
        candidates.extend(sorted(self.root.glob("progress-*.json")))
        for source in candidates:
            if not source.is_file():
                continue
            payload = source.read_bytes()
            target = self.directory / source.name
            active_conflict = False
            if target.exists():
                if target.read_bytes() == payload:
                    # Remove only the exact duplicate whose bytes are already durably present.
                    if source.read_bytes() != payload:
                        raise QuizError("L'historique ancien a changé pendant sa migration ; relance le programme.")
                    source.unlink()
                    self.migration_notes.append(f"Doublon historique rangé : {source.name}.")
                    continue
                active_conflict = source.name == "progress.json"
                stamp = self.now().astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                digest = hashlib.sha256(payload).hexdigest()[:12]
                label = "progress-legacy" if source.name == "progress.json" else source.stem + "-legacy"
                base = self.directory / f"{label}-{stamp}-{digest}.json"
                target = base
                suffix = 0
                while target.exists():
                    if target.read_bytes() == payload:
                        break
                    suffix += 1
                    target = base.with_name(f"{base.stem}-{suffix}.json")
            if not target.exists():
                with target.open("xb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
            if target.read_bytes() != payload or source.read_bytes() != payload:
                raise QuizError("Vérification de migration impossible ; les fichiers ont été conservés.")
            source.unlink()
            self.migration_notes.append(f"Historique conservé dans preferences/{target.name}.")
            if active_conflict:
                self.migration_notice = (
                    "Deux historiques différents ont été détectés. La progression dans preferences/progress.json "
                    f"reste active ; l'ancien historique de la racine est conservé dans preferences/{target.name}.")
                atomic_json(self.directory / "migration-notice.json",
                            {"notice": self.migration_notice, "at": self.now().isoformat(),
                             "preserved_legacy_file": target.name})

    def _blank_state(self):
        return {"schema_version": 1, "scope": 30, "initial_complete": False,
                "session_mode": "normal",
                "growth_correct": 0, "presentations": [], "attempts": [],
                "records": {}, "new_since_review": 0, "daily": {}, "adjudications": [],
                "question_fingerprints": {str(k): self._fingerprint(q)
                                          for k, q in self.questions.items()}}

    def now(self):
        value = self.clock()
        if value.tzinfo is None:
            raise QuizError("L'horloge doit fournir une date avec fuseau.")
        return value

    def _current_hash(self):
        return hashlib.sha256(self.path.read_bytes()).hexdigest() if self.path.exists() else None

    @staticmethod
    def _fingerprint(q):
        return hashlib.sha256(json.dumps(q, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    @staticmethod
    def _correct_answers(q):
        return set(q.get("answers", [q["answer"]]))

    @staticmethod
    def _parse_letters(value):
        if not isinstance(value, str):
            raise QuizError("Coche une ou plusieurs réponses A–D.")
        compact = re.sub(r"[\s,;+]+", "", value.upper())
        if not compact or any(c not in "ABCD" for c in compact):
            raise QuizError("Choisis une ou plusieurs lettres A–D, par exemple A,C.")
        return sorted(set(compact))

    def _question_for(self, presentation):
        return presentation.get("question_snapshot", self.questions[presentation["question_id"]])

    def question_number(self, question_id):
        return self.question_numbers[question_id]

    def _migrate_question_revisions(self):
        """Accept only an explicitly recorded old-to-new fingerprint transition.

        Existing presentations retain the question and grading that were displayed.
        Acquired scores and the number of attempts are never recomputed from new keys.
        """
        changes = []
        for key, fingerprint in self.state.get("question_fingerprints", {}).items():
            qid = int(key)
            if qid not in self.questions:
                continue  # Normal state validation reports the missing question.
            current = self._fingerprint(self.questions[qid])
            if current == fingerprint:
                continue
            revision = next((r for r in self.bank.get("revisions", [])
                             if r["question_id"] == qid and r["from_fingerprint"] == fingerprint
                             and r["to_fingerprint"] == current), None)
            if revision is None:
                raise QuizError(f"La question {key} a changé ; migration explicite nécessaire.")
            changes.append((key, revision))
        if not changes:
            return False
        for key, revision in changes:
            for presentation in self.state["presentations"]:
                if presentation["question_id"] == int(key):
                    presentation.setdefault("question_snapshot", copy.deepcopy(revision["previous_question"]))
            self.state["question_fingerprints"][key] = revision["to_fingerprint"]
        notice = ("QCM à choix multiples : questions N1/N2 reformulées. Les notes déjà acquises sont conservées ; "
                  "une présentation ancienne encore ouverte garde son énoncé et son barème.")
        self.state.setdefault("bank_migrations", []).append({
            "version": self.bank.get("version"), "at": self.now().isoformat(),
            "question_ids": [int(key) for key, _ in changes], "notice": notice})
        self.migration_notes.append(notice)
        return True

    def _backup_before_revision(self, original):
        payload = self.path.read_bytes()
        if self._current_hash() != self._disk_hash or read_json(self.path) != original:
            raise QuizError("La progression a changé pendant la migration. Relance le programme.")
        backup = self.directory / f"progress-before-qcm-{self._disk_hash[:16]}.json"
        if backup.exists():
            if backup.read_bytes() != payload:
                raise QuizError("Une sauvegarde différente existe déjà ; migration arrêtée.")
        else:
            with backup.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())

    def _validate_bank(self):
        if not isinstance(self.bank, dict) or not isinstance(self.bank.get("sources"), dict):
            raise QuizError("La banque doit contenir sources et questions.")
        for q in self.bank.get("questions", []):
            if (not isinstance(q, dict) or type(q.get("id")) is not int or q["id"] < 1
                    or q["id"] in self.questions):
                raise QuizError("Identifiant de question manquant, invalide ou dupliqué.")
            if (not isinstance(q.get("choices"), list) or len(q["choices"]) != 4
                    or not all(isinstance(c, str) and c.strip() for c in q["choices"])
                    or len(set(q["choices"])) != 4 or not isinstance(q.get("answer"), str)
                    or q.get("answer") not in "ABCD"
                    or len(q["answer"]) != 1 or not isinstance(q.get("q"), str)
                    or not isinstance(q.get("why"), str)
                    or q.get("source") not in self.bank["sources"]
                    or type(q.get("min_scope")) is not int or not 30 <= q["min_scope"] <= 100):
                raise QuizError(f"Question {q['id']} invalide.")
            self.questions[q["id"]] = q
            if "answers" in q and (not isinstance(q["answers"], list) or not q["answers"]
                    or any(a not in ("A", "B", "C", "D") for a in q["answers"])
                    or len(set(q["answers"])) != len(q["answers"])
                    or q["answer"] not in q["answers"]):
                raise QuizError(f"Réponses multiples invalides pour la question {q['id']}.")
            if "choice_scores" in q:
                scores = q["choice_scores"]
                if (not isinstance(scores, list) or len(scores) != 4
                        or any(type(s) not in (int, float) or s not in (0, 0.5, 1) for s in scores)
                        or len(self._correct_answers(q)) != 1
                        or scores.count(1) != 1 or scores["ABCD".index(q["answer"])] != 1):
                    raise QuizError(f"Barème des choix invalide pour la question {q['id']}.")
        for revision in self.bank.get("revisions", []):
            if (not isinstance(revision, dict) or revision.get("question_id") not in self.questions
                    or not isinstance(revision.get("previous_question"), dict)
                    or revision["previous_question"].get("id") != revision["question_id"]
                    or self._fingerprint(revision["previous_question"]) != revision.get("from_fingerprint")
                    or self._fingerprint(self.questions[revision["question_id"]]) != revision.get("to_fingerprint")
                    or not isinstance(revision.get("reason"), str) or not revision["reason"].strip()):
                raise QuizError("Migration de banque invalide.")
        if any(qid not in self.questions or self.questions[qid]["min_scope"] > 30
               for qid in self.INITIAL_IDS):
            raise QuizError("Les questions initiales 1 à 10 doivent exister au périmètre 30 %.")

    def _validate_state(self):
        s = self.state
        if s.get('session_mode','normal') not in ('normal','revision'):
            raise QuizError('Mode de session inconnu.')
        if (s.get("schema_version") != 1 or type(s.get("scope")) is not int
                or not 30 <= s["scope"] <= 100 or s.get("growth_correct") not in (0, 1)
                or not isinstance(s.get("attempts"), list)
                or not isinstance(s.get("presentations"), list)
                or not isinstance(s.get("records"), dict)):
            raise QuizError("Format du fichier de progression invalide.")
        for key, fingerprint in s.get("question_fingerprints", {}).items():
            if int(key) not in self.questions or self._fingerprint(self.questions[int(key)]) != fingerprint:
                raise QuizError(f"La question {key} a changé ; migration explicite nécessaire.")
        seen = set()
        for p in s["presentations"]:
            if (p.get("question_id") not in self.questions or p.get("id") in seen
                    or sorted(p.get("order", [])) != [0, 1, 2, 3]
                    or type(p.get("answered")) is not bool):
                raise QuizError("Présentation enregistrée invalide.")
            seen.add(p["id"])
            parse_time(p["at"])
        answered = [a["presentation_id"] for a in s["attempts"]]
        if len(set(answered)) != len(answered) or not set(answered).issubset(seen):
            raise QuizError("Tentatives dupliquées ou sans présentation.")
        if any(str(k) not in s["records"] for k in
               [a["question_id"] for a in s["attempts"]]):
            raise QuizError("Résultats incomplets.")

    def _save(self):
        if self._current_hash() != self._disk_hash:
            raise QuizError("La progression a changé dans un autre processus. Relance la commande.")
        atomic_json(self.path, self.state)
        self._disk_hash = self._current_hash()

    def _seed(self, seed):
        if not isinstance(seed, dict) or not isinstance(seed.get("answered", []), list):
            raise QuizError("seed.json invalide.")
        for row in seed.get("answered", []):
            qid = row.get("question_id")
            if qid not in self.questions:
                raise QuizError("Question de reprise inconnue.")
            at = parse_time(row["at"]) if row.get("at") else self.now()
            p = self._present(qid, at, "seed", canonical=True)
            self._answer(row.get("letter", ""), p, at)
            if not row.get("at"):
                self.state["attempts"][-1]["at"] = None
                self.state["attempts"][-1]["imported_at"] = at.isoformat()
                self.state["attempts"][-1]["date_unknown"] = True
        qid = seed.get("pending_question_id")
        if qid is not None:
            if qid not in self.questions or not self._accessible(self.questions[qid]):
                raise QuizError("Question en attente de reprise inaccessible.")
            self._present(qid, self.now(), "new", canonical=True)

    def _record(self, qid):
        return self.state["records"].setdefault(str(qid),
            {"status": "unseen", "wrong": 0, "partial": 0, "correct": 0,
             "due_dates": [], "due_after_attempt": None})

    def _accessible(self, q):
        return q["min_scope"] <= self.state["scope"] and (
            self.state["initial_complete"] or q["id"] in self.INITIAL_IDS)

    def _present(self, qid, at, kind, canonical=False):
        self.state["question_fingerprints"].setdefault(str(qid), self._fingerprint(self.questions[qid]))
        prior = sum(p["question_id"] == qid for p in self.state["presentations"])
        offset = 0 if canonical else prior % 4
        order = [(i + offset) % 4 for i in range(4)]
        p = {"id": len(self.state["presentations"]) + 1, "question_id": qid,
             "at": at.isoformat(), "kind": kind, "order": order, "answered": False}
        self.state["presentations"].append(p)
        rec = self._record(qid)
        if rec["status"] == "unseen":
            rec["status"] = "pending"
        return p

    def public_question(self, p):
        q = self._question_for(p)
        session = self.session()
        number = self.question_number(q['id'])
        reason = session["priority_reason"] if q["id"] == session["priority_question_id"] else (
            f"Q{number} : révision programmée." if p["kind"] == "review" else
            f"Q{number} : question enregistrée en attente de réponse.")
        if self.state.get('session_mode','normal') == 'revision':
            reason = f"Révision — question {number} déjà répondue. " + (session['priority_reason'] or '')
        return {"question_id": q["id"], "question_number": number, "presentation_id": p["id"], "kind": p["kind"],
                "session_mode": self.state.get('session_mode','normal'),
                "question": q["q"], "choices": dict(zip("ABCD", [q["choices"][i] for i in p["order"]])),
                "one_answer": len(self._correct_answers(q)) == 1, "selection_reason": reason, "status": self.status(),
                "previous_revision": self._fingerprint(q) != self._fingerprint(self.questions[q["id"]])}

    def session(self):
        """Describe the real saved session without changing any presentation or result."""
        pending = [p for p in self.state["presentations"] if not p["answered"] and p['kind'] != 'revision']
        latest = max(pending, key=lambda p: p["id"], default=None)
        fresh = max((p for p in pending if p["kind"] in ("new", "seed")),
                    key=lambda p: p["id"], default=None)
        priorities = sorted((int(k) for k, r in self.state["records"].items()
                            if r["status"] in ("failed", "partial")), key=self.question_number)
        priority_id = priorities[0] if priorities else None
        reason = None
        if priority_id is not None:
            rec = self.state["records"][str(priority_id)]
            detail = "réponse incomplète à 0,5 point" if rec["status"] == "partial" else "réponse incorrecte à 0 point"
            reason = f"Q{self.question_number(priority_id)} en reprise : {detail}."
        last = max(self.state["presentations"], key=lambda p: p["id"], default=None)
        return {"has_history": bool(self.state["attempts"] or self.state["presentations"]),
                "resume_question_id": latest["question_id"] if latest else None,
                "last_presented_question_id": last["question_id"] if last else None,
                "last_fresh_pending_question_id": fresh["question_id"] if fresh else None,
                "priority_question_id": priority_id, "priority_reason": reason,
                "resume_question_number": self.question_number(latest['question_id']) if latest else None,
                "last_presented_question_number": self.question_number(last['question_id']) if last else None,
                "priority_question_number": self.question_number(priority_id) if priority_id is not None else None,
                "review_available": bool(self.state['attempts']),
                "session_mode": self.state.get('session_mode','normal'),
                "migration_notes": list(self.migration_notes), "migration_notice": self.migration_notice,
                "status": self.status()}

    def resume_latest(self):
        """An explicit user choice: continue the most recently presented pending item."""
        if self.state.get('session_mode','normal') != 'normal':
            self.state['session_mode'] = 'normal'
            self._save()
        pending = [p for p in self.state["presentations"] if not p["answered"] and p['kind'] != 'revision']
        if not pending:
            return self.next()
        p = max(pending, key=lambda item: item["id"])
        result = self.public_question(p)
        result["resume_override"] = True
        session = self.session()
        priority_id = session["priority_question_id"]
        if priority_id is not None and priority_id != p["question_id"]:
            result["selection_reason"] = (f"Q{self.question_number(p['question_id'])} : reprise explicite du dernier point enregistré. "
                                          f"Q{self.question_number(priority_id)} reste à reprendre en priorité.")
        return result

    def start_review(self):
        """Start a review of answered questions without discarding the regular pending item."""
        if not self.state['attempts']:
            raise QuizError('Réponds à au moins une question avant de commencer une révision.')
        if self.state.get('session_mode','normal') != 'revision':
            self.state['session_mode'] = 'revision'
            self._save()
        return self._next_revision()

    def _next_revision(self):
        seen = {a['question_id'] for a in self.state['attempts']}
        if not seen:
            raise QuizError('Aucune question déjà répondue à réviser.')
        pending = [p for p in self.state['presentations'] if not p['answered']]
        failures = [qid for qid in seen if self._record(qid)['status'] in ('failed','partial')]
        if failures:
            qid = min(failures,key=self.question_number)
        else:
            previous = next((p for p in reversed(pending) if p['kind']=='revision'),None)
            if previous is not None:
                return self.public_question(previous)
            qid = self._least_recent(seen)
        previous = next((p for p in reversed(pending) if p['question_id']==qid),None)
        if previous is not None:
            return self.public_question(previous)
        presentation = self._present(qid,self.now(),'revision')
        self._save()
        return self.public_question(presentation)

    def restart(self):
        """Explicit reset only: archive original bytes, ignore seed, then present Q1."""
        if self._current_hash() != self._disk_hash:
            raise QuizError("La progression a changé dans un autre processus. Relance la commande.")
        stamp = self.now().astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        base = self.directory / f"progress-{stamp}.json"
        backup = base
        suffix = 0
        while backup.exists():
            suffix += 1
            backup = base.with_name(f"{base.stem}-{suffix}.json")
        original = self.path.read_bytes() if self.path.exists() else None
        if original is not None:
            with backup.open("xb") as stream:
                stream.write(original)
                stream.flush()
                os.fsync(stream.fileno())
        previous = self.state
        self.state = self._blank_state()
        try:
            self._save()
        except Exception:
            self.state = previous
            raise
        return {"backup_file": str(backup) if original is not None else None,
                "message": "Nouvelle session vierge : reprise à la question 1.", "next": self.next()}

    def reset(self):
        """Explicitly forget active answers, without creating or deleting any archive."""
        previous = self.state
        self.state = self._blank_state()
        try:
            self._save()
        except Exception:
            self.state = previous
            raise
        return {"message": "Réponses et scores de la session active oubliés : retour à Q1, périmètre 30 %.",
                "next": self.next()}

    def next(self, daily=False):
        if self.state.get('session_mode','normal') == 'revision':
            return self._next_revision()
        at = self.now()
        # Daily is idempotent, and never creates multiple presentations of the same pending item.
        day = at.astimezone().date().isoformat()
        failures = [int(k) for k, r in self.state["records"].items() if r["status"] in ("failed", "partial")]
        if daily and day in self.state["daily"] and not failures:
            pid = self.state["daily"][day]
            old = next(p for p in self.state["presentations"] if p["id"] == pid)
            if not old["answered"]:
                return self.public_question(old)
            return {"message": "La question quotidienne a déjà reçu une réponse.", "status": self.status()}
        pending = [p for p in self.state["presentations"] if not p["answered"] and p['kind'] != 'revision']
        if failures:
            qid = min(failures, key=self.question_number)
            old = next((p for p in reversed(pending) if p["question_id"] == qid), None)
            if old:
                return self.public_question(old)
            kind = "retry"
        elif pending and not daily:
            return self.public_question(pending[-1])
        else:
            due = []
            for k, rec in self.state["records"].items():
                q = self.questions[int(k)]
                if not self._accessible(q) or any(p["question_id"] == q["id"] for p in pending):
                    continue
                if (any(parse_time(d) <= at for d in rec["due_dates"])
                        or rec.get("due_after_attempt") is not None
                        and len(self.state["attempts"]) >= rec["due_after_attempt"]):
                    due.append(q["id"])
            fresh = [q["id"] for q in sorted(self.questions.values(), key=lambda q:(q['min_scope'],q['id']))
                     if self._accessible(q)
                     and self.state["records"].get(str(q["id"]), {}).get("status", "unseen") == "unseen"]
            learned = [int(k) for k, r in self.state["records"].items()
                       if r["status"] in ("first_correct", "corrected") and self._accessible(self.questions[int(k)])
                       and not any(p["question_id"] == int(k) for p in pending)]
            if due and not (daily and fresh):
                qid, kind = min(due, key=self.question_number), "review"
            elif (not daily and self.state["initial_complete"] and learned
                  and self.state["new_since_review"] >= 3):
                qid, kind = self._least_recent(learned), "review"
            elif fresh:
                qid, kind = fresh[0], "new"
            elif self.state["initial_complete"] and learned:
                qid, kind = self._least_recent(learned), "review"
            elif pending:
                return self.public_question(pending[-1])
            else:
                return {"message": "Aucune question accessible. La banque doit être complétée.", "status": self.status()}
        p = self._present(qid, at, kind)
        if daily:
            self.state["daily"][day] = p["id"]
        self._save()
        return self.public_question(p)

    def _least_recent(self, ids):
        last = {qid: 0 for qid in ids}
        for a in self.state["attempts"]:
            if a["question_id"] in last:
                last[a["question_id"]] = a["presentation_id"]
        return min(ids, key=lambda qid: (last[qid], qid))

    @staticmethod
    def _check_score(score, reason):
        if score is not None:
            if type(score) not in (int, float) or score not in (0, 0.5, 1):
                raise QuizError("Le score doit être 0, 0.5 ou 1.")
            if not isinstance(reason, str) or not reason.strip():
                raise QuizError("Une correction manuelle exige un motif --reason.")

    @staticmethod
    def _score(attempt):
        return attempt.get("score", 1 if attempt["correct"] else 0)

    def answer(self, letter, question_id=None, score=None, reason=None, presentation_id=None):
        self._check_score(score, reason)
        letter = ",".join(self._parse_letters(letter))
        pending = [p for p in self.state["presentations"] if not p["answered"]
                   and (question_id is None or p["question_id"] == question_id)
                   and (presentation_id is None or p["id"] == presentation_id)]
        if presentation_id is None and question_id is not None and len(pending)>1:
            revision = self.state.get('session_mode','normal') == 'revision'
            active = [p for p in pending if (p['kind']=='revision') == revision]
            if len(active)==1:
                pending=active
        if len(pending) != 1:
            raise QuizError("Plusieurs questions sont en attente : précise --question ID." if pending
                            else "Aucune question correspondante en attente. Utilise next.")
        result = self._answer(letter, pending[0], self.now(), score, reason)
        self._save()
        return result

    def _answer(self, letter, p, at, score=None, reason=None):
        letters = self._parse_letters(letter)
        letter = ",".join(letters)
        q = self._question_for(p)
        selected = {"ABCD"[p["order"]["ABCD".index(value)]] for value in letters}
        expected = self._correct_answers(q)
        canonical = ",".join(sorted(selected))
        automatic_score = (1 if selected == expected else 0.5 if selected < expected else 0)
        if "choice_scores" in q and len(selected) == 1:
            automatic_score = q["choice_scores"]["ABCD".index(canonical)]
        effective_score = automatic_score if score is None else score
        p["answered"] = True
        attempt = {"presentation_id": p["id"], "question_id": q["id"],
            "at": at.isoformat(), "letter": letter, "canonical_letter": canonical,
            "correct": effective_score == 1, "score": effective_score,
            "original_score": automatic_score, "original_correct": automatic_score == 1,
            "kind": p["kind"]}
        self.state["attempts"].append(attempt)
        if score is not None:
            self._adjudicate(attempt, automatic_score, effective_score, reason, at, "answer")
        self._rebuild_results()
        result = self._answer_result(attempt)
        if score is not None:
            result["reason"] = reason.strip()
        return result

    def _adjudicate(self, attempt, old_score, new_score, reason, at, kind):
        self.state.setdefault("adjudications", []).append({
            "presentation_id": attempt["presentation_id"], "question_id": attempt["question_id"],
            "old_score": old_score, "new_score": new_score, "reason": reason.strip(),
            "at": at.isoformat(), "kind": kind})

    def regrade(self, question_id, score, reason):
        self._check_score(score, reason)
        if score is None:
            raise QuizError("Le score est requis pour une réévaluation.")
        attempt = next((a for a in reversed(self.state["attempts"])
                        if a["question_id"] == question_id), None)
        if attempt is None:
            raise QuizError("Aucune tentative à réévaluer pour cette question.")
        old_score = self._score(attempt)
        attempt.setdefault("original_score", old_score)
        attempt.setdefault("original_correct", attempt["correct"])
        self._adjudicate(attempt, old_score, score, reason, self.now(), "regrade")
        attempt["score"] = score
        attempt["correct"] = score == 1
        self._rebuild_results()
        self._save()
        result = self._answer_result(attempt)
        result.update({"regraded": True, "old_score": old_score, "reason": reason.strip()})
        return result

    def _rebuild_results(self):
        """Replay effective scores; preserve original attempts, presentations and adjudications."""
        self.state.update({"scope": 30, "initial_complete": False, "growth_correct": 0,
                           "new_since_review": 0, "records": {}})
        presentations = {p["id"]: p for p in self.state["presentations"]}
        for index, attempt in enumerate(self.state["attempts"], start=1):
            score = self._score(attempt)
            if score not in (0, 0.5, 1):
                raise QuizError("Score historique invalide.")
            p = presentations[attempt["presentation_id"]]
            at = parse_time(attempt.get("at") or attempt.get("imported_at") or p["at"])
            rec = self._record(attempt["question_id"])
            was_learned = rec["status"] in ("first_correct", "corrected")
            had_failure = bool(rec["wrong"] or rec["partial"])
            was_initial_complete = self.state["initial_complete"]
            if score == 1:
                rec["correct"] += 1
                rec["status"] = "corrected" if had_failure else "first_correct"
                if not was_learned:
                    offsets = (3, 7, 14) if had_failure else (7, 21)
                    rec["due_dates"] = [(at + timedelta(days=n)).isoformat() for n in offsets]
                    rec["due_after_attempt"] = index + 2 if had_failure else None
                else:
                    rec["due_dates"] = [d for d in rec["due_dates"] if parse_time(d) > at]
                    rec["due_after_attempt"] = None
                if p["kind"] in ("new", "seed"):
                    self.state["new_since_review"] += 1
                else:
                    self.state["new_since_review"] = 0
                if all(self._record(qid)["status"] in ("first_correct", "corrected") for qid in self.INITIAL_IDS):
                    self.state["initial_complete"] = True
                if was_initial_complete:
                    self.state["growth_correct"] += 1
                    if self.state["growth_correct"] == 2:
                        self.state["scope"] = min(100, self.state["scope"] + 1)
                        self.state["growth_correct"] = 0
            elif score == 0.5:
                rec["partial"] += 1
                rec["status"] = "partial"
            else:
                rec["wrong"] += 1
                rec["status"] = "failed"
        for p in self.state["presentations"]:
            rec = self._record(p["question_id"])
            if not p["answered"] and rec["status"] == "unseen":
                rec["status"] = "pending"

    def _answer_result(self, attempt):
        p = next(p for p in self.state["presentations"] if p["id"] == attempt["presentation_id"])
        q = self._question_for(p)
        correct_letters = sorted("ABCD"[p["order"].index("ABCD".index(letter))]
                                 for letter in self._correct_answers(q))
        correct_letter = ", ".join(correct_letters)
        score = self._score(attempt)
        return {"question_id": q["id"], "question_number": self.question_number(q['id']), "correct": score == 1, "partial": score == 0.5,
                "score": score, "correct_letter": correct_letter, "correct_letters": correct_letters,
                "answered_at": attempt.get('at'),
                "explanation": q["why"], "source": self.bank["sources"][q["source"]],
                "status": self.status()}

    def status(self):
        counts = {"unseen": 0, "pending": 0, "first_correct": 0, "failed": 0, "partial": 0, "corrected": 0}
        for qid in self.questions:
            counts[self.state["records"].get(str(qid), {}).get("status", "unseen")] += 1
        initial = sum(self.state["records"].get(str(qid), {}).get("status") in
                      ("first_correct", "corrected") for qid in self.INITIAL_IDS)
        return {"scope": self.state["scope"], "initial_acquired": initial, "initial_total": 10,
                "session_mode": self.state.get('session_mode','normal'),
                "last_answer_at": self.state['attempts'][-1].get('at') if self.state['attempts'] else None,
                "initial_complete": self.state["initial_complete"], "growth_correct": self.state["growth_correct"],
                "questions_in_bank": len(self.questions), "counts": counts,
                "attempts": len(self.state["attempts"]),
                "correct_attempts": sum(self._score(a) == 1 for a in self.state["attempts"]),
                "wrong_attempts": sum(self._score(a) == 0 for a in self.state["attempts"]),
                "partial_attempts": sum(self._score(a) == 0.5 for a in self.state["attempts"]),
                "points": sum(self._score(a) for a in self.state["attempts"]),
                "validated_questions": counts["first_correct"] + counts["corrected"],
                "adjudications_count": len(self.state.get("adjudications", [])),
                "pending_ids": [p["question_id"] for p in self.state["presentations"] if not p["answered"]],
                  "next_unseen_id": next((qid for qid in sorted(self.questions, key=self.question_number) if self.state["records"].get(str(qid), {}).get("status", "unseen") == "unseen"), None),
                "sources_checked_at": self.bank.get("checked_at"), "migration_notice": self.migration_notice}

    def history(self):
        attempts = copy.deepcopy(self.state["attempts"])
        for attempt in attempts:
            attempt['question_number'] = self.question_number(attempt['question_id'])
            attempt['question_title'] = self._question_for(next(p for p in self.state['presentations']
                if p['id']==attempt['presentation_id']))['q']
            attempt["adjudications"] = copy.deepcopy([event for event in self.state.get("adjudications", [])
                if event["presentation_id"] == attempt["presentation_id"]])
        return attempts

    def summary(self):
        rules = []
        seen = set()
        for q in self.questions.values():
            if self._accessible(q) and q["why"] not in seen:
                seen.add(q["why"])
                rules.append({"rule": q["why"], "source": self.bank["sources"][q["source"]]})
        result = {"status": self.status(), "rules": rules}
        path = self.bank_path.parent / "synthesis.json"
        if path.exists():
            result["reference"] = self._read_synthesis(path)
        return result

    @staticmethod
    def _read_synthesis(path):
        data = read_json(path)

        def invalid(detail):
            raise QuizError("Synthèse structurée invalide : " + detail)

        def strings(value):
            return isinstance(value, list) and all(isinstance(item, str) for item in value)

        if not isinstance(data, dict):
            invalid("objet JSON attendu.")
        if (type(data.get("version")) not in (int, str)
                or not isinstance(data.get("title"), str) or not data["title"].strip()
                or not isinstance(data.get("introduction"), str)
                or not isinstance(data.get("checked_at"), str)):
            invalid("version, date, titre ou introduction manquants.")
        try:
            datetime.strptime(data["checked_at"], "%Y-%m-%d")
        except ValueError:
            invalid("checked_at doit être une date ISO AAAA-MM-JJ.")
        sources = data.get("sources")
        if not isinstance(sources, dict):
            invalid("sources doit être un dictionnaire.")
        for key, source in sources.items():
            if (not isinstance(key, str) or not isinstance(source, dict)
                    or not isinstance(source.get("reference"), str)
                    or not isinstance(source.get("url"), str)
                    or not isinstance(source.get("version", ""), str)):
                invalid("référence de source mal formée.")
            try:
                parsed = urlsplit(source["url"])
            except ValueError:
                invalid(f"URL de source incorrecte : {key}.")
            if (parsed.scheme not in ("http", "https") or not parsed.netloc
                    or any(char.isspace() for char in source["url"])):
                invalid(f"URL HTTP(S) attendue pour la source {key}.")

        def check_source_ids(ids):
            if not strings(ids) or any(key not in sources for key in ids):
                invalid("référence à une source inconnue.")

        sections = data.get("sections")
        if not isinstance(sections, list):
            invalid("sections doit être une liste.")
        section_ids = set()
        for section in sections:
            if (not isinstance(section, dict) or not isinstance(section.get("id"), str)
                    or not section["id"].strip() or section["id"] in section_ids
                    or not isinstance(section.get("title"), str)
                    or not strings(section.get("columns")) or not section["columns"]
                    or not isinstance(section.get("rows"), list)
                    or not strings(section.get("notes", []))):
                invalid("section, en-tête ou notes mal formés.")
            section_ids.add(section["id"])
            for row in section["rows"]:
                if not strings(row) or len(row) != len(section["columns"]):
                    invalid(f"nombre ou type des cellules incorrect dans {section['id']}.")
            check_source_ids(section.get("sources", []))
        audit = data.get("audit", [])
        if not isinstance(audit, list):
            invalid("audit doit être une liste.")
        for row in audit:
            if (not isinstance(row, dict)
                    or any(not isinstance(row.get(key), str) for key in ("item", "supplied", "verified"))
                    or row.get("status") not in ("corrected", "qualified", "confirmed", "unresolved")):
                invalid("ligne d'audit mal formée.")
            check_source_ids(row.get("source_ids", []))
        attachments = data.get("attachments", [])
        if not isinstance(attachments, list) or any(not isinstance(row, dict) or any(
                not isinstance(row.get(key), str) for key in ("name", "library_file_id", "role")) for row in attachments):
            invalid("pièce jointe mal formée.")
        return data
