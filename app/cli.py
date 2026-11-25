"""QCM FFESSM local, Python 3.10+, sans dépendance ni connexion réseau."""
import argparse
import json
import os
import sys
from pathlib import Path
try:
    from .engine import Quiz, QuizError
except ImportError:
    from engine import Quiz, QuizError


ANSI = False


def enable_ansi():
    if not sys.stdout.isatty():
        return False
    if os.name != "nt":
        return True
    try:
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.windll.kernel32
        kernel.GetStdHandle.restype = wintypes.HANDLE
        kernel.GetStdHandle.argtypes = [wintypes.DWORD]
        kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        handle = kernel.GetStdHandle(-11)
        mode = wintypes.DWORD()
        return bool(kernel.GetConsoleMode(handle, ctypes.byref(mode))
                    and kernel.SetConsoleMode(handle, mode.value | 0x0004))
    except (AttributeError, OSError):
        return False


def styled(text, color=None, bold=False):
    if not ANSI:
        return text
    codes = (["1"] if bold else []) + ([color] if color else [])
    return "\033[" + ";".join(codes or ["0"]) + "m" + text + "\033[0m"


def render_status(s):
    stage = (f"lot initial {s['initial_acquired']}/10" if not s["initial_complete"]
             else f"élargissement {s['growth_correct']}/2")
    return (f"Périmètre {s['scope']} % · {stage} · {s['points']:g} point(s) sur {s['attempts']} tentative(s) · "
            f"{s['counts']['failed']} échec(s) et {s['counts']['partial']} partielle(s) à reprendre")


def render(value):
    if isinstance(value, list):
        if not value:
            print("Aucune tentative enregistrée.")
        for row in value:
            score = row.get("score", 1 if row["correct"] else 0)
            label = "juste" if score == 1 else "partielle, à reprendre" if score == 0.5 else "à reprendre"
            print(f"Q{row.get('question_number', row['question_id'])} · {row['letter']} · {label} · {score:g}/1 · {row['at'] or 'date historique inconnue (import)'}")
            for event in row.get("adjudications", []):
                print(f"  Réévaluation {event['old_score']:g} → {event['new_score']:g} : {event['reason']}")
    elif "question" in value:
        print("\n\n" + ("─" * 56 if ANSI else ""))
        print(render_status(value["status"]))
        label = "1 réponse" if value.get("one_answer", True) else "Plusieurs réponses"
        print(styled(f"\nQuestion {value.get('question_number', value['question_id'])} - {label} ({value['kind']})\n", bold=True))
        print(styled(value["question"], bold=True))
        if value.get("selection_reason"):
            print(value["selection_reason"])
        for letter, choice in value["choices"].items():
            print(f"  {letter}. {choice}")
        if value.get("previous_revision"):
            print("Présentation antérieure à la mise à jour : son énoncé et son barème sont conservés.")
        print("Indique toutes les réponses exactes, par exemple A,C.")
    elif "correct" in value:
        label, color = (("Correct — 1 point.", "32") if value["correct"] else
                        ("À affiner — 0,5 point ; question à reprendre.", "38;5;208") if value.get("partial") else
                        (f"Incorrect — 0 point. Réponse attendue : {value['correct_letter']}.", "31"))
        print(styled(label, color=color, bold=True))
        if value.get("reason"):
            print(value["reason"])
        if value.get("partial"):
            print("Réponses attendues : " + value["correct_letter"] + ".")
        print(value["explanation"])
        print("Source : " + value["source"]["reference"])
        print(render_status(value["status"]))
    elif "rules" in value:
        print(render_status(value["status"]))
        reference = value.get("reference")
        if reference:
            print("\nSynthèse vérifiée — ensemble du programme")
            print(reference["title"])
            print(f"Vérifiée le {reference['checked_at']} · version {reference['version']}")
            print(reference["introduction"])
            for section in reference["sections"]:
                print("\n" + section["title"])
                print(" · ".join(section["columns"]))
                for row in section["rows"]:
                    print(" · ".join(row))
                for note in section.get("notes", []):
                    print("- " + note)
                for key in section.get("sources", []):
                    source = reference["sources"][key]
                    print("Source : " + source["reference"] + (" · " + source["version"] if source.get("version") else "")
                          + " · " + source["url"])
            for row in reference.get("audit", []):
                if row["status"] != "confirmed":
                    print(f"\nVérification [{row['status']}] — {row['item']}")
                    print("Document transmis : " + row["supplied"])
                    print("Vérifié : " + row["verified"])
            print(f"\nRappel du périmètre courant : {value['status']['scope']} %")
        for row in value["rules"]:
            print(f"\n- {row['rule']} ({row['source']['reference']})")
    elif "scope" in value:
        print(render_status(value))
        if value.get("migration_notice"):
            print(value["migration_notice"])
        print(f"Banque : {value['questions_in_bank']} questions. En attente : {value['pending_ids']}.")
    elif "has_history" in value:
        print(render_status(value["status"]))
        if value.get("migration_notice"):
            print(value["migration_notice"])
        if not value["has_history"]:
            print("Aucun historique : la première question sera Q1.")
        else:
            print(f"Dernière question présentée : Q{value.get('last_presented_question_number', value['last_presented_question_id'])}.")
            if value["resume_question_id"] is not None:
                print(f"Dernier point en attente : Q{value.get('resume_question_number', value['resume_question_id'])} (commande resume-latest).")
            if value["priority_reason"]:
                print(value["priority_reason"])
            print("Pour repartir à Q1 en archivant l'historique : commande restart.")
    else:
        if value.get("message"):
            print(value["message"])
        if value.get("status"):
            print(render_status(value["status"]))


def main(argv=None):
    global ANSI
    # JSON is always UTF-8, including when PowerShell captures stdout through pipes.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--json", action="store_true", help="Réponse JSON, sans texte annexe")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("next", help="Reprendre la question en attente ou en choisir une")
    commands.add_parser("daily", help="Nouvelle question du jour, sans noter les absences comme fausses")
    ans = commands.add_parser("answer", help="Enregistrer une réponse puis afficher la suivante")
    ans.add_argument("letter")
    ans.add_argument("--question", type=int, help="Identifiant requis si plusieurs questions attendent")
    ans.add_argument("--score", type=float, choices=(0, 0.5, 1), help="Score manuel, exige --reason")
    ans.add_argument("--reason", help="Motif de correction manuelle")
    grade = commands.add_parser("regrade", help="Réévaluer la dernière tentative d'une question, sans créer de tentative")
    grade.add_argument("--question", type=int, required=True)
    grade.add_argument("--score", type=float, choices=(0, 0.5, 1), required=True)
    grade.add_argument("--reason", required=True)
    for name in ("status", "history", "summary", "session", "resume-latest", "start-review", "restart", "reset"):
        commands.add_parser(name)
    args = parser.parse_args(argv)
    ANSI = False if args.json else enable_ansi()
    try:
        quiz = Quiz(args.data_dir)
        if args.command in ("restart", "reset"):
            result = getattr(quiz, args.command)()
            if args.json:
                print(json.dumps(result, ensure_ascii=False))
            else:
                print(result["message"])
                if result.get("backup_file"):
                    print("Historique archivé : " + result["backup_file"])
                render(result["next"])
            return 0
        if args.command in ("answer", "regrade"):
            result = (quiz.answer(args.letter, args.question, args.score, args.reason)
                      if args.command == "answer" else quiz.regrade(args.question, args.score, args.reason))
            following = quiz.next()
            if args.json:
                print(json.dumps({"result": result, "next": following}, ensure_ascii=False))
            else:
                render(result)
                print()
                render(following)
            return 0
        if args.command:
            value = (quiz.next(daily=args.command == "daily") if args.command in ("next", "daily") else
                     quiz.resume_latest() if args.command == "resume-latest" else
                     quiz.start_review() if args.command == 'start-review' else getattr(quiz, args.command)())
            print(json.dumps(value, ensure_ascii=False)) if args.json else render(value)
            return 0
        if args.json:
            print(json.dumps(quiz.next(), ensure_ascii=False))
            return 0
        question = quiz.next()
        while True:
            render(question)
            answer = input("\nTes réponses (A,C ou AC ; résumé, bilan, révision, reprendre, quitter) : ").strip()
            if answer.lower() in ("q", "quitter", "exit"):
                return 0
            if answer.lower() in ('révision','revision','reprendre'):
                quiz=Quiz(args.data_dir)
                try:
                    question=quiz.resume_latest() if answer.lower()=='reprendre' else quiz.start_review()
                except QuizError as exc:
                    print(str(exc))
                continue
            if answer.lower() in ("résumé", "resume", "synthèse", "summary"):
                quiz = Quiz(args.data_dir)
                render(quiz.summary())
                continue
            if answer.lower() in ("bilan", "status"):
                quiz = Quiz(args.data_dir)
                render(quiz.status())
                continue
            try:
                # Another interface may have answered while this terminal waited for input.
                quiz = Quiz(args.data_dir)
                presentation = next((p for p in quiz.state["presentations"]
                                     if p["id"] == question.get("presentation_id")), None)
                if presentation is None or presentation["answered"]:
                    print("Cette question a déjà été traitée ou remplacée dans une autre interface. Réponse non comptée.")
                    question = quiz.next()
                    continue
                current = quiz.public_question(presentation)
                if (current["question_id"] != question.get("question_id")
                        or current["question"] != question.get("question")
                        or current["choices"] != question.get("choices")):
                    print("La présentation a changé dans une autre interface. Vérifie les choix actualisés ; réponse non comptée.")
                    question = current
                    continue
                result = quiz.answer(answer, question.get("question_id"),
                                     presentation_id=question.get("presentation_id"))
                render(result)
                question = quiz.next()
                print()
            except QuizError as exc:
                print(str(exc))
                # Keep in-memory attempts aligned with disk even after a concurrent-write rejection.
                quiz = Quiz(args.data_dir)
                question = quiz.next()
    except (QuizError, OSError) as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        else:
            print("Erreur : " + str(exc))
        return 2
    except (EOFError, KeyboardInterrupt):
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
