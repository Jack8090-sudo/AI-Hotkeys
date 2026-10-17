"""
AI-Hotkeys — which prompts to use.

prompts.py ships with the app and is replaced on every update.
Your own copy, prompts_user.py (same folder), is never shipped or overwritten:
when it exists it is used instead. If it has an error, prompts.py is used and
the reason is shown after the next reload (work/config_warning.txt).

    from prompt_loader import prompts
"""

import importlib

PROMPTS_WARNING = None


def _load():
    global PROMPTS_WARNING
    try:
        return importlib.import_module("prompts_user")
    except ModuleNotFoundError as e:
        if e.name != "prompts_user":
            PROMPTS_WARNING = f"prompts_user.py could not be loaded ({e}): using the standard prompts."
    except Exception as e:
        PROMPTS_WARNING = (f"prompts_user.py has an error ({type(e).__name__}: {e}): "
                           "using the standard prompts.")
    return importlib.import_module("prompts")


prompts = _load()
