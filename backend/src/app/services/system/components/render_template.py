from typing import Any, Dict

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def render_template(template, context: Dict[str, Any]) -> Any:
    """
    Renders a string template with support for:
    - Python expression evaluation inside `{}` (e.g., `{a + b}`)
    - f-strings with dictionary or attribute access (e.g., `f"Value: {test.inner}"`)
    - Multiline f-strings using triple quotes
    - Dot-notation in keys for nested access (e.g. "test.inner": 3)
    - Dynamic content generation using comprehensions in expressions

    The context dictionary supports:
    - Dotted keys like 'a.b.c', which are expanded into nested dictionaries
    - Fallback values if non-dotted and dotted versions of the same key exist

    Args:
        template (str): A string containing an expression or f-string format.
                        Can be:
                            - A raw expression in `{}` (e.g., `{a + b}`)
                            - A single-line f-string (e.g., `f"Hello {name}"`)
                            - A multiline f-string using triple quotes (e.g., `f'''...'''`)
        context (Dict[str, Any]): Variables and data available to the template.
                                  Keys can be plain or use dot notation (e.g., 'user.name').

    Returns:
        Any: The evaluated result of the rendered template. This could be a string, a number,
             or any other expression result depending on the input.
    """
    
    class DotDict(dict):
        """
        A dictionary subclass that supports:
        - Attribute-style access (e.g., obj.key)
        - Deep lookup using dot notation in keys (e.g., obj['a.b.c'])

        Used to simplify access to deeply nested keys created from dotted context variables.
        """
        
        def __getattr__(self, item):
            value = self.get(item)
            if isinstance(value, dict):
                return DotDict(value)
            return value
        
        def __getitem__(self, item):
            if '.' in item:
                parts = item.split('.')
                value = self
                for part in parts:
                    value = dict.__getitem__(value, part) if isinstance(value, dict) else getattr(value, part)
                return value
            return dict.__getitem__(self, item)
    
    def expand_dotted_keys(d: Dict[str, Any]) -> Dict[str, Any]:
        """
        Expands keys with dot notation into nested dictionaries.

        Example:
            {'a.b': 1, 'a.c': 2}
            -> {'a': {'b': 1, 'c': 2}}
        """
        result = {}
        for key, value in d.items():
            parts = key.split(".")
            current = result
            for part in parts[:-1]:
                if part not in current or not isinstance(current[part], dict):
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = value
        return result
    
    def merge_dicts(primary: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively merges two dictionaries. Values from `primary` take precedence
        over those in `fallback`.

        Used to merge base context values with expanded dotted keys.
        """
        result = dict(fallback)
        for k, v in primary.items():
            if isinstance(v, dict) and k in result and isinstance(result[k], dict):
                result[k] = merge_dicts(v, result[k])
            else:
                result[k] = v
        return result
    
    def to_dotdict(obj):
        """
        Recursively converts a dictionary into a DotDict object for
        attribute-style and dotted-path access.
        """
        if isinstance(obj, dict):
            return DotDict({k: to_dotdict(v) for k, v in obj.items()})
        return obj
    
    if not isinstance(template, str):
        return template
    
    # Merge and normalize context
    expanded = expand_dotted_keys({k: v for k, v in context.items() if '.' in k})
    base = {k: v for k, v in context.items() if '.' not in k}
    merged_context = to_dotdict(merge_dicts(expanded, base))
    
    # Evaluate based on prefix
    stripped = template.strip()
    # logger.debug(stripped)
    
    resolve_variant = None
    resolved = ""
    
    if stripped.startswith(("f'''", 'f"""')):
        fstring_body = stripped[4:-3]
        result = eval(f"f'''{fstring_body}'''", {}, merged_context)
        resolve_variant = "Resolve F-String Multiline"
        resolved = result
    elif stripped.startswith(("f'", 'f"')):
        fstring_body = stripped[2:-1]
        result = eval(f"f'{fstring_body}'", {}, merged_context)
        resolve_variant = "Resolve F-String Single"
        resolved = result
    elif stripped.startswith("{") and stripped.endswith("}"):
        expression = stripped[1:-1]
        try:
            # Try evaluating as a single expression
            result = eval(expression, {}, merged_context)
            resolve_variant = "Eval (single line expression resolution)"
            resolved = result
        except:
            # Fallback: wrap in a function and exec multiline block with return
            try:
                # logger.debug(f"Failed to evaluate expression '{expression}' as a single expression. -> Will attempt exec")
                lines = expression.splitlines()
                indent = "    "
                arg_names = list(merged_context.keys())  # top-level context keys (e.g., generator)
                
                # Create function definition with args
                code = f"def _template_fn({', '.join(arg_names)}):\n"
                code += "\n".join(f"{indent}{line}" for line in lines)
                
                local_vars = {}
                exec(code, {}, local_vars)
                
                func = local_vars["_template_fn"]
                args = [merged_context[name] for name in arg_names]
                resolve_variant = "Exec (multiline expression resolution)"
                resolved = func(*args)
            except Exception as e:
                logger.error(f"Failed to evaluate expression '{expression}' as a single expression or multiline block: {e}", exc_info=True)
                raise e
    else:
        resolve_variant = "No template detected."
        resolved = template
    
    # logger.debug(f"Resolved template: {resolved} [using: {resolve_variant}]")
    return resolved
