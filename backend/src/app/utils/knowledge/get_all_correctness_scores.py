import csv
import json
from pathlib import Path

from pymongo import MongoClient

from app.constants.mongodb_constants import (
    CHATS_COLLECTION, QUESTION_DS_COLLECTION, GENERATED_RESULTS_COLLECTION, EVAL_MONGODB_DATABASE, MONGODB_DATABASE,
    GUIDELINE_REFERENCE_COLLECTION, GUIDELINE_COLLECTION,
)

# MongoDB collections
mongo_client = MongoClient("mongodb://mongo:mongo@127.0.0.1:27017/")
system_interaction_database = mongo_client[MONGODB_DATABASE]
eval_database = mongo_client[EVAL_MONGODB_DATABASE]
generated_results = eval_database[GENERATED_RESULTS_COLLECTION]
questions = eval_database[QUESTION_DS_COLLECTION]
chats = system_interaction_database[CHATS_COLLECTION]
references = system_interaction_database[GUIDELINE_REFERENCE_COLLECTION]
guidelines = system_interaction_database[GUIDELINE_COLLECTION]

# Result list
final_output = []

filter_generation_run = "FINAL.D"  # |006.i|006.j|003."

# Query documents with correctness_evaluations present and non-empty
cursor = generated_results.find(
    {
        "correctness_evaluations": {"$exists": True, "$ne": []},
        "generation_run.name": {"$regex": filter_generation_run},
    },
)

docs = [doc for doc in cursor]

print(f"Found {len(docs)} documents with correctness_evaluations present and non-empty. Filter: {filter_generation_run}")


def get_retrieval_content(reference):
    ref_type = reference.get("type")
    if ref_type == "text":
        return reference.get("contained_text", "")
    elif ref_type == "image":
        return f"{reference.get('caption', '')}\n{reference.get('describing_text', '')}"
    elif ref_type == "table":
        return f"{reference.get('caption', '')}\n{reference.get('table_markdown', '')}"
    elif ref_type == "recommendation":
        return f"{reference.get('recommendation_title', '')}\n{reference.get('recommendation_content', '')}\n{reference.get('recommendation_grade', '')}"
    elif ref_type == "statement":
        return f"{reference.get('statement_title', '')}\n{reference.get('statement_content', '')}\n{reference.get('statement_consensus_grade', '')}"
    elif ref_type == "metadata":
        return reference.get("metadata_content", "")
    else:
        return ""


def format_retrieval(retrieval_id):
    reference_doc = references.find_one({"_id": retrieval_id})
    if not reference_doc:
        return None
    
    # Find corresponding guideline
    guideline_id = reference_doc.get("guideline_id")
    guideline_doc = guidelines.find_one({"_id": guideline_id})
    if not guideline_doc:
        return None
    
    guideline_label = f"{guideline_doc.get('awmf_register_number')} - {guideline_doc.get('title')}"
    retrieval_content = get_retrieval_content(reference_doc)
    
    return {
        "guideline": guideline_label,
        "retrieval": retrieval_content,
    }


for doc in docs:
    calculated_correctness_score = doc["automatic_evaluation"]["accuracy_evaluation"]["gpt_likert_similarity"]
    correctness = doc["correctness_evaluations"][0]
    
    score = correctness.get("correctness_score")
    fact_conflicts = correctness.get("count_factual_conflicts", 0)
    input_conflicts = correctness.get("count_input_conflicts", 0)
    context_conflicts = correctness.get("count_context_conflicts", 0)
    note = correctness.get("note", "")
    
    reason = f"Fact conflicts: {fact_conflicts}, Input conflicts: {input_conflicts}, Context conflicts: {context_conflicts}; {note}"
    
    retrieval_score = doc["automatic_evaluation"]["retrieval_evaluation"]
    r_recall = retrieval_score.get("recall", 0)
    r_precision = retrieval_score.get("precision", 0)
    
    # Resolve related question
    question_doc = questions.find_one({"_id": doc["related_question"]})
    question_text = question_doc["question"] if question_doc else None
    correct_answer = question_doc["correct_answer"] if question_doc else None
    
    # Resolve related chat and get actual answer from last interaction
    chat_doc = chats.find_one({"_id": doc["related_chat"]})
    actual_answer = None
    if chat_doc and chat_doc.get("interactions"):
        actual_answer = chat_doc["interactions"][-1].get("generator_output")
    
    chat_doc = chats.find_one({"_id": doc["related_chat"]})
    actual_answer = None
    actual_retrieval = []
    if chat_doc and chat_doc.get("interactions"):
        actual_answer = chat_doc["interactions"][-1].get("generator_output")
        raw_actual_retrieval = chat_doc["interactions"][-1].get("retrieval_output", [])
        actual_retrieval = []
        for actual_retrieval_entry in raw_actual_retrieval:
            formatted_ref = format_retrieval(actual_retrieval_entry["reference_id"])
            if formatted_ref:
                actual_retrieval.append(formatted_ref)
            else:
                print(f"Retrieval ID {actual_retrieval_entry['reference_id']} not found in references or guidelines")
    
    expected_retrieval_ids = question_doc.get("expected_retrieval", []) if question_doc else []
    
    retrieval_entries = []
    for retrieval_id in expected_retrieval_ids:
        formatted_retrieval = format_retrieval(retrieval_id)
        if formatted_retrieval:
            retrieval_entries.append(formatted_retrieval)
        else:
            print(f"Retrieval ID {retrieval_id} not found in references or guidelines")
    
    final_output.append(
        {
            "gen_res_id": doc["_id"],
            "gen_run_name": doc["generation_run"]["name"],
            "question": question_text,
            "expected_answer": correct_answer,
            "expected_retrievals": retrieval_entries,
            "actual_response": actual_answer,
            "actual_retrievals": actual_retrieval,
            "correctness_score": score,
            "reason": reason,
            "calculated_correctness_score": calculated_correctness_score,
            "difference_in_scores": (calculated_correctness_score - score),
            "retrieval_recall": r_recall,
            "retrieval_precision": r_precision,
        },
    )


def filter_for_question_run():
    # Count questions per gen_run_name
    question_run_counts = {}
    for item in final_output:
        if item["question"] not in question_run_counts:
            question_run_counts[item["question"]] = set()
        question_run_counts[item["question"]].add(item["gen_run_name"])
    
    # Filter questions that appear in exactly 2 runs
    questions_to_keep = {q for q, runs in question_run_counts.items() if len(runs) == 2}
    return [item for item in final_output if item["question"] in questions_to_keep]


# final_output = filter_for_question_run()

# Sort and print results
final_output.sort(key=lambda x: x["question"], reverse=True)

print(json.dumps(final_output, indent=4, ensure_ascii=False, default=str, sort_keys=False, separators=(',', ': ')))

FIELDNAMES = [
    "gen_res_id",
    "gen_run_name",
    "question",
    "expected_answer",
    "expected_retrievals",
    "actual_response",
    "actual_retrievals",
    "correctness_score",
    "reason",
    "calculated_correctness_score",
    "difference_in_scores",
    "retrieval_recall",
    "retrieval_precision",
]


def _encode(v):
    # CSV wants scalars; JSON-encode lists/dicts
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return v


name = filter_generation_run.replace(" ", "").replace("-", "").replace("^", "")
csv_path = Path(f"final_output_{name}.csv")
with csv_path.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
    writer.writeheader()
    for row in final_output:
        writer.writerow({k: _encode(row.get(k)) for k in FIELDNAMES})
