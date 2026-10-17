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


class _UserPrompts:
    """prompts_user.py first; any name it does not define (for example one added by a
    later update) comes from prompts.py, so an old personal copy keeps working."""

    def __init__(self, user, standard):
        self._user = user
        self._standard = standard

    def __getattr__(self, name):
        try:
            return getattr(self._user, name)
        except AttributeError:
            return getattr(self._standard, name)


def _load():
    global PROMPTS_WARNING
    standard = importlib.import_module("prompts")
    try:
        return _UserPrompts(importlib.import_module("prompts_user"), standard)
    except ModuleNotFoundError as e:
        if e.name != "prompts_user":
            PROMPTS_WARNING = f"prompts_user.py could not be loaded ({e}): using the standard prompts."
    except Exception as e:
        PROMPTS_WARNING = (f"prompts_user.py has an error ({type(e).__name__}: {e}): "
                           "using the standard prompts.")
    return standard


prompts = _load()
