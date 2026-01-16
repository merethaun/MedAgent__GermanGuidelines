import re
from abc import abstractmethod
from typing import Dict, Type, Any, Optional, Tuple, List, Union

from rapidfuzz.distance import Levenshtein

from app.models.chat.chat import WorkflowComponentExecutionResult
from app.services.system.components import AbstractComponent, render_template
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_HyDE_MULTI_PROMPT = """You generate concise hypothetical documents ("HyDE") for a given question to improve retrieval.
Write AT MOST {num_docs} documents.
{document_description}

Think briefly to decide what to write, but OUTPUT ONLY the final hypothetical documents.
Limit EACH document to at most {target_tokens} tokens.
Use STRICT formatting (this is mandatory):
<document>
...single document text...
</document>
(repeat until maximum of {num_docs} documents are produced)

{few_shot_examples}

QUESTION:
\"\"\"{question}\"\"\"

OUTPUT:
Return AT MOST {num_docs} <document>...</document> blocks.
Do NOT nest these blocks, and make sure for each <document>, there also in an ending statement </document>
If no useful document can be generated, return an empty string.
"""


class AbstractHyDEGenerator(AbstractComponent, variant_name="hyde_generator"):
    variants: Dict[str, Type['AbstractHyDEGenerator']] = {}
    
    default_parameters: Dict[str, Any] = {
        "num_documents": 1,
        "target_tokens": 309,
        "question": "f'{start.current_user_input}'",
        "document_description": "German guidelines for Oral and Maxillofacial surgery from the AWMF (Arbeitsgemeinschaft der Wissenschaftlichen Medizinischen Fachgesellschaften e.V. – Association of the Scientific Medical Societies in Germany). If relevant, prefer definitions, indications/contraindications, core diagnostics, and first-line therapy. If a query does not relate to the topic, do not fabricate irrelevant potential answers.",
        "examples": [
            {
                "question": "Welche Symptome können im Zusammenhang mit Weisheitszähne vorkommen?",
                "documents": "Klinische und radiologische Symptome im Zusammenhang mit Weisheitszähnen können typischerweise sein:\n Perikoronare Infektion; Erweiterung des radiologischen Perikoronarraumes; Perikoronare Auftreibung (beispielsweise durch Zystenbildung); Schmerzen/Spannungsgefühl im Kiefer-Gesichtsbereich; Parodontale Schäden, insbesondere distal an 12-Jahr Molaren; Resorptionen an Nachbarzähnen; Elongation/Kippung; kariöse Zerstörung/Pulpitis",
            },
            {
                "question": "Wann kann die Nachsorge einer odontogenen Infektion ambulant erfolgen?",
                "documents": [
                    "Die Nachsorge sollte bis zum Abklingen der Symptome der odontogenen Infektion regelmäßig und in kurzen Abständen erfolgen.",
                    "Bei ambulant geführten Patienten sollte der eingelegte Drain spätestens jeden zweiten bis dritten, Tag gewechselt werden.",
                ],
            },
            {
                "question": "Unter welchen Voraussetzungen ist eine Synovialbiopsie am Kiefergelenk bei Patient:innen mit JIA indiziert, und welche besonderen Einschränkungen gelten für Kinder und Jugendliche?",
                "documents": [
                    "Eine Synovialbiopsie, die unabhängig von einer anderweitig indizierten Intervention stattfindet, soll zur Vermeidung von nicht unbedingt notwendigen Eingriffen einer strengen Indikationsstellung unterliegen – dies gilt insbesondere für Patienten ≤ 17 Jahre.",
                    "Bei klinischen Hinweisen auf strukturelle Schäden und Schmerzfreiheit („stille Kiefergelenkarthritis“) sowie grenzwertigen Befunden26 in der MRT-Diagnostik kann bei Patienten > 17 Jahre im Einzelfall eine Entnahme und Untersuchung von synovialer Flüssigkeit aus dem Kiefergelenk erwogen werden.",
                ],
            },
        ],
        "min_chars": 64,
        "max_levenstein_similarity": 0.9,
    }
    
    def __init__(self, component_id, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        self.next_component_id = None
    
    def __init_subclass__(cls, variant_name: Optional[str] = None, **kwargs):
        super().__init_subclass__(**kwargs)
        if variant_name:
            AbstractHyDEGenerator.variants[variant_name] = cls
    
    def set_next_component(self, next_component_id: str):
        self.next_component_id = next_component_id
    
    @abstractmethod
    def load_execution_result(self, result: WorkflowComponentExecutionResult):
        pass
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "num_documents": {
                "type": "int",
                "description": "How many hypothetical documents to generate (d)",
                "default": 1,
            },
            "target_tokens": {
                "type": "int",
                "description": "Max tokens per document (instructional hint to the model)",
                "default": 160,
            },
            "document_description": {
                "type": "string",
                "description": "Describe the nature of the documents (style/content expectations)",
                "default": "guideline-style answer paragraphs",
            },
            "examples": {
                "type": "list",
                "description": "Few-shot examples as [{'question': str, 'output': str}]",
                "default": [],
            },
            "min_chars": {
                "type": "int",
                "description": "Drop very short/boilerplate outputs (based on unique char count)",
                "default": 64,
            },
            "max_levenstein_similarity": {
                "type": "float",
                "description": "Drop very similar outputs (based on Levenstein distance) -> Lexical similarity gate",
                "default": 0.9,
            },
        }
    
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "generator.hyde_prompt": {
                "type": "string",
                "description": "The FULL HyDE prompt that was sent to the model (for audit/logging)",
            },
            "hyde_generator.full_response": {
                "type": "string",
                "description": "The FULL response from the HyDE generator",
            },
            "hyde_generator.filtered_hyde_docs": {
                "type": "list",
                "description": "List[str]: individual documents extracted from <document>...</document> blocks (and filtered based on min_chars and min_levenstein_distance)",
            },
        }
    
    @abstractmethod
    def generate_response(self, prompt: str) -> str:
        pass
    
    @staticmethod
    def _render_prompt(
            num_documents: int, target_tokens: int, question: str, document_description: str, examples: List[Dict[str, Union[str, List[str]]]],
    ) -> str:
        rendered_examples = []
        for i, example in enumerate(examples):
            q = example.get("question", "").strip()
            docs = example.get("documents", [])
            if isinstance(docs, str):
                docs = [docs]
            
            if not q or not docs:
                continue
            
            rendered_docs = '\n'.join(f"<document>\n{d}\n</document>" for d in docs)
            rendered_examples.append(
                f"""Example {i + 1}:
    Question: {q}
    Output: {rendered_docs}""",
            )
        
        prompt = _HyDE_MULTI_PROMPT.format(
            num_docs=num_documents,
            target_tokens=target_tokens,
            question=question,
            document_description=("Follow this style: " + document_description) if document_description else "",
            few_shot_examples=(
                    "\n---\nFEW-SHOT EXAMPLES (format is mandatory):\n" + "\n".join(rendered_examples) + "\n---\n"
            ) if rendered_examples else "",
        )
        return prompt
    
    @staticmethod
    def _extract_documents(raw_text: str) -> List[str]:
        if not raw_text:
            return []
        # case-insensitive, dotall
        blocks = re.findall(r"<document>\s*(.*?)\s*</document>", raw_text, flags=re.IGNORECASE | re.DOTALL)
        
        docs: List[str] = []
        for b in blocks:
            t = (b or "").strip()
            if t:
                docs.append(t)
        
        return docs
    
    @staticmethod
    def _filter_documents(docs: List[str], min_chars: int, max_levenstein_similarity: int) -> List[str]:
        if not docs:
            return []
        
        filtered_docs = []
        kept_norm: List[str] = []
        
        for doc in docs:
            if len(doc) < min_chars:
                continue
            
            norm_doc = " ".join(doc.lower().split())
            if all(Levenshtein.normalized_similarity(norm_doc, f) <= max_levenstein_similarity for f in kept_norm):
                kept_norm.append(norm_doc)
                filtered_docs.append(doc)
            else:
                continue
        
        return filtered_docs
    
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        num_documents = self.parameters.get("num_documents") or self.default_parameters.get("num_documents")
        target_tokens = self.parameters.get("target_tokens") or self.default_parameters.get("target_tokens")
        question_template = self.parameters.get("question") or self.default_parameters.get("question")
        document_description = self.parameters.get("document_description") or self.default_parameters.get("document_description")
        examples = self.parameters.get("examples") or self.default_parameters.get("examples")
        
        min_chars = self.parameters.get("min_chars") or self.default_parameters.get("min_chars")
        max_levenstein_similarity = self.parameters.get("max_levenstein_similarity") or self.default_parameters.get("max_levenstein_similarity")
        
        question = render_template(question_template, data)
        hyde_prompt = self._render_prompt(num_documents, target_tokens, question, document_description, examples)
        data[f"{self.id}.hyde_prompt"] = hyde_prompt
        
        full_response = self.generate_response(hyde_prompt)
        data[f"{self.id}.full_response"] = full_response
        
        docs = self._extract_documents(full_response)
        filtered_docs = self._filter_documents(docs, min_chars, max_levenstein_similarity)
        data[f"{self.id}.filtered_hyde_docs"] = filtered_docs
        
        return data, self.next_component_id
