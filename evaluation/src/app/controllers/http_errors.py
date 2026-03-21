from fastapi import HTTPException, status


def as_http_error(exc: ValueError) -> HTTPException:
    message = str(exc)
    lowered = message.lower()

    if "not found" in lowered:
        status_code = status.HTTP_404_NOT_FOUND
    elif any(fragment in lowered for fragment in ["already completed", "claimed by another", "not available to claim"]):
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_400_BAD_REQUEST

    return HTTPException(status_code=status_code, detail=message)
