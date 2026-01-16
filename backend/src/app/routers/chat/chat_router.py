from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query

from app.models.chat.chat import Chat
from app.services.chat import ChatService
from app.services.system import WorkflowSystemStorageService
from app.utils.logger import setup_logger
from app.utils.service_creators import get_chat_service, get_workflow_storage

logger = setup_logger(__name__)
chat_router = APIRouter()


@chat_router.post("/", response_model=Chat, status_code=status.HTTP_201_CREATED)
def create_chat(
        initial_chat: Chat,
        chat_service: ChatService = Depends(get_chat_service),
        wf_storage_service: WorkflowSystemStorageService = Depends(get_workflow_storage),
):
    try:
        wf_storage_service.get_workflow_entry_by_id(initial_chat.workflow_system_id)
    except ValueError as e:
        logger.error(f"Failed to get workflow: {str(e)} for provided chat", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found (please insert valid workflow ID)",
        )
    except Exception as e:
        logger.error(f"Error while fetching workflow: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    try:
        return chat_service.create_chat_entry(initial_chat)
    except ValueError as e:
        logger.warning(str(e))
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create chat: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@chat_router.get("/", response_model=List[Chat])
def list_chats(
        workflow_id: Optional[str] = Query(default=None, description="Filter chats by workflow system ID"),
        user_name: Optional[str] = Query(default=None, description="Filter chats by user name"),
        chat_service: ChatService = Depends(get_chat_service),
        wf_storage_service: WorkflowSystemStorageService = Depends(get_workflow_storage),
):
    if workflow_id is not None:
        try:
            wf_storage_service.get_workflow_entry_by_id(workflow_id)
        except ValueError as e:
            logger.error(f"Failed to get workflow: {str(e)} for provided chat", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found (please insert valid workflow ID)",
            )
        except Exception as e:
            logger.error(f"Error while fetching workflow: {str(e)}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    try:
        return chat_service.list_all_chats(workflow_id=workflow_id, user_name=user_name)
    except Exception as e:
        logger.error(f"Failed to get chats: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@chat_router.get("/{chat_id}", response_model=Chat)
def get_chat_by_id(
        chat_id: str,
        chat_service: ChatService = Depends(get_chat_service),
):
    try:
        entry = chat_service.get_chat_entry_by_id(chat_id)
    except ValueError as e:
        logger.warning(f"Chat not found: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    except Exception as e:
        logger.error(f"Failed to get chat: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    return entry


@chat_router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat(
        chat_id: str,
        chat_service: ChatService = Depends(get_chat_service),
):
    result = chat_service.delete_chat_entry(chat_id)
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    return


@chat_router.put("/{chat_id}", response_model=Chat)
def update_chat(
        chat_id: str,
        updated_chat: Chat,
        chat_service: ChatService = Depends(get_chat_service),
        wf_storage_service: WorkflowSystemStorageService = Depends(get_workflow_storage),
):
    try:
        wf_storage_service.get_workflow_entry_by_id(updated_chat.workflow_system_id)
    except ValueError as e:
        logger.error(f"Failed to get workflow: {str(e)} for provided chat")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found (please insert valid workflow ID)",
        )
    except Exception as e:
        logger.error(f"Error while fetching workflow: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    try:
        return chat_service.update_chat_entry(chat_id, updated_chat)
    except ValueError as e:
        logger.warning(str(e))
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update chat: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@chat_router.put("/{chat_id}/pose-input", response_model=Chat)
def pose_question(
        chat_id: str,
        user_input: str,
        chat_service: ChatService = Depends(get_chat_service),
):
    try:
        return chat_service.pose_question(chat_id, user_input)
    except ValueError as e:
        logger.warning(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update chat: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
