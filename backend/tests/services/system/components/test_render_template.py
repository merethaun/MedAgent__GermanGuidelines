import unittest

from app.services.system.components.render_template import render_template
from app.utils.logger import setup_logger

logger = setup_logger(log_to_console=True, name="TEST_backend")


class TestRenderTemplate(unittest.TestCase):
    
    def test_direct_dict_output(self):
        template = "{test}"
        context = {"test": {"test_obj": 1}}
        result = render_template(template, context)
        logger.info("Test: Direct dict output => %s", result)
        self.assertEqual(result, {"test_obj": 1})
    
    def test_fstring_with_dict_access(self):
        template = "f'Test: {test[\"test_obj\"]}'"
        context = {"test": {"test_obj": 1}}
        result = render_template(template, context)
        logger.info("Test: f-string with dict access => %s", result)
        self.assertEqual(result, "Test: 1")
    
    def test_expression_evaluation(self):
        template = "{a + b}"
        context = {"a": 4, "b": 3}
        result = render_template(template, context)
        logger.info("Test: Expression evaluation => %s", result)
        self.assertEqual(result, 7)
    
    def test_dot_notation_in_fstring(self):
        template = "f'Test layer: {test.inner}'"
        context = {"test.inner": 3, "test": 1}
        result = render_template(template, context)
        logger.info("Test: Dot notation in f-string => %s", result)
        self.assertEqual(result, "Test layer: 3")
    
    def test_dot_notation_expression(self):
        template = "{test.inner}"
        context = {"test.inner": 3, "test": 1}
        result = render_template(template, context)
        logger.info("Test: Dot notation in expression => %s", result)
        self.assertEqual(result, 3)
    
    def test_comprehension_expression(self):
        template = "{''.join(f\"<context_item>{r['text']}</context_item>\" for r in retriever.results)}"
        context = {
            "start.current_user_input": "Hello?",
            "retriever.results": [
                {"text": "The answer is 42."},
                {"text": "The answer is 43."},
                {"text": "The answer is 44."},
            ],
        }
        result = render_template(template, context)
        logger.info("Test: Comprehension expression => %s", result)
        self.assertEqual(
            result,
            "<context_item>The answer is 42.</context_item>"
            "<context_item>The answer is 43.</context_item>"
            "<context_item>The answer is 44.</context_item>",
        )
    
    def test_multiline_fstring_comprehension(self):
        template = (
            "f'''Answer the question provided inside the <question></question> section. "
            "Base your answers in the citations from medical guidelines given in the <context></context> section.\n\n"
            "<question>{start.current_user_input}</question>\n\n"
            "<context>{ \"\".join(f\"<context_item>{r['text']}</context_item>\" for r in retriever.results) }"
            "</context>'''"
        )
        context = {
            "start.current_user_input": "Hello?",
            "retriever.results": [
                {"text": "The answer is 42."},
                {"text": "The answer is 43."},
                {"text": "The answer is 44."},
            ],
        }
        result = render_template(template, context)
        logger.info("Test: Multiline f-string with comprehension =>\n%s", result)
        self.assertIn("<question>Hello?</question>", result)
        self.assertIn("<context_item>The answer is 42.</context_item>", result)
    
    def test_complex_list_creation(self):
        template = (
            "{[{'source_id': r['retrieved_chunk'].get('guideline_id', None), "
            "'retrieval': r['retrieved_chunk'].get('text', None), "
            "'reference_id': r['retrieved_chunk'].get('reference_id', None)} for r in retriever.results]}"
        )
        context = {
            "retriever.results": [
                {
                    "retrieved_chunk": {"guideline_id": 0, "text": "The answer is 42.", "reference_id": None},
                    "score": 0.0,
                },
                {
                    "retrieved_chunk": {"guideline_id": 1, "text": "The answer is 52.", "reference_id": "14"},
                    "score": 1.0,
                },
            ],
        }
        result = render_template(template, context)
        logger.info("Test: Complex list creation => %s", result)
        expected = [
            {'source_id': 0, 'retrieval': "The answer is 42.", 'reference_id': None},
            {'source_id': 1, 'retrieval': "The answer is 52.", 'reference_id': "14"},
        ]
        self.assertEqual(result, expected)
    
    def test_list(self):
        template = (
            "f'''You are evaluating multiple answers to a clinical question. "
            "Each answer was generated independently and may use different reasoning strategies. "
            "Review all answers carefully and explain which one is most complete, precise, and well-supported.\n\n"
            "<question>{start.current_user_input}</question>\n\n"
            "<answers>{' '.join([f'<answer_{i}>{item[\"response\"]}</answer_{i}>' for i, item in enumerate(list_item.out)])}</answers>'''"
        )
        context = {
            "start.current_user_input": "Hello?",
            "list_item.out": [
                {"response": "The answer is 42."},
                {"response": "The answer is 43."},
            ],
        }
        result = render_template(template, context)
        logger.info("Test: List =>\n%s", result)
        self.assertIn("<question>Hello?</question>", result)
        self.assertIn("<answer_0>The answer is 42.</answer_0>", result)
        self.assertIn("<answer_1>The answer is 43.</answer_1>", result)
    
    def test_extract_single_answer_tag(self):
        template = (
            "{import re\nmatch = re.search(r'<answer>\s*([\s\S]+)\s*</answer>', generator.response)\n"
            "if match:\n    return match.group(1)}"
        )
        context = {
            "generator.response": "<answer>The answer is 42.</answer>",
        }
        result = render_template(template, context)
        logger.info("Test: Extract single answer tag => %s", result)
        self.assertIn("The answer is 42.", result)
    
    def test_extract_nested_answer_unclosed_outer(self):
        template = (
            "{import re\nmatch = re.search(r'<answer>\s*([\s\S]+)\s*</answer>', generator.response)\n"
            "if match:\n    return match.group(1)}"
        )
        context = {
            "generator.response": "<answer><answer>The answer is 42.</answer>",
        }
        result = render_template(template, context)
        logger.info("Test: Extract nested answer with unclosed outer => %s", result)
        self.assertIn("<answer>The answer is 42.", result)
    
    def test_extract_nested_answer_multiline_unclosed(self):
        template = (
            "{import re\nmatch = re.search(r'<answer>\s*([\s\S]+)\s*</answer>', generator.response)\n"
            "if match:\n    return match.group(1)}"
        )
        context = {
            "generator.response": "<answer>\n<answer>The answer is 42.\n</answer>",
        }
        result = render_template(template, context)
        logger.info("Test: Extract multiline nested answer with unclosed outer => %s", result)
        self.assertIn("<answer>The answer is 42.", result)
    
    def test_extract_nested_answer_fully_closed(self):
        template = (
            "{import re\nmatch = re.search(r'<answer>\s*([\s\S]+)\s*</answer>', generator.response)\n"
            "if match:\n    return match.group(1)}"
        )
        context = {
            "generator.response": "<answer>\n<answer>The answer is 42.\n</answer></answer>",
        }
        result = render_template(template, context)
        logger.info("Test: Extract fully closed nested answer => %s", result)
        self.assertIn("<answer>The answer is 42.\n</answer>", result)
    
    def test_extract_from_list_of_responses(self):
        template = (
            "{import re\nmatch = re.search(r'<answer>\s*([\s\S]+)\s*</answer>', generator.response[0])\n"
            "if match:\n    return match.group(1)}"
        )
        context = {
            "generator.response": [
                "<answer>\n<answer>The answer is 42.\n</answer></answer>",
                "<answer>\n<answer>The answer is 42.\n</answer></answer>",
            ],
        }
        result = render_template(template, context)
        logger.info("Test: Extract from list of response strings => %s", result)
        self.assertIn("<answer>The answer is 42.\n</answer>", result)
    
    def test_context_items_from_retriever_results(self):
        template = (
            "{texts = [r['retrieved_chunk']['text'] for r in retriever.results]\n"
            "context_items = '\\n'.join([f'<context_item id={i}>{t}</context_item>' for i, t in enumerate(texts)])\n"
            "return f'<question>{start.current_user_input}</question><context>{context_items}</context>'}"
        )
        context = {
            "start.current_user_input": "Hello?",
            "retriever.results": [
                {"retrieved_chunk": {"text": "The answer is 42."}},
                {"retrieved_chunk": {"text": "The answer is 43."}},
            ],
        }
        result = render_template(template, context)
        logger.info("Test: Context items from retriever results => %s", result)
        self.assertIn("<context_item id=0>The answer is 42.</context_item>", result)
        self.assertIn("<context_item id=1>The answer is 43.</context_item>", result)
    
    def test_merged_context_items_from_nested_chunks(self):
        template = (
            "{def merge_text(chunk_list):\n    text = ''\n    for chunk in chunk_list:\n        text = text + chunk['retrieved_chunk']['text']"
            "\n    return text\ntexts = [\n   merge_text(chunk_w_context) for chunk_w_context in list_context_retrievals.component_outputs\n]"
            "\ncontext_items = '\\n'.join([\n    f'<context_item id={i}>{t}</context_item>' for i, t in enumerate(texts)\n])"
            "\nreturn f'<question>{start.current_user_input}</question>\\n<context>{context_items}</context>'}"
        )
        context = {
            "start.current_user_input": "Hello?",
            "list_context_retrievals.component_outputs": [
                [{"retrieved_chunk": {"text": "The answer is 42."}}, {"retrieved_chunk": {"text": "The answer is 43."}}],
                [{"retrieved_chunk": {"text": "B The answer is 42."}}, {"retrieved_chunk": {"text": "B The answer is 43."}}],
            ],
        }
        result = render_template(template, context)
        logger.info("Test: Merged context items from nested chunk lists => %s", result)
        self.assertIn("<context_item id=0>The answer is 42.The answer is 43.</context_item>", result)
        self.assertIn("<context_item id=1>B The answer is 42.B The answer is 43.</context_item>", result)
    
    def test_question_and_context_from_subquery_retriever(self):
        template = (
            "{question = output_parser.code_output[0]\n"
            "retrieval_texts = [\n    r['retrieved_chunk']['text'] for r in subquery_retriever_list.component_outputs[0]['results']\n]\n"
            "context_items = '\\n'.join([\n    f'<context_item id={i}>{t}</context_item>' for i, t in enumerate(retrieval_texts)\n])\n"
            "return f'<question>{question}</question><context>{context_items}</context>'}"
        )
        context = {
            "output_parser.code_output": ["Q1", "Q2"],
            "subquery_retriever_list.component_outputs": [
                {"results": [{"retrieved_chunk": {"text": "R1a."}}, {"retrieved_chunk": {"text": "R1b."}}]},
                {"results": [{"retrieved_chunk": {"text": "R2a."}}, {"retrieved_chunk": {"text": "R2b."}}]},
            ],
        }
        result = render_template(template, context)
        logger.info("Test: Question and context from subquery retriever => %s", result)
        self.assertIn("<question>Q1</question>", result)
        self.assertIn("<context_item id=0>R1a.</context_item>", result)
    
    def test_question_retrieval_answer_from_subquery_retriever(self):
        template = (
            "{questions = output_parser.code_output\n"
            "retrievals = [\n    [ r['retrieved_chunk']['text'] for r in rs['results'] ] \n    for rs in subquery_retriever_list.component_outputs\n]\n"
            "answers = [ a['response'] for a in subquery_generator_list.component_outputs ]\n\n"
            "return [\n    {'question': questions[i], 'retrieval': retrievals[i], 'answer': answers[i]}\n    for i in range(len(questions))\n]}"
        )
        context = {
            "output_parser.code_output": ["Q1", "Q2"],
            "subquery_retriever_list.component_outputs": [
                {"results": [{"retrieved_chunk": {"text": "R1a."}}, {"retrieved_chunk": {"text": "R1b."}}]},
                {"results": [{"retrieved_chunk": {"text": "R2a."}}, {"retrieved_chunk": {"text": "R2b."}}]},
            ],
            "subquery_generator_list.component_outputs": [
                {"response": "A1"},
                {"response": "A2"},
            ],
        }
        result = render_template(template, context)
        logger.info("Test: Question and context from subquery retriever => %s", result)
        self.assertIn({"question": "Q1", "retrieval": ["R1a.", "R1b."], "answer": "A1"}, result)
        self.assertIn({"question": "Q2", "retrieval": ["R2a.", "R2b."], "answer": "A2"}, result)


if __name__ == '__main__':
    unittest.main()
