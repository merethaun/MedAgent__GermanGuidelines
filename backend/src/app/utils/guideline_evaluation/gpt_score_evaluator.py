import asyncio
import os
import re
from typing import Dict, Union, Tuple, Optional, List

from llama_index.core import ChatPromptTemplate
from llama_index.core.base.llms.types import ChatMessage, MessageRole
from llama_index.core.evaluation import CorrectnessEvaluator
from llama_index.core.evaluation.correctness import DEFAULT_USER_TEMPLATE

from app.utils.llama_index.llm_interaction import AzureOpenAILlamaIndexLLM
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_examples = [
    {
        "gen_res_id": "68876d9d0741c76bdb4a0614",
        "question": "Wann ist die dreidimensionale Bildgebung bei der Entfernung von Weisheitszähnen indiziert?",
        "expected_answer": "Eine dreidimensionale Bildgebung (z.B. DVT oder CT) ist dann indiziert, wenn die konventionelle zweidimensionale Bildgebung Hinweise auf eine unmittelbare Lagebeziehung zu Risikostrukturen oder pathologische Veränderungen zeigt und zusätzlich aus Sicht des Behandlers weiterführende räumliche Informationen für die Risikoaufklärung, die Eingriffsplanung oder die intraoperative Orientierung erforderlich sind.\n\nLiegt keine besondere Risikosituation vor, ist eine dreidimensionale Bildgebung nicht erforderlich.",
        "expected_retrievals": [
            {
                "guideline": "007-003 - Operative Entfernung von Weisheitszähnen",
                "retrieval": "Statement\nEine dreidimensionale Bildgebung ist vor einer Weisheitszahnentfernung nicht erforderlich, wenn in der konventionell zweidimensionalen Bildgebung keine Hinweise auf eine besondere Risikosituation vorliegen.\nStarker Konsens (4/4, zwei Enthaltungen aufgrund eines Interessenskonfliktes)",
            },
            {
                "guideline": "007-003 - Operative Entfernung von Weisheitszähnen",
                "retrieval": "Empfehlung\nEine dreidimensionale Bildgebung (beispielsweise DVT/CT) kann indiziert sein, wenn in der konventionellen zweidimensionalen Bildgebung Hinweise auf eine unmittelbare Lagebeziehung zu Risikostrukturen oder pathologischen Veränderungen vorhanden sind und gleichzeitig aus Sicht des Behandlers weitere räumliche Informationen entweder für die Risikoaufklärung des Patienten, Eingriffsplanung oder auch für die intraoperative Orientierung erforderlich sind.\nStarker Konsens (4/4, zwei Enthaltungen aufgrund eines Interessenskonfliktes)",
            },
        ],
        "actual_response": "Die AWMF-Leitlinie 007-089 „Operative Entfernung von Weisheitszähnen (Dritte Molaren)“ gibt klare Empfehlungen zur Indikation der dreidimensionalen Bildgebung (z.B. digitale Volumentomographie [DVT] oder Computertomographie [CT]) im Rahmen der Weisheitszahnentfernung.\n\n**Schrittweise Herleitung nach Leitlinie:**\n\n1. **Grundsatz:**  \n   - Die Standardbildgebung vor Weisheitszahnentfernung ist das zweidimensionale Röntgenbild, in der Regel das Orthopantomogramm (OPG).\n   - Die dreidimensionale Bildgebung ist mit einer höheren Strahlenbelastung verbunden und soll daher nur bei spezieller Fragestellung eingesetzt werden.\n\n2. **Indikationen für die dreidimensionale Bildgebung:**  \n   - Sie ist **indiziert**, wenn das konventionelle Röntgenbild (OPG) keine ausreichende Aussage über die Lagebeziehung von Weisheitszahn und Nachbarstrukturen (insbesondere Nervus alveolaris inferior, Nervus lingualis, Kieferhöhle) erlaubt.\n   - Bei Verdacht auf eine enge Beziehung oder Überlagerung zwischen Zahnwurzel und Nervus alveolaris inferior, wenn aus dem OPG eine Gefährdung nicht sicher ausgeschlossen werden kann.\n   - Bei komplexen anatomischen Verhältnissen, z.B. stark verlagerte, retinierte oder supernumeräre Weisheitszähne, bei denen die exakte dreidimensionale Lage für die OP-Planung relevant ist.\n   - Bei pathologischen Veränderungen (z.B. große Zysten, Tumoren) im Bereich des Weisheitszahns, deren Ausdehnung zweidimensional nicht ausreichend beurteilbar ist.\n   - Zur OP-Planung, wenn vorauszusehen ist, dass die Entfernung schwierig wird oder ein erhöhtes Risiko für Komplikationen besteht.\n\n3. **Nicht indiziert:**  \n   - Eine routinemäßige Anwendung der 3D-Bildgebung bei allen Weisheitszahnentfernungen ist nicht leitliniengerecht.\n\n**Zusammenfassung:**  \nDreidimensionale Bildgebung (DVT oder CT) ist bei Weisheitszahnentfernungen dann indiziert, wenn das konventionelle Röntgenbild keine ausreichende Beurteilung der Lagebeziehung des Zahns zu sensiblen Nachbarstrukturen (insbesondere zum Nervus alveolaris inferior) oder bei komplexen anatomischen Verhältnissen ermöglicht, oder wenn pathologische Veränderungen vorliegen, die zweidimensional nicht ausreichend dargestellt werden können.\n\n**Quelle:**  \nAWMF-Leitlinie 007-089: Operative Entfernung von Weisheitszähnen (Dritte Molaren), Kapitel „Bildgebende Diagnostik“.",
        "correctness_score": 5,
        "reason": "Die Antwort ist vollständig, korrekt und entspricht der Leitlinie. Alle relevanten Indikationen für die 3D-Bildgebung werden genannt, ohne vom Thema abzuweichen. Lediglich die Registernummer ist falsch angegeben, was aber den fachlichen Gehalt nicht beeinträchtigt.",
    },
    {
        "gen_res_id": "6875fac0c6945aa0f11ec374",
        "question": "Was sind die häufigsten Ursachen für die odontogene Sinusitis maxillaris?",
        "expected_answer": "Die häufigste Ursache einer odontogenen Sinusitis maxillaris ist eine persistierende Mund-Kieferhöhlen-Verbindung (z. B. nach Zahnentfernung). Zweithäufig tritt sie infolge einer apikalen Parodontitis aufgrund einer entzündlichen Pulpaerkrankung auf.",
        "expected_retrievals": [
            {
                "guideline": "007-086 - Odontogene Sinusitis maxillaris",
                "retrieval": "Die häufigste Ursache ist die persistierende Mund-Kieferhöhlen-Verbindung (oroantrale Fistel, Mund-Antrum-Verbindung) z.B. nach Zahnentfernung [Akhlagi 2015]. Die zweithäufigste Ursache stellt die apikale Parodontitis in Folge einer entzündlichen Pulpaerkrankung dar [AAE 2018].",
            },
        ],
        "actual_response": "Die **häufigsten Ursachen für die odontogene Sinusitis maxillaris** (also eine Entzündung der Kieferhöhle, die ihren Ursprung im Bereich der Zähne oder des Zahnhalteapparats hat) sind:\n\n---\n\n### 1. **Periapikale Infektionen**\n- **Periapikale Ostitis / Abszesse** an den Wurzeln der oberen Prämolaren und Molaren, deren Wurzeln in enger Nachbarschaft oder sogar in die Kieferhöhle hineinragen.\n- **Ausbreitung infizierten Materials** aus devitalen/abgestorbenen Zähnen in die Kieferhöhle.\n\n### 2. **Parodontalerkrankungen**\n- **Fortgeschrittene Parodontitis** mit Knochenabbau kann zu einer Kommunikation zwischen Mundhöhle und Sinus maxillaris führen und eine Infektion begünstigen.\n\n### 3. **Iatrogene Ursachen**\n- **Zahnextraktionen** (insbesondere der oberen Molaren/Prämolaren): Nach Entfernung kann es zu einer Eröffnung der Kieferhöhle (oroantrale Fistel) kommen, durch die Bakterien eindringen.\n- **Wurzelspitzenresektionen** und andere chirurgische Eingriffe im Oberkieferbereich.\n- **Fremdkörper** (z. B. Wurzelfüllmaterial, Zahnfragmente, Implantate), die versehentlich in die Kieferhöhle gelangen.\n\n### 4. **Zahnwurzelperforationen**\n- Bei tiefreichenden Kariesläsionen oder endodontischen Behandlungen kann es zur Perforation in die Kieferhöhle kommen.\n\n### 5. **Zysten und Tumoren odontogenen Ursprungs**\n- **Radikuläre Zysten** oder andere odontogene Zysten können in die Kieferhöhle einbrechen und diese infizieren.\n\n---\n\n#### **Zusammengefasst:**\nDie häufigsten Ursachen der odontogenen Sinusitis maxillaris sind **periapikale Infektionen (z. B. an den oberen Molaren), Parodontalerkrankungen, iatrogene Komplikationen wie Kieferhöhleneröffnung nach Zahnextraktion, Fremdkörper sowie odontogene Zysten oder Perforationen**.\n\n---\n\n**Quellen:**\n- DGMKG-Leitlinie \"Odontogene Infektionen\", 2020  \n- Hellwig E, Klimek J: Zahnmedizinische Propädeutik, Thieme 2015  \n- Brook I: Sinusitis of odontogenic origin. Otolaryngol Head Neck Surg. 2006\n\nGerne auf Wunsch ausführlicher zu einzelnen Ursachen!",
        "correctness_score": 4,
        "reason": "Die Antwort ist fachlich korrekt und sehr ausführlich, benennt zahlreiche Ursachen der odontogenen Sinusitis maxillaris mit passenden Erklärungen. Allerdings geht sie über den Rahmen der Frage hinaus, die konkret nach den häufigsten Ursachen fragt. Statt eine klare Priorisierung (z. B. Mund-Kieferhöhlen-Verbindung und apikale Parodontitis) zu geben, listet die Antwort viele Ursachen gleichwertig auf. Dadurch bleibt unklar, welche Ursachen am häufigsten sind.",
    },
    {
        "gen_res_id": "6875fb1dc6945aa0f11ec38c",
        "question": "Welche möglichen Indikationen können zur Entfernung von Weisheitszähnen bestehen?",
        "expected_answer": "Mögliche Indikationen zur Entfernung von Weisheitszähnen bestehen unter anderem zur Unterstützung kieferorthopädischer Maßnahmen, zur Vermeidung zukünftiger Komplikationen (z. B. bei eingeschränkter medizinischer Versorgung), bei Schäden an Nachbarzähnen, Karies mit Pulpaexposition, geplanter prothetischer Versorgung, geplanter Narkoseeingriffe, Störungen der Okklusion durch Elongation oder Kippung sowie therapieresistenter Halitosis.",
        "expected_retrievals": [
            {
                "guideline": "007-003 - Operative Entfernung von Weisheitszähnen",
                "retrieval": "Empfehlung: Mögliche Indikationen zur Entfernung von Weisheitszähnen\nEine Indikation kann bestehen:\na) zur Vereinfachung der kieferorthopädischen Zahnbewegungen und/oder zur Erleichterung der kieferorthopädischen Retention oder Sicherung einer abgeschlossenen KFO-Behandlung.\nb) zur prophylaktische Zahnentfernung aus übergeordneten, der Lebensführung zuzuordnenden Gesichtspunkten (z.B. fehlende Verfügbarkeit medizinischer Versorgung etc.)\nc) bei Resorptionen an benachbarten Zähnen (Siehe Hintergrundtext 9.2)\nd) bei Pulpaexposition durch Zahnkaries\ne) Bei Zähnen, die bei einer geplanten prothetischen Versorgung stören, wenn beispielsweise ein sekundärer Durchbruch aufgrund der weiteren Atrophie des Alveolarkammes bzw. aufgrund der Druckbelastung durch herausnehmbaren Zahnersatz zu erwarten steht\nf) wenn andere Maßnahmen unter Narkose vorgenommen werden und eine erneute Narkose zur Entfernung eines Weisheitszahnes durchgeführt werden müsste\ng) wenn der elongierte/gekippte Weisheitszahn eine Störung der dynamischen Okklusion darstellt\nStarker Konsens (6/6)",
            },
            {
                "guideline": "007-003 - Operative Entfernung von Weisheitszähnen",
                "retrieval": "Empfehlung: Mögliche Indikationen zur Entfernung von Weisheitszähnen\nEine Indikation kann bestehen: \nh) Wenn der Weisheitszahn die Ursache einer behandlungsbedürftigen Halitosis darstellt und andere, zahnerhaltende Therapiemaßnahmen nicht erfolgreich waren \nStarker Konsens (7/8, davon eine Enthaltung)",
            },
        ],
        "actual_response": "**Antwort:**\n\nDie **Entfernung von Weisheitszähnen** (dritte Molaren) ist nicht immer routinemäßig erforderlich, sondern sollte **indiziert** sein, also aus medizinischen Gründen erfolgen. Die wichtigsten **möglichen Indikationen** sind:\n\n---\n\n### **1. Akute Entzündungen**\n- **Perikoronitis:** Akute Entzündung des Zahnfleischs um einen (teil-)retinierten Weisheitszahn\n- **Abszessbildung:** Eiteransammlung im Bereich des Weisheitszahns\n- **Wiederholte Infektionen** (rezidivierende Perikoronitiden)\n\n### **2. Karies und Pulpitis**\n- **Karies am Weisheitszahn**, die nicht suffizient versorgt werden kann\n- **Karies am Nachbarzahn** durch Lage des Weisheitszahns\n- **Pulpitis oder apikale Parodontitis**\n\n### **3. Parodontale Probleme**\n- **Parodontitis** im Bereich des Weisheitszahns oder des benachbarten Zahns\n- **Taschenbildung** und Knochenabbau\n\n### **4. Platzmangel/Zahnverschiebungen**\n- **Druck- oder Engstandssymptome** (z. B. Verschiebung der Frontzähne)\n- **Fehlstellung** der Nachbarzähne durch den Weisheitszahn\n\n### **5. Retinierte, impaktierte oder verlagerte Weisheitszähne**\n- **Retiniert:** Zahn liegt im Kiefer und ist nicht durchgebrochen\n- **Impaktiert/verlagert:** Zahn ist in Fehlposition und kann nicht regelrecht durchbrechen\n\n### **6. Zysten oder Tumoren**\n- **Folgezysten** (z. B. dentigeröse Zysten)\n- **Odontogene Tumoren** im Zusammenhang mit Weisheitszähnen\n\n### **7. Prothetische/orthodontische Gründe**\n- **Geplante prothetische Versorgung** (z. B. Prothese, Brücke), bei der der Weisheitszahn stört\n- **Kieferorthopädische Behandlung** (z. B. zur Platzgewinnung)\n\n### **8. Vorbereitung auf bestimmte Therapien**\n- **Geplante Chemo-/Strahlentherapie** oder Organtransplantation (Infektionsprophylaxe)\n- **Vor Unterkieferfraktur-OPs** (Vermeidung von Komplikationen)\n\n### **9. Schmerzen und Beschwerden**\n- **Wiederkehrende Schmerzen**, auch ohne klare Ursache, sofern mit dem Zahn in Zusammenhang stehend\n\n### **10. Nicht-erhaltungswürdige Zähne**\n- **Zahn ist zerstört, kariös, frakturiert oder lässt sich nicht adäquat erhalten**\n\n---\n\n### **Zusammengefasst:**\n**Indikationen** zur Entfernung von Weisheitszähnen bestehen bei:  \n- akuten oder chronischen Entzündungen  \n- Karies/Pulpitis  \n- Parodontalproblemen  \n- Platzmangel/Zahnverschiebungen  \n- retinierten/impaktierten/verlagerten Zähnen  \n- Zysten/Tumoren  \n- prothetischen/orthodontischen Gründen  \n- Vorbereitung auf bestimmte Therapien  \n- Schmerzen oder nicht-erhaltungswürdigen Zähnen.\n\n---\n\n**Quellen:**  \n- DGMKG-Leitlinie „Operative Entfernung von Weisheitszähnen“, 2020  \n- Hellwig E, Klimek J: Zahnmedizinische Propädeutik, Thieme 2015\n\nGerne ausführlicher zu einzelnen Indikationen oder Kontraindikationen!",
        "correctness_score": 3,
        "reason": "Die Antwort enthält größtenteils korrekte Angaben zu möglichen Indikationen, weicht jedoch vom Fokus der Frage ab: Statt einer kompakten Auflistung medizinischer Gründe werden viele Zusatzinformationen, Erklärungen und allgemeine Hintergrundaspekte genannt. Dadurch wird die Antwort unnötig umfangreich und verliert an Präzision.",
    },
    {
        "gen_res_id": "6875fc04c6945aa0f11ec3ba",
        "question": "Bei Patient:innen mit entzündlich bedingten knöchernen Fehlbildungen des Kiefergelenks im Rahmen einer JIA – welches Verfahren kann nach abgeschlossenem Wachstum zur Verbesserung des harmonischen Gesichtsbildes eingesetzt werden?",
        "expected_answer": "Bei skelettalen Deformitäten kann nach abgeschlossenem Wachstum eine Genioplastik eingesetzt werden. Sie dient der Optimierung der fazialen Ästhetik und stellt ein konturverbesserndes Verfahren dar, das in der Literatur für Patient:innen im Alter von 17 bis 39 Jahren beschrieben ist.",
        
        "expected_retrievals": [
            {
                "guideline": "007-061 - Inflammatorische Erkrankungen des Kiefergelenks: Juvenile Idiopathische Arthritis (JIA) und Rheumatoide Arthritis (RA) des Kiefergelenks",
                "retrieval": "Diverse Autoren beschreiben einen Einsatz der Genioplastik bei JIA-Patienten im Alter von 17 bis 39 Jahren mit skelettalen Deformitäten als konturverbesserndes Verfahren zur Korrektur und Optimierung der fazialen Ästhetik.",
            },
            {
                "guideline": "007-061 - Inflammatorische Erkrankungen des Kiefergelenks: Juvenile Idiopathische Arthritis (JIA) und Rheumatoide Arthritis (RA) des Kiefergelenks",
                "retrieval": "Statement\nBei skelettalen Deformitäten im Rahmen einer Kiefergelenkbeteiligung bei JIA bzw. in Folge von JIA stellt die Genioplastik45 zur Korrektur der Okklusion und Optimierung der fazialen Ästhetik nach Wachstumsabschluss prinzipiell eine adäquate Behandlungsoption dar.\nEvidenzniveau: IV (Øye et al. 2003, IV/k-; Stoor et al. 2018, IV/k-); Starker Konsens",
            },
        ],
        "actual_response": "Bei Patient:innen mit **entzündlich bedingten knöchernen Fehlbildungen des Kiefergelenks im Rahmen einer juvenilen idiopathischen Arthritis (JIA)** kann nach abgeschlossenem Wachstum eine **orthognathe Umstellungsosteotomie** (z. B. **Bilateral Sagittale Spaltung des Unterkiefers [BSSO]**, Le-Fort-Osteotomie des Oberkiefers oder eine Kombination davon) zur **Verbesserung des harmonischen Gesichtsbildes** eingesetzt werden.\n\n**Begründung:**\n- Nach Abschluss des Gesichtsschädelwachstums können knöcherne Fehlstellungen und Asymmetrien chirurgisch korrigiert werden.\n- Ziel ist es, funktionelle und ästhetische Defizite (z. B. Kieferfehlstellungen, Gesichtsasymmetrie, Okklusionsstörungen) zu beheben und ein harmonisches Profil wiederherzustellen.\n\n**Vorgehen nach Leitlinie:**\n- Die Umstellungsosteotomie kann je nach Ausprägung als Ein- oder Zwei-Kiefer-OP (Kombination von Ober- und Unterkieferosteotomie) durchgeführt werden.\n- Voraussetzung ist **abgeschlossenes Wachstum** und **stabile Remission der Grunderkrankung**, um das Risiko für erneute Wachstumsstörungen und Rezidive zu minimieren.\n\n**Quellen:**\n- S2k-Leitlinie „Kiefergelenkbeteiligung bei JIA“, AWMF 027-041, 2021\n- DGKCH/DGMKG: Empfehlungen zur Diagnostik und Therapie der Kiefergelenkbeteiligung bei JIA\n- Hellwig E, Klimek J: Zahnmedizinische Propädeutik, Thieme 2015\n\n**Zusammengefasst:**  \n**Orthognathe Umstellungsosteotomien** (z. B. BSSO, Le-Fort-I-Osteotomie) sind das Verfahren der Wahl zur Harmonisierung des Gesichtsbildes nach abgeschlossenem Wachstum bei JIA-bedingten Kieferfehlbildungen.",
        "correctness_score": 2,
        "reason": "Die Antwort nennt fachlich richtige und relevante chirurgische Verfahren (z. B. BSSO, Le-Fort-I-Osteotomie), geht aber am Kern der Frage vorbei. Gefragt war nach einem ästhetisch konturierenden Verfahren zur Harmonisierung des Gesichtsbildes, nicht nach umfassenden knöchernen Umstellungen zur Korrektur von Fehlstellungen. Laut Leitlinie ist in solchen Fällen – insbesondere bei abgeschlossener Entwicklung und fehlender funktioneller Einschränkung – die Genioplastik ein empfohlenes Verfahren. Diese wird in der Antwort jedoch nicht erwähnt. Damit wird der Fokus der Frage verfehlt, auch wenn die Antwort inhaltlich korrekt ist.",
    },
    {
        "gen_res_id": "6875fb61c6945aa0f11ec39a",
        "question": "Wann und in welcher Form wird die chirurgische Therapie der odontogenen Sinusitis maxillaris leitliniengerecht empfohlen – und auf worauf sollte möglichst verzichtet werden?",
        "expected_answer": "Die chirurgische Therapie der odontogenen Sinusitis maxillaris wird leitliniengerecht empfohlen, wenn sich der ursächliche odontogene Prozess in die Kieferhöhle ausbreitet und/oder die Ventilation und Drainage der Kieferhöhle langfristig gestört sind. Ziel des Eingriffs ist die Sanierung der Entzündungsursache sowie – bei Bedarf – die Drainage der Kieferhöhle zur vollständigen Ausheilung.\n\nEin transorales Vorgehen wird bevorzugt, da es eine bessere Einsicht in den Recessus alveolaris und die anteriore mediale Kieferhöhlenwand ermöglicht. Die Drainage kann über eine Fensterung in den unteren oder mittleren Nasengang erfolgen.\n\nVerzichtet werden sollte auf die vollständige Ausräumung der Kieferhöhlenschleimhaut und die dauerhafte Entfernung des facialen Kieferhöhlendeckels.\n",
        "expected_retrievals": [
            {
                "guideline": "007-086 - Odontogene Sinusitis maxillaris",
                "retrieval": "\nDie operative Therapie der odontogenen Sinusitis maxillaris soll erfolgen, wenn sich der ursächliche pathologische odontogene Prozess in die Kieferhöhle ausdehnt und/oder die Ventilation und Drainage der Kieferhöhle langfristig gestört ist.\n8/8",
            },
            {
                "guideline": "007-086 - Odontogene Sinusitis maxillaris",
                "retrieval": "\nDie chirurgische Therapie soll dann die Sanierung der Entzündungsursache und bei Bedarf die\nDrainage der entzündlich veränderten Kieferhöhle mit dem Ziel der vollständigen Ausheilung\numfassen [Reinert 2014].\n8/8",
            },
            {
                "guideline": "007-086 - Odontogene Sinusitis maxillaris",
                "retrieval": "Empfehlung\nAuf die Ausräumung der Kieferhöhlenschleimhaut und die dauerhafte Entfernung des facialen\nKieferhöhlendeckels soll verzichtet werden.\n9/9",
            },
            {
                "guideline": "007-086 - Odontogene Sinusitis maxillaris",
                "retrieval": "Empfehlung\nEin transorales Vorgehen sollte bei dieser Indikation auf Grund der besseren Einsicht in den Recessus\nalveolaris und auf die anterior mediale Wand bevorzugt werden. [Lopatin 2002]\n9/9",
            },
            {
                "guideline": "007-086 - Odontogene Sinusitis maxillaris",
                "retrieval": "Empfehlung\nDie Drainage der Kieferhöhle zur Nase kann über eine Fensterung im unteren oder mittleren Nasengang erfolgen. [Arnes 1985]\n9/9",
            },
        ],
        "actual_response": "**Antwort:**\n\n### **Wann ist die chirurgische Therapie der odontogenen Sinusitis maxillaris leitliniengerecht angezeigt?**\n\nDie chirurgische Therapie wird nach den aktuellen Leitlinien (z. B. DGMKG-Leitlinie \"Odontogene Infektionen\", S2k-Leitlinie \"Rhinosinusitis\") **empfohlen, wenn**:\n\n- **Konservative Therapie (zahnärztliche Sanierung und medikamentöse Behandlung) nicht ausreicht** oder erfolglos bleibt.\n- **Komplikationen auftreten**, z. B. Abszessbildung, Ausbreitung in Nachbarstrukturen, drohende oder bestehende Orbitabeteiligung, Hirnhautentzündung, Fistelbildung.\n- **Chronische Verläufe** trotz konservativer Therapie bestehen.\n- **Fremdkörper** (z. B. Wurzelfüllmaterial, Zahnfragmente, Implantate) in der Kieferhöhle persistieren.\n- **Persistierende oroantrale Fistel** nach Zahnextraktion vorliegt.\n\n---\n\n### **In welcher Form wird die chirurgische Therapie empfohlen?**\n\n#### **1. Sanierung der Dentogenen Ursache**\n- **Entfernung der Infektionsquelle**: z. B. Extraktion des verursachenden Zahns, Wurzelkanalbehandlung, Entfernung von Fremdkörpern (Wurzelfüllmaterial, Zahnfragmente).\n\n#### **2. Chirurgische Sanierung der Kieferhöhle**\n- **Endonasale (funktionelle endoskopische) Sinusoperation (FESS):**\n  - Eröffnung und Drainage der Kieferhöhle über die Nase (mittlere Nasenmuschel, meatus medius), Entfernung von Sekret, Granulationen, ggf. Fremdkörpern.\n  - **Vorteil:** Minimal-invasiv, Erhalt der natürlichen Drainagewege.\n- **Transorale Kieferhöhlenrevision (z. B. nach Caldwell-Luc):**\n  - Nur noch selten bei ausgedehnten oder rezidivierenden Fällen.\n  - Zugang über die Mundhöhle (vestibulär) zur Kieferhöhle.\n\n---\n\n### **Worauf sollte möglichst verzichtet werden?**\n\n- **Alleinige transorale Kieferhöhlenoperation ohne Funktionserhalt** (klassische Caldwell-Luc-Operation) sollte **möglichst vermieden** werden, da sie das Risiko für chronische Entzündungen und Narbenbildung erhöht.\n- **Alleinige medikamentöse Therapie ohne Sanierung der Ursache**: Eine alleinige Antibiotikagabe oder abschwellende Medikation ohne Beseitigung der Ursache (z. B. Zahnextraktion, Entfernung von Fremdkörpern) ist **nicht zielführend**.\n- **Unnötig radikale Eingriffe** mit Schädigung der Schleimhaut oder knöchernen Strukturen sollen vermieden werden.\n\n---\n\n### **Zusammengefasst:**\n\n- **Chirurgische Therapie** der odontogenen Sinusitis maxillaris ist **leitliniengerecht angezeigt bei fehlendem Erfolg der konservativen Therapie, Komplikationen, chronischem Verlauf, persistierenden Fisteln oder Fremdkörperpersistenz**.\n- Die **Sanierung der dentogenen Ursache steht immer an erster Stelle**. Anschließend ggf. minimal-invasive endonasale oder in Ausnahmefällen transorale Sanierung der Kieferhöhle.\n- **Auf radikale, funktionseinschränkende Verfahren und alleinige medikamentöse Therapie ohne Ursachenbeseitigung sollte verzichtet werden.**\n\n---\n\n**Quellen:**  \n- DGMKG-Leitlinie „Odontogene Infektionen“, 2020  \n- S2k-Leitlinie „Rhinosinusitis“ (AWMF 017-049), 2017  \n- Hellwig E, Klimek J: Zahnmedizinische Propädeutik, Thieme 2015\n\nGerne auf Wunsch detaillierter zu OP-Techniken oder Ablauf!",
        "correctness_score": 1,
        "reason": "Die Antwort ist insgesamt medizinisch fundiert und nennt sinnvolle Indikationen und Verfahren. Allerdings widerspricht sie in wesentlichen Punkten den offiziellen Leitlinien. So wird etwa fälschlich die S2k-Leitlinie „Rhinosinusitis“ als Referenz angegeben, obwohl diese nicht für odontogene Sinusitiden zuständig ist. Auch wird die klassische Caldwell-Luc-Operation pauschal abgewertet, obwohl laut Leitlinie ein transorales Vorgehen bei odontogener Ursache bevorzugt wird – da es besseren Zugang zur vorderen Kieferhöhlenwand und zum Recessus alveolaris erlaubt. Die empfohlene Form der Drainage (z.B. Fensterung zum Nasengang) fehlt. Insgesamt weicht die Antwort somit deutlich vom erwarteten leitliniengerechten Vorgehen ab.",
    },
    {
        "gen_res_id": "68878263020043be7fda1fe3",
        "question": "In welchem Winkel soll die Wurzelspitzenresketion erfolgen?",
        "expected_answer": "Die Resektion der Wurzelspitze soll nahezu rechtwinklig zur Zahnachse erfolgen.",
        "expected_retrievals": [
            {
                "guideline": "007-007 - Wurzelspitzenresektion",
                "retrieval": "Empfehlung 9 (neu 2020)\nDie Resektion der Wurzelspitze soll nahezu rechtwinklig zur Zahnachse erfolgen. Anschließend sollen die Präparation einer retrograden, ca. 3 mm tiefen und zum Wurzelkanal achsgerechten Kavität sowie die Applikation einer retrograden Füllung erfolgen. Dies gilt jeweils, sofern es anatomisch möglich ist.\nAbstimmung: 10/13 (ja/ Anzahl der Stimmen)\nIm Verlauf des Verabschiedungsprozesses schlossen sich – entgegen der Abstimmung der Mandatstragenden – vier weitere Fachgesellschaften/ Organisationen dem Sondervotum zu Empfehlung 9 an. Drei weitere Fachgesellschaften/ Organisationen stimmten der Empfehlung in dieser Form nicht zu (s.u.)\nExpertenkonsens und weiterführende Literatur (Tabelle 15); Konsens",
            },
        ],
        "actual_response": "Die Wurzelspitzenresektion soll laut AWMF-Leitlinie 007-100 möglichst **orthogonal zur Längsachse der Wurzel**, also in einem Winkel von **0°–10°**, erfolgen. Dieses nahezu senkrechte Abtrennen der Wurzelspitze minimiert die Anzahl exponierter Dentintubuli, reduziert das Risiko von Mikroleckagen und verbessert die Voraussetzungen für eine dichte retrograde Wurzelfüllung sowie die Heilung.\n",
        "correctness_score": 1,
        "reason": "Die Antwort ist inhaltlich irreführend und weist mehrere gravierende Fehler auf:\n\n1. **Falsche Leitlinie genannt**: Es wird fälschlich auf die Leitlinie 007-100 (Mundhöhlenkarzinom) verwiesen – korrekt wäre 007-007 zur Wurzelspitzenresektion.\n2. **Falsch dargestellter Winkel**: Die Angabe „0°–10°“ ist weder in der korrekten Leitlinie enthalten noch medizinisch nachvollziehbar. Die Leitlinie fordert eine *nahezu rechtwinklige* Resektion – also etwa 90°, nicht 0°–10°.\n3. **Nicht gefragte Begründungen**: Es werden spekulative Aussagen zur Reduktion von Mikroleckagen und Dentintubuli gemacht, obwohl die Frage ausschließlich nach dem Winkel der Resektion fragt.\n\nDie Antwort enthält somit sachliche Fehler, eine falsche Quellenangabe und weicht deutlich von der geforderten knappen, leitliniengerechten Antwort ab.",
    },
    {
        "gen_res_id": "68876ed60741c76bdb4a0648",
        "question": "Wann und in welcher Form wird die chirurgische Therapie der odontogenen Sinusitis maxillaris leitliniengerecht empfohlen – und auf worauf sollte möglichst verzichtet werden?",
        "expected_answer": "Die chirurgische Therapie der odontogenen Sinusitis maxillaris wird leitliniengerecht empfohlen, wenn sich der ursächliche odontogene Prozess in die Kieferhöhle ausbreitet und/oder die Ventilation und Drainage der Kieferhöhle langfristig gestört sind. Ziel des Eingriffs ist die Sanierung der Entzündungsursache sowie – bei Bedarf – die Drainage der Kieferhöhle zur vollständigen Ausheilung.\n\nEin transorales Vorgehen wird bevorzugt, da es eine bessere Einsicht in den Recessus alveolaris und die anteriore mediale Kieferhöhlenwand ermöglicht. Die Drainage kann über eine Fensterung in den unteren oder mittleren Nasengang erfolgen.\n\nVerzichtet werden sollte auf die vollständige Ausräumung der Kieferhöhlenschleimhaut und die dauerhafte Entfernung des facialen Kieferhöhlendeckels.\n",
        "expected_retrievals": [
            {
                "guideline": "007-086 - Odontogene Sinusitis maxillaris",
                "retrieval": "\nDie operative Therapie der odontogenen Sinusitis maxillaris soll erfolgen, wenn sich der ursächliche pathologische odontogene Prozess in die Kieferhöhle ausdehnt und/oder die Ventilation und Drainage der Kieferhöhle langfristig gestört ist.\n8/8",
            },
            {
                "guideline": "007-086 - Odontogene Sinusitis maxillaris",
                "retrieval": "\nDie chirurgische Therapie soll dann die Sanierung der Entzündungsursache und bei Bedarf die\nDrainage der entzündlich veränderten Kieferhöhle mit dem Ziel der vollständigen Ausheilung\numfassen [Reinert 2014].\n8/8",
            },
            {
                "guideline": "007-086 - Odontogene Sinusitis maxillaris",
                "retrieval": "Empfehlung\nAuf die Ausräumung der Kieferhöhlenschleimhaut und die dauerhafte Entfernung des facialen\nKieferhöhlendeckels soll verzichtet werden.\n9/9",
            },
            {
                "guideline": "007-086 - Odontogene Sinusitis maxillaris",
                "retrieval": "Empfehlung\nEin transorales Vorgehen sollte bei dieser Indikation auf Grund der besseren Einsicht in den Recessus\nalveolaris und auf die anterior mediale Wand bevorzugt werden. [Lopatin 2002]\n9/9",
            },
            {
                "guideline": "007-086 - Odontogene Sinusitis maxillaris",
                "retrieval": "Empfehlung\nDie Drainage der Kieferhöhle zur Nase kann über eine Fensterung im unteren oder mittleren Nasengang erfolgen. [Arnes 1985]\n9/9",
            },
        ],
        "actual_response": "Die chirurgische Therapie der odontogenen Sinusitis maxillaris wird gemäß AWMF-Leitlinien 007-092 „Rhinosinusitis“ und 007-006 „Odontogene Infektionen“ unter bestimmten Voraussetzungen empfohlen. Das leitliniengerechte Vorgehen orientiert sich an Ursache, Ausprägung und Verlauf der Sinusitis.\n\n**Schrittweise leitliniengerechte Herleitung:**\n\n1. **Indikation für eine chirurgische Therapie:**  \n   - Eine chirurgische Therapie ist angezeigt, wenn:\n     - Eine **oroantrale Verbindung** (Kommunikation zwischen Mundhöhle und Kieferhöhle, z.B. nach Zahnextraktion) vorliegt.\n     - **Persistierende oder rezidivierende Beschwerden** bestehen, die sich unter konservativer Therapie (Antibiotika, Nasenspülung, Abschwellung) nicht bessern.\n     - Eine **persistierende Infektion** oder Fremdkörper (z.B. Wurzelreste, Füllungsmaterial, Sequester) in der Kieferhöhle nachweisbar sind.\n     - Eine **chronische odontogene Sinusitis** besteht.\n\n2. **Form der chirurgischen Therapie (empfohlene Verfahren):**  \n   - **Sanierung des odontogenen Fokus:**  \n     - Entfernung verbliebener infizierter Zahn- oder Knochenanteile, Fremdkörper oder Sequester.\n   - **Verschluss einer oroantralen Verbindung:**  \n     - Primärer Wundverschluss mittels Schleimhaut- oder Verschiebelappen, abhängig von der Defektgröße.\n   - **Kieferhöhlensanierung:**  \n     - Das bevorzugte Verfahren ist die **endoskopisch-endonasale Antrostomie** (mittlere Nasenmuschel), da sie minimalinvasiv ist und eine effektive Drainage und Belüftung der Kieferhöhle ermöglicht.\n     - Bei speziellen anatomischen Situationen kann auch ein transoraler Zugang mit Entfernung des Fremdkörpers und Spülung der Kieferhöhle notwendig sein.\n   - **Kombinierte Verfahren** sind bei komplexen Situationen möglich.\n\n3. **Worauf sollte verzichtet werden?**  \n   - Auf ein **alleiniges, wiederholtes Spülen der Kieferhöhle** ohne Beseitigung der Ursache (z.B. Entfernung des Fremdkörpers, Verschluss der oroantralen Verbindung) sollte verzichtet werden.\n   - Die **alleinige Antibiotikatherapie** ohne chirurgische Sanierung reicht bei nachgewiesener oroantraler Verbindung oder persistierender Infektion nicht aus.\n   - **Radikale, großflächige transantrale Eingriffe** (z.B. Caldwell-Luc-Operation) sollen, wenn möglich, vermieden werden, da sie mit erhöhter Morbidität und schlechterer Funktion assoziiert sind.\n\n**Zusammenfassung:**  \nEine chirurgische Therapie der odontogenen Sinusitis maxillaris ist bei nachgewiesener oroantraler Verbindung, persistierender Infektion, Fremdkörpern oder chronischen Verläufen indiziert. Leitliniengerecht wird eine minimalinvasive, meist endoskopisch-endonasale Sanierung mit Sanierung des odontogenen Fokus und Defektverschluss empfohlen. Auf alleinige symptomatische Maßnahmen (z.B. wiederholte Spülungen, alleinige Antibiose) und auf großflächig radikale transantrale Eingriffe sollte möglichst verzichtet werden.\n\n**Quellen:**  \n- AWMF-Leitlinie 007-092: Rhinosinusitis, Kapitel „Odontogene Sinusitis“  \n- AWMF-Leitlinie 007-006: Odontogene Infektionen",
        "correctness_score": 4,
        "reason": "Die Antwort ist fachlich korrekt und deckt alle Aspekte der Frage umfassend ab, inklusive Indikation, bevorzugter chirurgischer Zugänge und zu vermeidender Maßnahmen. Sie bezieht sich inhaltlich auf die korrekte Leitlinie (007-086), nennt jedoch fälschlicherweise andere Registernummern (007-092, 007-006), was als Kontextfehler gewertet wird. Die ausführliche Darstellung geht leicht über die Frage hinaus, ist jedoch insgesamt hilfreich und nicht irreführend. Daher ist die Antwort weitgehend korrekt, aber nicht perfekt.",
    },
    {
        "gen_res_id": "6875fbbcc6945aa0f11ec3ac",
        "question": "Welches Gelenk ist am häufigsten von einer JIA betroffen?",
        "expected_answer": "Das Temporomandibulargelenk ist eines der am häufigsten betroffenen Gelenke bei JIA.",
        "expected_retrievals": [
            {
                "guideline": "007-061 - Inflammatorische Erkrankungen des Kiefergelenks: Juvenile Idiopathische Arthritis (JIA) und Rheumatoide Arthritis (RA) des Kiefergelenks",
                "retrieval": "11 bis 87% der Patienten zeigen Zeichen einer Kiefergelenkbeteiligung (siehe Anhang, Abschnitt 10.2.4), was das Temporomandibulargelenk zu einem der am häufigsten betroffenen Gelenke bei JIA macht (Weiss et al. 2008; Tzaribachev et al. 2010).",
            },
        ],
        "actual_response": "Das **am häufigsten von einer juvenilen idiopathischen Arthritis (JIA) betroffene Gelenk** ist das **Kniegelenk**.\n\n---\n\n**Begründung:**\n\n- In den meisten epidemiologischen Studien und laut S2k-Leitlinie „Juvenile idiopathische Arthritis – Diagnostik und Therapie“ (AWMF 027-041) ist das Kniegelenk dasjenige, das bei Kindern mit JIA am häufigsten als erstes oder im Verlauf betroffen ist.\n- Gerade bei der häufigsten Form, der oligoartikulären JIA, ist das Kniegelenk die mit Abstand am häufigsten betroffene Lokalisation.\n\n---\n\n**Quellen:**  \n- S2k-Leitlinie „Juvenile idiopathische Arthritis – Diagnostik und Therapie“ (AWMF 027-041), 2021  \n- Petty RE et al., J Rheumatol 2004;31:390–2  \n- Weiss A, et al. Monatsschrift Kinderheilkunde 2019\n\n---\n\n**Kurzantwort:**  \n**Das Kniegelenk ist das am häufigsten von einer JIA betroffene Gelenk.**",
        "correctness_score": 1,
        "reason": "Die Antwort nennt mit dem Kniegelenk eine falsche Hauptlokalisation für JIA im gegebenen Kontext. Die zugrundeliegende Leitlinie 007-061 behandelt gezielt die Kiefergelenkbeteiligung und nennt das Temporomandibulargelenk als eines der am häufigsten betroffenen Gelenke bei JIA (mit Prävalenzen von bis zu 87 %). Die Antwort weicht inhaltlich vollständig vom erwarteten Fokus ab, zitiert eine fachfremde Leitlinie (027-041) und liefert damit eine irreführende Kernbotschaft. Trotz formaler Korrektheit der Aussage im allgemeinen JIA-Kontext ist sie für die gestellte Frage im MKG-spezifischen Rahmen unbrauchbar.",
    },
    {
        "gen_res_id": "6875fad2c6945aa0f11ec378",
        "question": "Was ist die Therapie der Wahl bei einer odontogenne Infektion mit und ohne Ausbreitungstendenz?",
        "expected_answer": "Bei einer odontogenen Infektion ohne Ausbreitungstendenz ist die Inzision mit anschließender Drainage die Therapie der Wahl. Die Eröffnung ermöglicht einen Abfluss des Eiters und versorgt das Gewebe mit Sauerstoff. Als Drainagen kommen Gummilaschen, Röhrchen oder Gazestreifen zum Einsatz.\n\nBei einer odontogenen Infektion mit Ausbreitungstendenz ist eine möglichst rasche chirurgische Therapie erforderlich, um eine effektive Entlastung und Drainage zu gewährleisten und einer weiteren Ausbreitung entgegenzuwirken. Die Eröffnung erfolgt in der Regel in Allgemeinanästhesie und beinhaltet die Einlage von Drains in die betroffenen Logen. Zusätzlich wird ein Abstrich zur mikrobiologischen Diagnostik entnommen, um gegebenenfalls eine gezielte Antibiotikatherapie einleiten zu können.",
        "expected_retrievals": [
            {
                "guideline": "007-006 - Odontogene Infektionen",
                "retrieval": "Konsensbasierte Empfehlung\nDie Behandlung des Infiltrates oder der lokalen odontogenen Infektion soll aus Drainage (z.B. Trepanation, Inzision, Scaling/ Kürettage) und Beseitigung der odontogenen Infektionsursache bestehen. Es können im Verlauf Folgetherapien notwendig sein, um die odontogene Ursache zu beseitigen.\nKonsensstärke: 17/17",
            },
            {
                "guideline": "007-006 - Odontogene Infektionen",
                "retrieval": "Neben den bereits genannten Verfahren stellt die chirurgische Intervention durch Inzision einer odontogenen Infektion die Therapie der Wahl dar [132]. Bei lokalen odontogenen Infektionen ist eine Entlastung in Lokalanästhesie von enoral möglich. Bei Patienten mit einer Blutgerinnungsstörung oder unter Antikoagulanzientherapie ist es in ausgewählten Fällen möglich, durch eine Punktion der odontogenen Infektion eine Blutung oder Nachblutung zu vermeiden [112, 133]. Im Ultraschall ist eine Identifikation der Abszesshöhle und im Ausnahmefall die geführte Punktion möglich [134]. Die Einlage eines Drains (z.B.: Gummilasche, Rohr oder Gaze) in die Inzisionswunde ermöglicht einen Abfluss des Eiters, und durch die Eröffnung wird das Gewebe mit Sauerstoff versorgt. ",
            },
            {
                "guideline": "007-006 - Odontogene Infektionen",
                "retrieval": "Zeigt sich bei einer odontogenen Infektion eine Ausbreitungstendenz, ist eine möglichst schnelle chirurgische Therapie Mittel der Wahl, um eine Entlastung und Drainage zu ermöglichen und einer weiteren Ausbreitung entgegenzuwirken [91, 137]. Die Eröffnung einer odontogenen Infektion mit Ausbreitungstendenz in Allgemeinanästhesie ermöglicht es, eine schmerzfreie Therapie durchzuführen. Hierbei werden Drains in die betroffenen Logen eingelegt [114]. ",
            },
        ],
        "actual_response": "**Antwort:**\n\nDie **Therapie der Wahl bei einer odontogenen Infektion** richtet sich nach dem Ausmaß der Infektion und danach, ob eine Ausbreitungstendenz besteht.\n\n---\n\n### 1. **Ohne Ausbreitungstendenz (lokalisierte Infektion)**\n- **Therapie der Wahl:**  \n  - **Sicherung und Wiederherstellung der Drainage**: Das bedeutet die Beseitigung der Infektionsursache, z. B. durch\n    - Eröffnung und Drainage eines Abszesses\n    - Trepanation des Zahnes (Zugang zur Pulpa, ggf. Wurzelkanalbehandlung)\n    - Entfernung des infizierten Zahnes (Extraktion), falls nicht erhaltungswürdig\n  - **Lokale Behandlung**: Spülung, ggf. lokale Antiseptika\n  - **Antibiotikagabe:** *Nur bei systemischen Symptomen (Fieber, Ausbreitung, Immunsuppression) notwendig!* Bei unkomplizierten, lokalisierten Infektionen ohne Allgemeinsymptome ist eine alleinige chirurgische Sanierung meist ausreichend.\n\n---\n\n### 2. **Mit Ausbreitungstendenz (z. B. phlegmonöse Infektion, Ausbreitung in Weichteilräume, drohende oder bestehende Komplikationen)**\n- **Therapie der Wahl:**\n  - **Chirurgische Sanierung der Infektionsquelle**: wie oben (Drainage, Zahnsanierung/Extraktion)\n  - **Inzision und Drainage** betroffener Weichteilräume\n  - **Unverzügliche systemische Antibiotikatherapie** (Breitbandantibiotika, z. B. Amoxicillin/Clavulansäure, in schweren Fällen ggf. zusätzlich Clindamycin oder Metronidazol bei Penicillinallergie)\n  - **Stationäre Aufnahme** bei schwerem Verlauf, systemischen Zeichen, Ausbreitung in tiefe Räume, drohender Atemwegsenge, Immunsuppression etc.\n  - **Begleitmaßnahmen:** Schmerztherapie, ggf. Flüssigkeitssubstitution, Überwachung\n\n---\n\n### **Merke:**  \nDie **Beseitigung der Ursache (Sanierung des infizierten Zahnes und ggf. Abszessdrainage)** steht immer im Vordergrund – die **Antibiotikatherapie ist bei komplizierten Verläufen oder Ausbreitungstendenz essenziell** und kann eine chirurgische Sanierung nicht ersetzen!\n\n---\n\n**Quellen:**  \n- DGMKG-Leitlinie „Odontogene Infektionen“ 2020  \n- Hellwig, E.; Klimek, J.: Zahnmedizinische Propädeutik, Thieme  \n- Zimmermann RE, Gellrich NC: Mund-Kiefer-Gesichtsinfektionen, Thieme 2018\n\nGerne auf Wunsch konkrete Antibiotika-Schemata oder Details zur chirurgischen Versorgung!",
        "correctness_score": 2,
        "reason": "Die Antwort enthält viele korrekte medizinische Aussagen, weicht jedoch mehrfach vom eigentlichen Leitlinienfokus ab. Sie geht über die Frage hinaus, indem sie ausführlich auf Antibiotikatherapie, stationäre Aufnahme und systemische Maßnahmen eingeht, obwohl diese in der Leitlinie 007-006 zur Therapie der Wahl nicht zentral betont werden. Die Formulierung zur Antibiotikagabe (nur bei Allgemeinsymptomen notwendig) steht im Widerspruch zur Leitlinie, die bei Ausbreitungstendenz eine sofortige chirurgische Intervention als essenziell beschreibt. Außerdem werden zusätzliche, nicht genannte Optionen wie Trepanation oder Zahnentfernung als Standard dargestellt, obwohl diese nicht als primäre Therapie der Wahl betont werden. Insgesamt ist die Antwort durch Überinformation, falsche Gewichtung und begrenzt korrekte Aussagen nur eingeschränkt brauchbar.",
    },
    {
        "gen_res_id": "68789f7237dbaee7a7a73c4f",
        "question": "Für welche Erkrankung steht JAI?",
        "expected_answer": "\"JAI\" ist ein Tippfehler. War \"JIA\" gemeint? Dies steht für Juvenile idiopathische Arthritis.",
        "expected_retrievals": [
            {
                "guideline": "007-061 - Inflammatorische Erkrankungen des Kiefergelenks: Juvenile Idiopathische Arthritis (JIA) und Rheumatoide Arthritis (RA) des Kiefergelenks",
                "retrieval": "JIA Juvenile idiopathische Arthritis",
            },
        ],
        "actual_response": "In den offiziellen AWMF-Leitlinien findet sich keine gängige medizinische Abkürzung „JAI“, die eindeutig einer bestimmten Erkrankung zugeordnet ist. Es gibt keine Leitlinie, die den Begriff „JAI“ als anerkannte Abkürzung für eine spezifische Erkrankung verwendet. \n\nSollten Sie eine spezielle Erkrankung oder einen bestimmten Kontext meinen, empfiehlt sich eine genauere Spezifizierung. Auf Grundlage der AWMF-Leitlinien kann hierzu keine exakte Aussage getroffen werden.\n</answer>",
        "correctness_score": 4,
        "reason": "„JAI“ ist kein valider Begriff in den Leitlinien. Die Antwort erkennt dies korrekt, vermeidet Halluzinationen und bleibt im fachlichen Rahmen. Daher vollständig korrekt, auch wenn eine Korrektur zu JIA idealer wäre.",
    },
]


class GPTScoreEvaluator:
    """
    Use LlamaIndex to get a correctness evaluator: https://docs.llamaindex.ai/en/stable/api_reference/evaluation/correctness/
    """
    
    def __init__(
            self,
            model: str = "azure-gpt-4.1",
            api_version: str = "2024-08-01-preview",
            temperature: float = 0.7,
            max_tokens: int = 1024,
    ):
        self.api_key = os.getenv("AZURE_OPENAI_API_KEY", "")
        self.api_base = os.getenv("AZURE_OPENAI_API_BASE", "")
        self.api_version = api_version
        self.deployment_name = model
        
        logger.info(f"[GPTScoreEvaluator] Using Azure model: {self.deployment_name}")
        self.llm = AzureOpenAILlamaIndexLLM(
            deployment_name=self.deployment_name,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=self.api_key,
            api_base=self.api_base,
            api_version=self.api_version,
        )
        
        def format_reference_answer(i):
            expected_answer = _examples[i]["expected_answer"]
            expected_retrieval = _examples[i].get("expected_retrievals", [])
            return f"Answer: {expected_answer}\nRetrieval:\n" + ((
                                                                     "\n".join(
                                                                         f"Retrieval {i}: {er['guideline']}; {er['retrieval']}" for i, er in
                                                                         enumerate(expected_retrieval),
                                                                     )
                                                                 ) if len(expected_retrieval) > 0 else "/")
        
        def format_example(i):
            return f"""# Example {i + 1}
## User Query
{_examples[i]["question"]}

## Reference Answer
{format_reference_answer(i)}

## Generated Answer
{_examples[i]["actual_response"]}

&rarr; Response
{_examples[i]["reason"]}
{_examples[i]["correctness_score"]}"""
        
        example_prompt = '\n\n---\n'.join(format_example(i) for i in range(len(_examples))) if _examples else "/"
        system_prompt = f"""You are an expert evaluation system for a German clinical question answering chatbot based on guidelines from the AWMF (Arbeitsgemeinschaft der Wissenschaftlichen Medizinischen Fachgesellschaften e.V. – Association of the Scientific Medical Societies in Germany).

Given:
- a **user question**,
- a **generated answer**, and
- a **reference answer** (ground truth),
- the **correct grounding in guideline information** (relevant text passages from medical guidelines to answer question).

Your task is to assess the **clinical correctness and relevance** of the generated answer compared to the reference.

**Respond with exactly two lines**:
1. **Reasoning in German** explaining your judgment.
2. A **single score between 1 to 5**, representing your holistic evaluation.

Scoring Rules
- Score must be a value between 1 and 5, where 1 = worst, 5 = best.
- The score reflects how completely and precisely the generated answer covers the reference. Consider:
  - Coverage of relevant content from the reference,
  - Factual and clinical correctness of the answer,
  - Focus on the actual question (no off-topic or misleading additions).

Score Definitions (in German, since the reasoning will also be German)
- **5 – Perfekt**: Präzise, vollständig und korrekt, leitliniengetreu, sprachlich klar und zielgerichtet. Ohne (oder sehr wenige) nicht notwendige Ausführungen oder Interpretationen.
    - Keine sachlichen Fehler; Knapp, präzise, medizinisch korrekt; Sprachlich klar und zielgerichtet; Keine unnötigen Zusätze oder Interpretationen
- **4 – Weitgehend korrekt**: Kerninhalt stimmt (noch immer Leitlinien-gerecht), evtl. sprachlich oder strukturell schwächer, keine wesentlichen Auslassungen, evtl. zu ausführlich.
    - Aussage sinngemäß korrekt, ggf. leicht verkürzt oder umformuliert; Keine irreführenden Ergänzungen; Ggf. etwas zu lang oder sprachlich unpräzise
- **3 – Teilweise korrekt**: Antwort enthält richtige Kernaussage, aber ist unvollständig, ungenau oder enthält kleinere faktische oder sprachliche Fehler.
    - Relevante Aussagen vorhanden, aber ungenau oder falsch gewichtet; Begriffe unsauber oder missverständlich; Struktur oder Argumentation problematisch
- **2 – Schwach**: Kern der Antwort fehlt oder ist verzerrt, einige Aussagen sind nicht nachvollziehbar, teils sinnlose/erfundene Inhalte, aber einzelne relevante Elemente vorhanden.
    - Wichtige Inhalte fehlen oder sind falsch dargestellt; Korrekte Begriffe ohne klaren Kontext; Viele unzutreffende, spekulative oder erfundene Aussagen
- **1 – Unbrauchbar**: Antwort ist falsch oder irreführend, gibt falsche Empfehlungen, entscheidende Inhalte fehlen, medizinisch falsch, oder enthält größere Mengen irrelevanter/phantastischer Inhalte. Auch wenn richtige Elemente enhalten sind, die überschattet werden von grabierenden Falschinformationen.
    - Nicht leitliniengerecht; Inhaltlich widersprüchlich oder phantastisch; Keine verwertbare Aussage, ggf. kontraindiziert;

---

The following will present example

{example_prompt}
"""
        
        def output_parser(eval_response: str) -> Tuple[Optional[float], Optional[str]]:
            """
            Parses LLM evaluation output:
            - Reasoning can span multiple lines
            - Score must be the last non-empty line with digits (1–5), optionally decimal
            """
            logger.warning(f"[output_parser] eval_response: {eval_response}")
            if not eval_response.strip():
                return None, "No response"
            
            # Regex pattern:
            # - (?s) → dot matches newline
            # - (.*\S) → capture reasoning with at least one non-space character
            # - \s* → allow any whitespace/newlines
            # - (\d+(?:\.\d+)?) → score (e.g., 4 or 4.0)
            # Full match: capture all reasoning before last float on its own line
            match = re.match(r"(?s)(.*\S)\s+(\d+(?:\.\d+)?)\s*$", eval_response.strip())
            if match:
                reasoning = match.group(1).strip()
                score_str = match.group(2).strip()
                try:
                    score = float(score_str)
                except ValueError:
                    score = None
                return score, reasoning
            
            # Fallback
            return None, eval_response.strip()
        
        self.evaluator = CorrectnessEvaluator(
            llm=self.llm,
            eval_template=ChatPromptTemplate(
                message_templates=[
                    ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
                    ChatMessage(role=MessageRole.USER, content=DEFAULT_USER_TEMPLATE),
                ],
            ),
            parser_function=output_parser,
        )
    
    async def evaluate_similarity_with_reason(
            self, question: str, expected_answer: str, actual_response: str, expected_retrieval: List[Dict[str, str]],
    ) -> Dict[str, Union[int, str]]:
        try:
            reference = f"Answer: {expected_answer}\nRetrieval:\n" + (
                ("\n".join(f"Retrieval {i}: {er['guideline']}; {er['content']}" for i, er in enumerate(expected_retrieval))
                 ) if len(expected_retrieval) > 0 else "/")
            result = self.evaluator.evaluate(
                query=question,
                reference=reference,
                response=actual_response,
            )  # It outputs a score between 1 and 5, where 1 is the worst and 5 is the best, along with reasoning for the score.
            if asyncio.iscoroutine(result):
                result = await result
            
            return {
                "similarity": result.score if result.score is not None else 1.0,
                "reason": result.feedback or "/",
            }
        
        except Exception as e:
            logger.error(f"[evaluate_similarity_with_reason] Failed to evaluate: {e}", exc_info=True)
            raise RuntimeError(f"Similarity evaluation failed: {e}")
