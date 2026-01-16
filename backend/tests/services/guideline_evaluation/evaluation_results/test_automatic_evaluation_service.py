import os
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch

from app.models.guideline_evaluation.evaluation_results.generation_result import GenerationResult, GenerationResultRun
from app.services.guideline_evaluation.evaluation_results.automatic_evaluation_service import AutomaticEvaluationService
from app.utils.knowledge.mongodb_object_id import PyObjectId
from app.utils.logger import setup_logger

logger = setup_logger(log_to_console=True, name="TEST_backend")


# --- Mocks ---

class MockGuidelineReference:
    def __init__(self, text, guideline_id="001"):
        self._text = text
        self.guideline_id = guideline_id
        self.type = "text"
    
    def extract_content(self):
        return self._text


class MockRetrievalResult:
    def __init__(self, text, source_id="001"):
        self.retrieval = text
        self.source_id = source_id


# --- Test Case ---
class AutomaticEvaluationTestCase(unittest.TestCase):
    
    def setUp(self):
        patch.dict(
            os.environ, {
                "AZURE_OPENAI_API_KEY": "fake_api_key",
                "AZURE_OPENAI_API_BASE": "https://fake.openai.azure.com",
            },
        ).start()
        
        self.mock_dataset_service = Mock()
        self.mock_generated_results_service = Mock()
        self.mock_chat_service = Mock()
        self.mock_references_service = Mock()
        self.mock_guideline_service = Mock()
        
        self.evaluator = AutomaticEvaluationService(
            dataset_service=self.mock_dataset_service,
            generated_results_service=self.mock_generated_results_service,
            chat_service=self.mock_chat_service,
            references_service=self.mock_references_service,
            guideline_service=self.mock_guideline_service,
        )
    
    def _run_retrieval_test_updated(self, er_text, pr_texts=None, pr_wo_texts=None):
        # Setup mock expected and provided retrievals
        er = MockGuidelineReference(er_text)
        pr_refs = [MockGuidelineReference(txt) for txt in (pr_texts or [])]
        pr_wo_refs = [MockRetrievalResult(txt) for txt in (pr_wo_texts or [])]
        
        interaction = MagicMock()
        interaction.retrieval_output = []
        interaction.retrieval_latency = 0.1
        
        for i, pr in enumerate(pr_refs):
            mock_entry = MagicMock()
            mock_entry.reference_id = f"ref{i}"
            interaction.retrieval_output.append(mock_entry)
        if pr_refs:
            self.evaluator.references_service.get_reference_by_id = MagicMock(side_effect=pr_refs)
        
        for pr_wo in pr_wo_refs:
            mock_wo = MagicMock()
            mock_wo.reference_id = None
            mock_wo.retrieval = pr_wo.retrieval
            mock_wo.source_id = pr_wo.source_id
            interaction.retrieval_output.append(mock_wo)
        
        gen_result = GenerationResult(
            _id=PyObjectId("64a4f1e26fc3b3b9f2d4d8d0"),
            generation_run=GenerationResultRun(workflow_system_id=PyObjectId("64a4f1e26fc3b3b9f2d4d8d0"), name="test"),
            related_question=PyObjectId("64a4f1e26fc3b3b9f2d4d8d1"),
            related_chat=PyObjectId("64a4f1e26fc3b3b9f2d4d8d2"),
            created_at=datetime.now(timezone.utc),
        )
        
        self.evaluator._get_to_be_evaluated_interaction = MagicMock(return_value=interaction)
        self.evaluator._get_matching_expected_retrievals = MagicMock(return_value=[er])
        self.evaluator.generated_results_service.update_generation_result_entry = MagicMock()
        
        self.evaluator.run_retrieval_performance_analysis(gen_result)
        update_args = self.evaluator.generated_results_service.update_generation_result_entry.call_args[1]
        print(update_args)
        return update_args["update_data"]["automatic_evaluation.retrieval_evaluation"]
    
    def test_tp_er_inside_pr(self):
        evaluation = self._run_retrieval_test_updated(
            er_text="abc def ghi",
            pr_texts=["prefix abc def ghi suffix", "second_prefix abc def ghi"],
        )
        self.assertGreaterEqual(evaluation.f1, 0.5)
    
    def test_tp_pr_inside_er(self):
        evaluation = self._run_retrieval_test_updated(
            er_text="123 abc def 456",
            pr_texts=["abc def"],
        )
        self.assertGreaterEqual(evaluation.recall, 0.3)
    
    def test_tp_partial_overlap_suffix(self):
        evaluation = self._run_retrieval_test_updated(
            er_text="abc def ghi",
            pr_texts=["def ghi xyz"],
        )
        self.assertGreaterEqual(evaluation.precision, 0.5)
    
    def test_tp_wo_reference(self):
        evaluation = self._run_retrieval_test_updated(
            er_text="abc def ghi",
            pr_texts=[],
            pr_wo_texts=["abc def ghi"],
        )
        self.assertGreaterEqual(evaluation.f1, 0.9)
    
    def test_realworld_example(self):
        evaluation = self._run_retrieval_test_updated(
            er_text="Insbesondere die Verwendung von hydraulischen Silikatzementen oder Zinkoxid-Eugenol-basierten Zementen scheinen für die retrograde Füllung empfehlenswert zu sein. Die retrograde Füllung mit Glasionomerzement ergibt signifikant schlechtere Erfolgsraten, dieses Material soll nicht für eine retrograde Füllung verwendet werden.",
            pr_wo_texts=[
                "Empfehlung 11 (neu 2020) : Insbesondere die Verwendung von hydraulischen Silikatzementen oder Zinkoxid-Eugenol-basierten Zementen scheinen für die retrograde Füllung empfehlenswert zu sein. Die retrograde Füllung mit Glasionomerzement ergibt signifikant schlechtere Erfolgsraten, dieses Material soll nicht für eine retrograde Füllung verwendet werden. (Abstimmung: 13/13 (ja/ Anzahl der Stimmen); Starker Konsens; Expertenkonsens und weiterführende Literatur (Tabelle 15))",
                "Walivaara et al. (2009) zeigten, dass auch Guttapercha für die retrograde Füllung erfolgreich eingesetzt werden kann, wenn durch den Einsatz eines Sealers eine entsprechende Randdichtigkeit erzeugt wird.",
                """Tabelle 10: Studien zur Effektivität der retrograden Füllung: | Publikation | Studiendesign | Intervention | Resultat/Hauptaussage | |--|--|--|--| | Christiansen et al.,
    2009 | randomisierte kontrollierte Studie;<br>Intervention an 52 Zähnen (Front-, Eckzähne und Prämolaren) bei 44 Patienten (26 Zähne je Gruppe), Nachuntersuchung von 46 Zähnen nach 1 Jahr | rechtwinklige WSR mit Ultraschallpräparation einer retrograden Kavität und Füllung mit hydraulischem Silikatzement oder WSR mit Glättung der orthograden Guttapercha-Wurzelkanal-füllung (erhitztes Instrument) | nach 1 Jahr Erfolgsrate von 97% bei retrograder Füllung mit hydraulischem Silikatzement und von 52% bei alleiniger Glättung der vorhandenen Wurzelkanalfüllung (statistisch signifikant, p<0.001) | | Walivaara et al.,
    2009 | randomisierte kontrollierte Studie;<br>Intervention an 160 Zähnen bei 139 Patienten (83 Zähne Epoxidharz-Sealer/Guttapercha und 77 Zähne ZnO-Eugenol-Zement), Nachuntersuchung von 147 Zähnen bei 131 Patienten nach 1 Jahr | nahezu rechtwinklige Wurzel-spitzenresektion mit Ultraschallpräparation einer retrograden Kavität und Füllung mit Epoxidharz-Sealer/injizierbarer Guttapercha oder ZnO-Eugenol-Zement | nach 1 Jahr Erfolgsrate von 90% bei Epoxidharz-Sealer/Guttapercha und von 85% bei ZnO-Eugenol-Zement (kein signifikanter Unterschied) | | Kruse et al.,
    2016 | randomisierte kontrollierte Studie;<br>Intervention an 52 Zähnen (Front-, Eckzähne und Prämolaren) bei 44 Patienten (26 Zähne je Gruppe), Nachuntersuchung von 39 Zähnen nach 6 Jahren | wie Christiansen et al.,
    2009 | nach 6 Jahren Erfolgsrate von 86% bei retrograder Füllung mit hydraulischem Silikatzement und von 55% bei alleiniger Glättung der vorhandenen Wurzelkanalfüllung (statistisch signifikant, p=0.04) | | Beck-Broichsitter et al.,
    2018 | retrospektive Kohortenstudie;<br>Intervention an 149 Zähnen (11 Frontzähne,
    67 Prämolaren,
    71 Molaren), Nachuntersuchung bis 12 Jahre postoperativ | Wurzelspitzenresektion, bei 80 Zähnen ohne zusätzliche Füllung, bei 47 Zähnen mit orthograder Wurzelkanal-füllung und bei 17 Zähnen mit retrograder Füllung (Mikro-Handstück, versch. Füllmaterialien) | nach 12 Jahren Erhalt von 40 Zähne (50%) ohne zusätzliche Füllung; kein Zahn (0%) mit orthograder Wurzelkanalfüllung erhalten gegenüber von 11 Zähnen (65%) mit retrograder Füllung (p=0,
    0237); Qualität der ursprünglichen Wurzelkanalfüllung hatte keinen signifikanten Einfluss (p=0,
    125) |""",
                """Tabelle 15: Studien zu retrograden Füllmaterialien : | Publikation | Studiendesign | Intervention | Resultat/Hauptaussage | |--|--|--|--| | Jensen et al.,
    2002 | randomisierte kontrollierte Studie; Intervention bei 134 Patienten (in beiden Gruppen 67 Pat.); Nachuntersuchung von 122 Patienten (60 Patienten Komposit und 62 Patienten Glasionomer-zement) nach 1 Jahr (1 Zahn pro Patient) | Wurzelspitzenresektion mit konkaver Präparation der Resektionsfläche und Füllung mit Dentin-Bonding/Komposit oder Glasionomerzement | nach 1 Jahr Erfolgsrate von 73% bei Komposit und von 31% bei Glasionomerzement (statistisch signifikant, p<0.001) | | Chong et al.,
    2003 | randomisierte kontrollierte Studie; Intervention bei 183 Patienten, Nachuntersuchung von 122 Patienten nach 1 Jahr und von 108 Patienten nach 2 Jahren (1 Zahn pro Patient) | rechtwinklige WSR mit Ultraschallpräparation einer retrograden Kavität und Füllung mit hydraulischem Silikatzement oder ZnO-Eugenol-Zement | nach 1 Jahr Erfolgsrate von 84% bei Silikatzement und 76% bei ZnO-Eugenol-Zement, nach 2 Jahren von 92% bei Silikat-zement und 87% bei ZnO-Eugenol-Zement (keine Signifikanz) | | Platt und Wannfors,
    2004 | randomisierte kontrollierte Studie; Intervention an 34 Zähnen bei 28 Patienten (18 Zähne Kompomer und 16 Zähne GIZ); Nachuntersuchung nach 1 Jahr | WSR mit konkaver Präparation der Resektionsfläche und Füllung mit Kompomer oder zylindrischer Präparation und Glasionomerzement -Füllung | nach 1 Jahr Erfolgsrate von 89% bei Kompomer und von 44% bei Glasionomerzement (statistisch signifikant, p<0.015) | | Lindeboom et al.,
    2005a | randomisierte kontrollierte Studie; 100 Zähne bei 90 Patienten (50 Zähne pro Gruppe); Nachuntersuchung nach 1 Jahr | um 10-25° angulierte WSR mit Ultraschallpräparation einer retrograden Kavität und Füllung mit hydraulischem Silikat-zement oder ZnO-Eugenol-Zement; Einsatz einer Lupe | nach 1 Jahr Erfolgsrate von 92% bei Silikatzement und 86% bei ZnO-Eugenol-Zement (kein signifikanter Unterschied) | | von Arx et al.,
    2010 | nicht randomisierte kontrollierte Studie; Intervention bei 353 Patienten, Nachuntersuchung von 339 Patienten nach 1 Jahr (173 Patienten Silikatzement und 166 Patienten Komposit; 1 Zahn pro Patient) | WSR mit Ultraschallpräparation einer retrograden Kavität und Füllung mit hydraulischem Silikatzement oder Präparation einer flachen Kavität und Füllung mit Dentin-Bonding/ Komposit | nach 1 Jahr Erfolgsrate von 91% bei Silikatzement und von 80% bei Komposit (statistisch signifikant, p=0.003) | | Walivaara et al.,
    2011 | randomisierte kontrollierte Studie; Intervention an 206 Zähnen bei 164 Patienten (99 Zähne ZnO-Eugenol-Zement und 107 Zähne EBA-Zement), Nach-untersuchung von 194 Zähnen bei 153 Patienten nach >1 Jahr | minimal schräge Wurzelspitzenresektion mit Ultraschallpräparation einer retrograden Kavität und Füllung mit ZnO-Eugenol-Zement oder EBA-Zement | nach mind. 1 Jahr (Mittel: 13,
    1 Monate) Erfolgsrate von 91% bei ZnO-Eugenol-Zement und 82% bei EBA-Zement (kein signifikanter Unterschied) | | Song und Kim,
    2012 | randomisierte kontrollierte Studie; Intervention bei 260 Patienten, Nachuntersuchung von 192 Patienten nach 1 Jahr (90 Patienten Silikatzement und 102 Patienten EBA-Zement; 1 Zahn pro Patient) | um 0-10° angulierte WSR mit Ultraschallpräparation einer retrograden Kavität und Füllung mit hydraulischem Silikat-zement oder EBA-Zement; Einsatz eines Mikroskops (20x bis 26x Vergr.) | nach 1 Jahr Erfolgsrate von 96% bei Silikatzement und von 93% bei EBA-Zement (kein signifikanter Unterschied) | | von Arx et al.,
    2014 | nicht randomisierte kontrollierte Studie; Nachuntersuchung nach 5 Jahren zu von Arx et al.,
    2010; 271 Patienten (134 Patienten hydraulischer Silikatzement und 137 Patienten Komposit; 1 Zahn pro Patient) | wie von Arx et al.,
    2010 | nach 5 Jahren Erfolgsrate von 88% bei Silikatzement und von 71% bei Komposit (statistisch signifikant, p=0.0005) | | Kim et al.,
    2016c | randomisierte kontrollierte Studie; Intervention bei 260 Patienten, Nachuntersuchung von 182 Patienten nach 4 Jahren (83 Patienten Silikatzement und 99 Patienten EBA-Zement; 1 Zahn pro Patient) | wie Song und Kim,
    2012 | nach 4 Jahren Erfolgsrate von 92% bei Silikatzement und von 90% bei EBA-Zement (kein signifikanter Unterschied) | | Zhou et al.,
    2017 | randomisierte kontrollierte Studie; Einschluss von 240 Zähnen in Studie, Nachunter-suchung von 158 Zähnen nach 1 Jahr (87 Zähne Gruppe 1 und 71 Zähne Gruppe 2 - retrograde Füllung mit unterschiedlichen Silikatzementen) | nicht angulierte Wurzelspitzenresektion mit Ultraschallpräparation einer retrograden Kavität und Füllung mit hydraulischem Silikatzement; Einsatz eines Mikroskops | nach 1 Jahr Erfolgsrate von 93% in Gruppe 1 und von 94% in Gruppe 2 (kein signifikanter Unterschied) | | von Arx et al.,
    2019 | Langzeit Follow-up-Studie; Intervention bei 195 Patienten (ein Zahn pro Patient), Nachuntersuchung von 119 Zähnen nach 1,
    5, und 10 Jahren | 3 mm Wurzelspitzenresektion mit Ultraschall-präparation einer retrograden Kavität und Füllung mit hydraulischem Silikatzement | nach 10 Jahren 97 von 119 Zähnen (81,
    5%) als geheilt eingestuft |
                """,
                "Empfehlung 9 (neu 2020) : Die Resektion der Wurzelspitze soll nahezu rechtwinklig zur Zahnachse erfolgen. Anschließend sollen die Präparation einer retrograden, ca. 3 mm tiefen und zum Wurzelkanal achsgerechten Kavität sowie die Applikation einer retrograden Füllung erfolgen. Dies gilt jeweils, sofern es anatomisch möglich ist. Im Verlauf des Verabschiedungsprozesses schlossen sich – entgegen der Abstimmung der Mandatstragenden – vier weitere Fachgesellschaften/ Organisationen dem Sondervotum zu Empfehlung 9 an. Drei weitere Fachgesellschaften/ Organisationen stimmten der Empfehlung in dieser Form nicht zu (s.u.). Sondervotum von DGMKG, DGI, AKOPOM, BDO, DAZ, FVDZ, BZÄK und KZBV Die genannten Fachgesellschaften/Organisationen teilen die Auffassung der übrigen Fachgesellschaften zur Präparation der retrograden Kavität nicht. Die zusammengehörigen Arbeiten von Christiansen et al. (2009) und von Kruse et al. (2016) liefern einen Hinweis für den Vorteil der retrograden Füllung. Dabei wurden keine Molaren untersucht. Es liegen keine weiteren Arbeiten mit diesem Studiendesign vor. Es besteht damit keine ausreichende Evidenz. Eine strenge Empfehlung zur Präparation der 3 mm tiefen retrograden Kavität und der Applikation der retrograden Füllung kann nicht gegeben werden. Die Empfehlung von DGMKG, DGI, AKOPOM, BDO, DAZ, FVDZ, BZÄK und KZBV lautet daher: Die Resektion der Wurzelspitze soll nahezu rechtwinklig zur Zahnachse erfolgen. Anschließend sollten die Präparation einer retrograden, ca. 3 mm tiefen und zum Wurzelkanal achsgerechten Kavität sowie die Applikation einer retrograden Füllung erfolgen. Dies gilt jeweils, sofern es anatomisch möglich ist. Die AGOKi, die DGMKG und der BDO stimmen der Empfehlung nicht zu. Aus anatomischen Gründen ist im Bereich der Molaren (und ggf. der Prämolaren) die Darstellung der Wurzelkanäle und die präzise Kontrolle der Randständigkeit der Wurzelfüllung bei rechtwinkliger Resektion nur erschwert möglich. Die AGOKi, die DGMKG und der BDO stimmen prinzipiell der Empfehlung zur Resektion der Wurzelspitze im rechten Winkel zur Zahnachse zu, sieht allerdings eine starke („soll“) Empfehlung nur im Frontzahnbereich umsetzbar. (Abstimmung: 10/13 (ja/ Anzahl der Stimmen); Konsens; Expertenkonsens und weiterführende Literatur (Tabelle 9 und Tabelle 10) )",
            ],
        )
        self.assertGreater(evaluation.f1, 0)
    
    def test_no_match(self):
        evaluation = self._run_retrieval_test_updated(
            er_text="completely different text",
            pr_texts=["no overlap here", "Or here"],
        )
        self.assertEqual(evaluation.precision, 0.0)
        self.assertEqual(evaluation.recall, 0.0)
        self.assertEqual(evaluation.f1, 0.0)
    
    def test_iteration_texts(self):
        er_text = """
            - Perikoronare Infektion
            - Erweiterung des radiologischen Perikoronarraumes
            - Perikoronare Auftreibung (beispielsweise durch Zystenbildung)
            - Schmerzen/Spannungsgefühl im Kiefer-Gesichtsbereich
            - Parodontale Schäden, insbesondere distal an 12-Jahr Molaren
            - Resorptionen an Nachbarzähnen (siehe Hintergrundtext unter 9.2)
            - Elongation/Kippung
            - kariöse Zerstörung/Pulpitis"""
        
        pr_text = "nen typischerweise sein: • Perikoronare Infektion • Erweiterung des radiologischen Perikoronarraumes • Perikoronare Auftreibung (beispielsweise durch Zystenbildung) • Schmerzen/Spannungsgefühl im Kiefer-Gesichtsbereich • Parodontale Schäden, insbesondere distal an 12-Jahr Molaren • Resorptionen an Nachbarzähnen (siehe Hintergrundtext unter 9.2) • Elongation/Kippung • kariöse Zerstörung/Pulpitis"
        
        evaluation = self._run_retrieval_test_updated(
            er_text=er_text,
            pr_texts=[pr_text],
        )
        
        self.assertGreaterEqual(evaluation.precision, 0.5)
        self.assertGreaterEqual(evaluation.recall, 0.5)
        self.assertGreaterEqual(evaluation.f1, 0.5)


if __name__ == '__main__':
    unittest.main()
