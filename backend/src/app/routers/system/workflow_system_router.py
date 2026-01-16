from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY

from app.models.system.workflow_system import WorkflowConfig
from app.services.chat import ChatService
from app.services.system import WorkflowSystemStorageService
from app.utils.logger import setup_logger
from app.utils.service_creators import get_workflow_storage, get_chat_service

logger = setup_logger(__name__)
workflow_system_router = APIRouter()


@workflow_system_router.post("/", response_model=WorkflowConfig, status_code=status.HTTP_201_CREATED)
def create_workflow_system(
        config: WorkflowConfig,
        storage: WorkflowSystemStorageService = Depends(get_workflow_storage),
):
    try:
        return storage.create_workflow_entry(config)
    except ValueError as e:
        logger.warning(str(e))
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create workflow: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@workflow_system_router.get("/", response_model=List[WorkflowConfig])
def list_workflows(
        storage: WorkflowSystemStorageService = Depends(get_workflow_storage),
):
    return storage.list_all_workflows()


@workflow_system_router.get("/name/{name}", response_model=WorkflowConfig)
def get_workflow_by_name(
        name: str,
        storage: WorkflowSystemStorageService = Depends(get_workflow_storage),
):
    try:
        entry = storage.get_workflow_entry_by_name(name)
    except ValueError as e:
        logger.warning(str(e))
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    if entry is None:
        logger.warning(f"Workflow with name '{name}' not found")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return entry


@workflow_system_router.get("/{wf_id}", response_model=WorkflowConfig)
def get_workflow_by_id(
        wf_id: str,
        storage: WorkflowSystemStorageService = Depends(get_workflow_storage),
):
    entry = storage.get_workflow_entry_by_id(wf_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return entry


@workflow_system_router.delete("/{wf_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow(
        wf_id: str,
        delete_with_chats: bool = Query(
            default=False,
            description="Delete all chats associated with this workflow system (if False, fail if associated chats exist)",
        ),
        storage: WorkflowSystemStorageService = Depends(get_workflow_storage),
        chat_service: ChatService = Depends(get_chat_service),
):
    try:
        to_be_deleted_chats = chat_service.list_all_chats(workflow_id=wf_id, user_name=None)
    except ValueError as e:
        logger.warning(f"Could not find chat: {e}", exc_info=True)
        raise HTTPException(status_code=HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Could not delete chats: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    if delete_with_chats:
        try:
            for chat in to_be_deleted_chats:
                chat_service.delete_chat_entry(chat.id)
        except ValueError as e:
            logger.warning(f"Could not find chat: {e}", exc_info=True)
            raise HTTPException(status_code=HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
        except Exception as e:
            logger.error(f"Could not delete chats: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    elif len(to_be_deleted_chats) > 0:
        logger.warning(f"Chats exist for this workflow system: {len(to_be_deleted_chats)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Chats exist for this workflow system")
    
    result = storage.delete_workflow_entry(wf_id)
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return


@workflow_system_router.put("/{wf_id}", response_model=WorkflowConfig)
def update_workflow(
        wf_id: str,
        config: WorkflowConfig,
        storage: WorkflowSystemStorageService = Depends(get_workflow_storage),
):
    try:
        return storage.update_workflow_entry(wf_id, config)
    except ValueError as e:
        logger.warning(str(e))
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update workflow: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
