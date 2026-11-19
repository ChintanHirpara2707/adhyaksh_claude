"""Clear, plain-language messages for every error code: what went wrong and what to do next.

Result.failure uses these when a caller gives no message of its own, so no failure reaches the user blank."""
from __future__ import annotations

MESSAGES: dict[str, str] = {
    "E_PATH_DENIED": "That location is outside the folders ADHYAKSH may use. Add it under Settings, Folders, or pick a file inside an allowed folder.",
    "E_NEEDS_CONFIRM": "This action needs your confirmation before it runs.",
    "E_NO_API_KEY": "No language model is set up. Add a key in Settings (or start Ollama) and allow cloud use if you want a cloud model.",
    "E_TIMEOUT": "The service took too long to answer. Check the internet connection and try again.",
    "E_FILE_NOT_FOUND": "That file was not found. Check the name, or ask me to list the folder.",
    "E_LOW_CONFIDENCE": "I am not sure what you meant. Please say it another way.",
    "E_UNSUPPORTED_OS": "That action is not available on this operating system.",
    "E_BLOCKED": "That action is not allowed by the safety rules.",
    "E_ACTION_FAILED": "The action could not be completed. Details are in the log on the Health page.",
    "E_CONFIRM_INVALID": "The confirmation is invalid or has expired. Please ask again.",
    "E_LLM_FAILED": "The language model did not answer. Try again, or check the provider on the Health page.",
    "E_NETWORK": "Could not reach the internet service. Check the connection and try again.",
    "E_BAD_SETTING": "That setting value is not valid.",
    "E_BAD_ARGUMENTS": "The action was missing a value it needs, or a value had the wrong form.",
    "E_UNVERIFIED": "The action reported success, but its effect could not be found afterwards.",
}


def message_for(code: str) -> str:
    return MESSAGES.get(code, "Something went wrong. Details are in the log on the Health page.")
