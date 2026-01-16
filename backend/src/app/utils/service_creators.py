from app.services.knowledge.graph import Neo4jGraphService

from app.constants.mongodb_constants import (
    CHATS_COLLECTION, WORKFLOW_SYSTEMS_COLLECTION, GUIDELINE_REFERENCE_COLLECTION, EVALUATORS_COLLECTION, QUESTION_DS_GROUP_COLLECTION,
    GUIDELINE_REFERENCE_GROUPS_COLLECTION, QUESTION_DS_COLLECTION, GUIDELINE_COLLECTION, VECTOR_DATABASES_COLLECTION, GENERATED_RESULTS_COLLECTION,
)
from app.services.chat import ChatService
from app.services.guideline_evaluation.evaluation_results import ResultGenerationService, AutomaticEvaluationService, ManualEvaluationService
from app.services.guideline_evaluation.question_dataset import QuestionDatasetService, QuestionDatasetParserService
from app.services.knowledge.guidelines import AWMFDocumentsService, GuidelineService, AWMFWebsiteInteractionService, GuidelineValidationService
from app.services.knowledge.guidelines.keywords.keyword_service import KeywordService
from app.services.knowledge.guidelines.references import GuidelineReferenceService
from app.services.knowledge.guidelines.references.reference_finder_service import ReferenceFinderService
from app.services.knowledge.vector import (
    VectorizerService, WeaviateVectorDBService, AdvancedDBService, SimilarityScoreService, HierarchicalIndexVectorDBService,
)
from app.services.system import WorkflowSystemInteractionService, WorkflowSystemStorageService
from app.utils.knowledge.mongodb import get_system_mongodb_database, get_eval_mongodb_database, get_neo4j_db_collection

# -- SINGLETON-LIKE SERVICES INITIALIZED ONCE --

# MongoDB collections
_system_db = get_system_mongodb_database()
_eval_db = get_eval_mongodb_database()
_neo4j_collection = get_neo4j_db_collection()

# Shared services
workflow_storage_service = WorkflowSystemStorageService(
    _system_db[WORKFLOW_SYSTEMS_COLLECTION],
)
wf_system_interaction_service = WorkflowSystemInteractionService(
    wf_def_service=workflow_storage_service,
)
chat_service = ChatService(
    _system_db[CHATS_COLLECTION], wf_system_interaction_service,
)

guideline_reference_service = GuidelineReferenceService(
    _system_db[GUIDELINE_REFERENCE_GROUPS_COLLECTION], _system_db[GUIDELINE_REFERENCE_COLLECTION],
)
question_dataset_service = QuestionDatasetService(
    _eval_db[QUESTION_DS_COLLECTION], _eval_db[QUESTION_DS_GROUP_COLLECTION], guideline_reference_service,
)
reference_finder_service = ReferenceFinderService()
guideline_service = GuidelineService(
    _system_db[GUIDELINE_COLLECTION],
)
awmf_documents_service = AWMFDocumentsService()
awmf_website_interaction_service = AWMFWebsiteInteractionService()
vectorizer_service = VectorizerService()
vector_db_service = WeaviateVectorDBService(
    _system_db[VECTOR_DATABASES_COLLECTION], vectorizer_service,
)
hier_vector_service = HierarchicalIndexVectorDBService(
    vector_db_service, _system_db[VECTOR_DATABASES_COLLECTION],
)
similarity_service = SimilarityScoreService(
    _system_db[VECTOR_DATABASES_COLLECTION], vectorizer_service,
)
advanced_db_service = AdvancedDBService(
    _system_db[VECTOR_DATABASES_COLLECTION], vectorizer_service, similarity_service,
)
result_generation_service = ResultGenerationService(
    _eval_db[EVALUATORS_COLLECTION], _eval_db[GENERATED_RESULTS_COLLECTION], question_dataset_service, chat_service,
)
automatic_evaluation_service = AutomaticEvaluationService(
    question_dataset_service, result_generation_service, chat_service, guideline_reference_service, guideline_service,
)
manual_evaluation_service = ManualEvaluationService(
    result_generation_service,
)
question_dataset_parser_service = QuestionDatasetParserService(
    question_dataset_service, guideline_reference_service, reference_finder_service, guideline_service,
)
guideline_validation_service = GuidelineValidationService(
    awmf_documents_service,
)
keyword_service = KeywordService()
neo4j_service = Neo4jGraphService(
    _neo4j_collection, keyword_service, vectorizer_service,
)


# -- EXPORT GETTERS FOR DEPENDENCY INJECTION --

# noinspection DuplicatedCode
def get_chat_service() -> ChatService:
    return chat_service


# noinspection DuplicatedCode
def get_workflow_interaction_service() -> WorkflowSystemInteractionService:
    return wf_system_interaction_service


# noinspection DuplicatedCode
def get_workflow_storage() -> WorkflowSystemStorageService:
    return workflow_storage_service


# noinspection DuplicatedCode
def get_question_dataset_service() -> QuestionDatasetService:
    return question_dataset_service


# noinspection DuplicatedCode
def get_guideline_reference_service() -> GuidelineReferenceService:
    return guideline_reference_service


def get_keyword_service() -> KeywordService:
    return keyword_service


# noinspection DuplicatedCode
def get_result_generation_service() -> ResultGenerationService:
    return result_generation_service


# noinspection DuplicatedCode
def get_automatic_evaluation_service() -> AutomaticEvaluationService:
    return automatic_evaluation_service


# noinspection DuplicatedCode
def get_manual_evaluation_service() -> ManualEvaluationService:
    return manual_evaluation_service


# noinspection DuplicatedCode
def get_guideline_service() -> GuidelineService:
    return guideline_service


# noinspection DuplicatedCode
def get_awmf_documents_service() -> AWMFDocumentsService:
    return awmf_documents_service


# noinspection DuplicatedCode
def get_awmf_website_interaction_service() -> AWMFWebsiteInteractionService:
    return awmf_website_interaction_service


# noinspection DuplicatedCode
def get_vector_db_service() -> WeaviateVectorDBService:
    return vector_db_service


# noinspection DuplicatedCode
def get_hierarchical_vector_service() -> HierarchicalIndexVectorDBService:
    return hier_vector_service


# noinspection DuplicatedCode
def get_graph_db_service() -> Neo4jGraphService:
    return neo4j_service


# noinspection DuplicatedCode
def get_advanced_db_service() -> AdvancedDBService:
    return advanced_db_service


# noinspection DuplicatedCode
def get_similarity_service() -> SimilarityScoreService:
    return similarity_service


# noinspection DuplicatedCode
def get_reference_finder_service() -> ReferenceFinderService:
    return reference_finder_service


# noinspection DuplicatedCode
def get_guideline_validation_service() -> GuidelineValidationService:
    return guideline_validation_service


# noinspection DuplicatedCode
def get_question_dataset_parser_service() -> QuestionDatasetParserService:
    return question_dataset_parser_service
