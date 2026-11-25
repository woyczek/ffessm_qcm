# QCM FFESSM — 1.7.0

140 questions stockées, une interface HTML et une interface terminal. Python 3.10 ou plus récent est nécessaire ; aucun paquet supplémentaire n'est requis. Les deux interfaces utilisent la même progression. La consultation des sources n'est pas répétée à chaque question.

## 1. Installation et lancement

Décompresse l'archive. Pour mettre une installation existante à jour, remplace les fichiers du programme dans son dossier habituel : la distribution ne contient aucune réponse personnelle et n'écrase pas les résultats. Au premier lancement, les anciens fichiers connus à la racine sont automatiquement rangés dans les nouveaux sous-dossiers.

| Système | Navigateur | Terminal |
|---|---|---|
| Windows | `Lancer-QCM.cmd` | `Lancer-QCM-Terminal.cmd` |
| macOS | `Lancer-QCM.command` | `Lancer-QCM-Terminal.command` |
| Linux | `sh lancer-qcm.sh` | `sh lancer-qcm.sh --terminal` |

Les lanceurs Windows acceptent les chemins UNC via `pushd`/`popd`. Les scripts Unix sont en fins de ligne LF et marqués exécutables dans le ZIP. Si un extracteur retire ce droit sur macOS, utilise `sh Lancer-QCM.command`, ou `chmod +x *.command lancer-qcm.sh`. Leur exécution native macOS/Linux reste à vérifier.

Garde la fenêtre du programme ouverte, éventuellement réduite, pendant l'utilisation dans le navigateur. Aucun service externe n'est nécessaire au fonctionnement du QCM.

## 2. Répondre et consulter les résultats

Dans le navigateur, sélectionne les réponses en cliquant sur les boutons habituels, puis valide. Un second clic désélectionne le bouton. A-D sélectionne ou désélectionne, et Entrée valide. L’intitulé précise « 1 réponse » ou « Plusieurs réponses ». Les questions à plusieurs réponses exigent toutes les propositions exactes : choix complet = 1 point en vert ; sous-ensemble correct incomplet = ½ point en orange ; dès qu’une proposition fausse est retenue = 0 point en rouge. Les barèmes particuliers préparés pour les anciennes questions restent applicables. Le candidat ne choisit pas sa note. Une justification en texte libre reste à évaluer par l’assistant.

La correction reste affichée dix secondes maximum, puis la question suivante arrive. « Suivante » ou Entrée permet d'avancer immédiatement. « Résultats », « Synthèse », « Périmètre courant » et « Sources » affichent ou masquent chacun leur contenu à chaque clic. La synthèse présente les six tableaux et un lien vers le PDF d'origine ; les références et le rappel courant ont leurs propres boutons. La consultation suspend le passage automatique à la suite. « Exporter », en bleu juste avant « Réinitialiser », permet de télécharger le fichier de progression ; « Réinitialiser », rouge, est placé à droite.

Dans le terminal, le numéro et l’énoncé sont en gras ; les questions sont séparées et les corrections reprennent les trois couleurs. Saisis par exemple `B,D`, `BD` ou `b d` pour plusieurs choix. Les commandes `résumé`, `bilan` et `quitter` sont disponibles. Le terminal recharge les résultats avant chaque réponse pour gérer un usage simultané du HTML, sans double comptage ni confusion entre deux ordres de choix.

Une nouvelle installation commence à Q1. Avec un historique, le menu permet de continuer au dernier point ou de revoir en priorité les réponses non validées. La raison d'une reprise est affichée. « Recommencer » archive l'ancien historique puis repart à Q1 ; « Réinitialiser » oublie les réponses et les scores de la session active, sans créer de nouvelle archive. Les archives déjà conservées restent hors de cette session.

Le menu de démarrage propose aussi « Session de révision » dès qu’au moins une question a reçu une réponse. Ce mode n’affiche que des questions déjà répondues, avec priorité aux échecs et réponses partielles. Les notes suivent le barème habituel et les bonnes réponses continuent à compter dans la progression. La question normale laissée en attente est conservée : « Reprendre la progression » quitte la révision et revient à ce point. Les dates des tentatives apparaissent dans les résultats, et la carte des points indique la date du dernier résultat, en heure de Paris. Une ancienne tentative sans date est signalée comme telle.

## 3. Progression et questions

Le lot initial comprend dix questions au périmètre 30 %. Les dix doivent être acquises avant l'élargissement. Ensuite, deux bonnes réponses ajoutent un point de périmètre jusqu'à 100 %. Elles n'ont pas besoin d'être consécutives. Une réponse à ½ point ne valide pas la question et n'élargit pas le périmètre.

Les réponses fausses et partielles repassent en priorité, avec les choix mélangés. Les acquis sont aussi révisés régulièrement. Une absence de réponse n'est pas un échec. Le journal distingue les questions uniques, leurs tentatives, les scores et les corrections ultérieures. Les pourcentages indiquent le périmètre ouvert, pas un taux de maîtrise ni une couverture exhaustive du MFT.

La banque contient 140 questions, dont 40 nouveaux QCM à plusieurs bonnes réponses. Ils s’ouvrent progressivement entre 31 et 96 % de périmètre. Les N1-N4, E1-E3 et jeunes plongeurs y figurent progressivement ; certains thèmes restent à enrichir. Les identifiants restent stables et les références sont conservées. Une question existante ne doit pas être modifiée silencieusement : son empreinte protège les résultats précédents. Ajoute un nouvel identifiant ou réalise une migration explicite.

Les numéros visibles 1–140 suivent maintenant l’ordre du périmètre. Les dix questions initiales gardent leur numéro. Les identifiants techniques utilisés par les anciens résultats ne changent pas ; le journal, les requêtes de réponse et les signalements conservent donc leurs liens. Le signalement précise aussi le numéro visible. La correspondance est conservée dans la banque et le catalogue. Les nouvelles questions sont intercalées dans la progression, et non repoussées après les cent anciennes.

Depuis la version 1.5.0, Q3, Q4 et Q5 ont une révision explicite à choix multiples : N1 à 6/20 m guidé ; N2 autonome à 12/20 m ; N2 guidé à 6/20/40 m. Leurs anciennes versions sont conservées dans les métadonnées de la banque. La migration sauvegarde la progression précédente, conserve les notes déjà acquises et maintient l’ancien énoncé/barème pour une présentation déjà ouverte. Les nouvelles présentations utilisent les questions révisées. Aucune tentative n’est ajoutée par la mise à jour.

## 4. Signaler une erreur

« Signaler une erreur » prépare un courriel pour **woyczek@gmail.com**, avec un rapport JSON comprenant le numéro et l'intitulé de la question ainsi que les remarques du stagiaire. Le stagiaire ouvre ensuite le courriel et valide l'envoi dans sa messagerie. Un téléchargement JSON est également disponible ; aucun message n'est envoyé silencieusement. Le compteur de passage à la suite est suspendu pendant la rédaction du signalement.

Le format comprend `type`, `schema_version`, `question_id`, `question_title`, `remarks`, `presentation_id` et `reported_at`. Son schéma est dans `preferences/signalement.schema.json`.

## 5. Dossiers et maintenance

La racine ne contient que le HTML, le README et les lanceurs Windows/macOS/Linux.

| Dossier | Contenu |
|---|---|
| `questions/` | Banque, catalogue, lots de questions et synthèse vérifiée (`synthesis.json`). |
| `preferences/` | Réponses dans `progress.json`, réglages de migration, sauvegardes d'historique et schéma des signalements. |
| `app/` | Moteur, terminal, serveur HTML et gestion de l'arborescence en Python. |
| `assets/` | Favicon de l’application fourni par l’auteur. |
| `documents/` | Word et PDF imprimables de la synthèse, inclus dans l’archive. |
| `tests/` | Vérifications du moteur, de l'interface, de la migration et de la distribution. |
| `tools/` | Fabrication de l'archive, sans inclure les réponses personnelles. |

Au premier lancement après une ancienne version, le programme déplace `progress.json` de la racine vers `preferences/` si aucune progression n'y existe déjà. En cas de divergence, la progression de `preferences/` est conservée et l'ancien historique est archivé. Les anciens imports figés sont rangés à part et ne sont pas rejoués automatiquement. Aucun historique divergent n'est fusionné silencieusement.

Pour déplacer l'installation sur un autre ordinateur, copie l'ensemble du dossier, notamment `preferences/`. Pour lancer les commandes techniques, reste dans la racine du projet :

```text
python app/cli.py --json next
python app/cli.py --json answer A --question 6
python app/cli.py --json answer B,D --question 3
python app/cli.py --json status
python app/cli.py --json session
python app/cli.py --json start-review
python app/cli.py --json resume-latest
python app/cli.py --json restart
python app/cli.py --json reset
python -m unittest discover -s tests -t .
python tools/pack.py
```

L'assistant peut noter une réponse partielle avec `answer ... --score 0.5 --reason "motif"`, ou réévaluer une tentative avec `regrade --question 6 --score 0.5 --reason "motif"`. La réévaluation ne crée pas de nouvelle tentative et conserve la trace de la correction.

`--data-dir`, lorsqu'il est utilisé, désigne la racine d'une installation. Le mode JSON reste sans mise en forme. Les tests JavaScript, si Node.js est disponible, se lancent avec `node tests/test_ui.js`.

## 6. Synthèse contrôlée le 23 novembre 2026

Dans la synthèse HTML, le lien « PDF à imprimer » est placé en haut et ouvre le document inclus localement par le lanceur. Il fonctionne sans ChatGPT ni connexion. Les tableaux n’ont pas de défilement interne. Le code couleur est commun au HTML, au Word et au PDF : vert pour les plongeurs, bleu pour les encadrants, jaune pour les jeunes. Les tableaux mixtes appliquent la catégorie ligne par ligne ; le tableau croisé conserve son rouge/vert. Les coches sont blanches sur fond vert, les croix rouges et les repères d’attention orange. Les documents imprimables donnent les références et les URL officielles en texte simple, sans hyperliens actifs.

Les références sont le Code du sport sur Légifrance et les chapitres nationaux du MFT : N1 et N3 (décembre 2025), N2 et GP-N4 (mai 2026), Initiateur (décembre 2025), Jeunes (juin 2026), MF1 (juillet 2026), MF2 et RIFAP (mai 2026). Le PDF de prérogatives fourni est un document comparé, pas une source normative. Une croix verte seule signifie une fonction autorisée sans plafond supplémentaire indiqué, sauf label ; aucune erreur de plafond N3 n'est déduite de cette croix.

La synthèse distingue les fonctions de plongeur, guide, enseignant immergé et directeur de plongée. Elle corrige notamment les préalables du PE40, le RIFAP non obligatoire pour PA40 seul, l'autonomie d'un E1 titulaire du N3, la limite de direction de plongée attribuée à tort au MF1, et l'épreuve finale d'IPD à 25 m du MF1. Les différences entre âge d'accès, certification et exercice sont explicites.

Deux discordances sont signalées sans arbitrage caché : PE60 à 17 ans dans N3 contre un abaissement à 16 ans annoncé dans Jeunes ; PA20 minimum à l'examen initiateur dans son chapitre contre N2 pour les jeunes dans le chapitre Jeunes. Aucun QCM ne doit imposer une réponse sur ces cas tant qu'ils ne sont pas clarifiés. Les modalités détaillées d'admission au N5 restent à vérifier sur sa version nationale actuelle, non retrouvée lors de ce contrôle.

La fiche pédagogique de stabilisation est identifiée comme un support de séance : son objectif à ±50 cm pendant 30 secondes n'est pas une exigence réglementaire fédérale générale. Les liens officiels, versions, références de pages et 18 points d'audit sont conservés dans `questions/synthesis.json`, consultable hors ligne par les deux interfaces.
