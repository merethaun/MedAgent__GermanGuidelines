from functools import wraps


class WebsiteNotAsExpectedError(Exception):
    """Raised when the expected content could not be extracted from the provided website."""
    
    def __init__(self, url: str, concrete_problem: str):
        self.url = url
        self.concrete_problem = concrete_problem
        self.message = f"Could not extract desired information from AWMF website {url} -> concretely: {concrete_problem}"
        super().__init__(self.message)


def handle_website_not_as_excepted_error(error_message=None, logger=None):
    """
    A decorator for handling exceptions and raising WebsiteNotAsExpectedError. !!! always have the second argument as url !!!

    Args:
        error_message: Optional custom error message. If None, uses the exception message.
        logger: Logger instance to use for error logging. If None, errors won't be logged.

    Returns:
        Decorated function that catches exceptions and raises WebsiteNotAsExpectedError
    """
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except WebsiteNotAsExpectedError:
                # Re-raise if it's already the correct exception type
                raise
            except Exception as e:
                # Extract URL from arguments if available
                url = args[1]
                msg = error_message or f"Error in {func.__name__}: {str(e)}"
                if logger:
                    logger.error(msg)
                raise WebsiteNotAsExpectedError(url=url, concrete_problem=msg) from e
        
        return wrapper
    
    return decorator
