from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.constants.auth_config import ROLE_ADMIN, ROLE_USER
from app.controllers.dependencies.auth_dependencies import require_roles
from app.exceptions.system.chat import ChatNotFoundError
from app.models.system.system_chat_interaction import Chat, RenameChatRequest
from app.models.system.workflow_system import WorkflowConfig
from app.services.service_registry import get_chat_service, get_workflow_storage_service
from app.services.system import WorkflowSystemStorageService
from app.services.system.chat import ChatService
from app.utils.logging import setup_logger

logger = setup_logger(__name__)

system_router = APIRouter()


#################################
# ----- Workflow system CRUD ----
#################################

@system_router.post(
    "/workflows",
    response_model=WorkflowConfig,
    status_code=status.HTTP_201_CREATED,
    summary="Create a workflow system (admin only)",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def create_workflow_system(
        config: WorkflowConfig,
        storage: WorkflowSystemStorageService = Depends(get_workflow_storage_service),
) -> WorkflowConfig:
    try:
        return storage.create_workflow(config)
    except ValueError as e:
        logger.warning(str(e))
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error("Failed to create workflow: %s", str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@system_router.get(
    "/workflows",
    response_model=List[WorkflowConfig],
    summary="List workflow systems (admin + study_user)",
    dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_USER))],
)
def list_workflows(
        storage: WorkflowSystemStorageService = Depends(get_workflow_storage_service),
) -> List[WorkflowConfig]:
    try:
        return storage.list_workflows()
    except Exception as e:
        logger.error("Failed to list workflows: %s", str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@system_router.get(
    "/workflows/name/{name}",
    response_model=WorkflowConfig,
    summary="Get workflow system by name (admin + study_user)",
    dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_USER))],
)
def get_workflow_by_name(
        name: str,
        storage: WorkflowSystemStorageService = Depends(get_workflow_storage_service),
) -> WorkflowConfig:
    try:
        entry = storage.get_workflow_by_name(name)
    except ValueError as e:
        logger.warning(str(e))
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return entry


@system_router.get(
    "/workflows/{wf_id}",
    response_model=WorkflowConfig,
    summary="Get workflow system by id (admin + study_user)",
    dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_USER))],
)
def get_workflow_by_id(
        wf_id: str,
        storage: WorkflowSystemStorageService = Depends(get_workflow_storage_service),
) -> WorkflowConfig:
    try:
        entry = storage.get_workflow_by_id(wf_id)
    except ValueError as e:
        logger.warning(str(e))
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return entry


@system_router.put(
    "/workflows/{wf_id}",
    response_model=WorkflowConfig,
    summary="Update workflow system (admin only)",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def update_workflow(
        wf_id: str,
        config: WorkflowConfig,
        storage: WorkflowSystemStorageService = Depends(get_workflow_storage_service),
) -> WorkflowConfig:
    try:
        return storage.update_workflow(wf_id, config)
    except ValueError as e:
        logger.warning(str(e))
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error("Failed to update workflow: %s", str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@system_router.delete(
    "/workflows/{wf_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete workflow system (admin only)",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def delete_workflow(
        wf_id: str,
        delete_with_chats: bool = Query(
            default=False,
            description="If True, delete all chats associated with the workflow; otherwise fail if chats exist.",
        ),
        storage: WorkflowSystemStorageService = Depends(get_workflow_storage_service),
        chat_service: ChatService = Depends(get_chat_service),
) -> None:
    # Find chats linked to wf_id
    try:
        chats = chat_service.list_chats(workflow_id=wf_id, user_name=None)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error("Could not list chats for workflow delete: %s", str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    if chats and not delete_with_chats:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Chats exist for this workflow system")
    
    if delete_with_chats:
        try:
            for c in chats:
                # works with both the old and the updated ChatService
                chat_service.delete_chat_entry(c.id)
        except Exception as e:
            logger.error("Could not delete chats for workflow: %s", str(e), exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    # Delete workflow entry
    try:
        result = storage.delete_workflow(wf_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error("Could not delete workflow: %s", str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    # Support both return styles (DeleteResult or bool/None)
    deleted_count = getattr(result, "deleted_count", None)
    if deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return None


#################################
# -------- Chat endpoints -------
#################################

@system_router.post(
    "/workflows/{wf_id}/chats",
    response_model=Chat,
    status_code=status.HTTP_201_CREATED,
    summary="Create a chat for a workflow (admin + study_user)",
    dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_USER))],
)
def create_chat_for_workflow(
        wf_id: str,
        initial_chat: Chat,
        chat_service: ChatService = Depends(get_chat_service),
        storage: WorkflowSystemStorageService = Depends(get_workflow_storage_service),
) -> Chat:
    # Ensure workflow exists
    try:
        wf = storage.get_workflow_by_id(wf_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    if wf is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    
    # Force the workflow_system_id to match the path
    initial_chat.workflow_system_id = wf_id
    if initial_chat.name is None:
        now = datetime.now().astimezone()
        formatted_time = now.strftime("%Y-%m-%d %H:%M")
        initial_chat.name = f"Chat ({formatted_time})"
    
    try:
        return chat_service.create_chat_entry(initial_chat)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error("Failed to create chat: %s", str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@system_router.get(
    "/chats",
    response_model=List[Chat],
    summary="List chats (admin + study_user)",
    dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_USER))],
)
def list_chats(
        workflow_id: Optional[str] = Query(default=None, description="Filter chats by workflow system ID"),
        user_name: Optional[str] = Query(default=None, description="Filter chats by user name"),
        chat_service: ChatService = Depends(get_chat_service),
        storage: WorkflowSystemStorageService = Depends(get_workflow_storage_service),
) -> List[Chat]:
    if workflow_id is not None:
        try:
            wf = storage.get_workflow_by_id(workflow_id)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
        if wf is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    
    try:
        return chat_service.list_chats(workflow_id=workflow_id, user_name=user_name)
    except Exception as e:
        logger.error("Failed to list chats: %s", str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@system_router.get(
    "/chats/{chat_id}",
    response_model=Chat,
    summary="Get chat by id (admin + study_user)",
    dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_USER))],
)
def get_chat_by_id(
        chat_id: str,
        chat_service: ChatService = Depends(get_chat_service),
) -> Chat:
    try:
        return chat_service.get_chat_entry_by_id(chat_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    except Exception as e:
        logger.error("Failed to get chat: %s", str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@system_router.delete(
    "/chats/{chat_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete chat (admin only)",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def delete_chat(
        chat_id: str,
        chat_service: ChatService = Depends(get_chat_service),
) -> None:
    try:
        result = chat_service.delete_chat_entry(chat_id)
        
        # Works with old ChatService (returns DeleteResult) and new one (returns None)
        deleted_count = getattr(result, "deleted_count", None)
        if deleted_count == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
        return None
    
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete chat: %s", str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@system_router.post(
    "/chats/{chat_id}/pose",
    response_model=Chat,
    summary="Pose a user input to the workflow (admin + study_user)",
    description="Appends a chat interaction, runs the workflow system, stores generator + retrieval outputs.",
    dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_USER))],
)
def pose_question(
        chat_id: str,
        user_input: str = Query(..., description="User input / question"),
        chat_service: ChatService = Depends(get_chat_service),
) -> Chat:
    try:
        return chat_service.pose_question(chat_id, user_input)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error("Failed to pose question: %s", str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@system_router.patch(
    "/chats/{chat_id}/name",
    response_model=Chat,
    summary="Rename chat (admin + study_user)",
    dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_USER))],
)
def rename_chat(
        chat_id: str,
        payload: RenameChatRequest,
        chat_service: ChatService = Depends(get_chat_service),
) -> Chat:
    try:
        return chat_service.rename_chat(chat_id, payload.name)
    except ChatNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error("Failed to rename chat: %s", str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
