"""All user-facing reply templates. Formal tone, no exclamation marks, no emojis.

Hindi (hi) and Gujarati (gu) variants are UNREVIEWED translations pending author review.
"""
from __future__ import annotations

TEMPLATES: dict[str, dict[str, str]] = {
    "identity_saved": {
        "en": "Welcome, {name}. Your profile has been saved.",
        "hi": "स्वागत है, {name}। आपकी प्रोफ़ाइल सहेज ली गई है।",
        "gu": "સ્વાગત છે, {name}. તમારી પ્રોફાઇલ સાચવવામાં આવી છે.",
    },
    "identity_query": {
        "en": "Your name is {name}.",
        "hi": "आपका नाम {name} है।",
        "gu": "તમારું નામ {name} છે.",
    },
    "memory_saved": {
        "en": "Saved to memory: {fact}.",
        "hi": "स्मृति में सहेजा गया: {fact}।",
        "gu": "મેમરીમાં સાચવ્યું: {fact}.",
    },
    "memory_exists": {
        "en": "This is already stored: {fact}.",
        "hi": "यह पहले से सहेजा हुआ है: {fact}।",
        "gu": "આ પહેલેથી સાચવેલું છે: {fact}.",
    },
    "unknown": {
        "en": "I could not match that request. Please rephrase it.",
        "hi": "मैं इस अनुरोध को समझ नहीं सका। कृपया दोबारा लिखें।",
        "gu": "હું આ વિનંતી સમજી શક્યો નથી. કૃપા કરીને ફરીથી લખો.",
    },
    "file_created": {
        "en": "File created: {path}.",
        "hi": "फ़ाइल बनाई गई: {path}।",
        "gu": "ફાઇલ બનાવવામાં આવી: {path}.",
    },
    "folder_created": {
        "en": "Folder created: {path}.",
        "hi": "फ़ोल्डर बनाया गया: {path}।",
        "gu": "ફોલ્ડર બનાવવામાં આવ્યું: {path}.",
    },
    "screenshot_taken": {"en": "Screenshot saved: {path}."},
    "special_folder_opened": {"en": "Opened {folder}."},
    "web_opened": {"en": "Opened {url} in the default browser."},
    "confirm_delete": {
        "en": "Delete {file}? This moves it to the Recycle Bin. Confirm or cancel.",
        "hi": "{file} हटाएँ? यह फ़ाइल रीसायकल बिन में जाएगी। पुष्टि करें या रद्द करें।",
        "gu": "{file} કાઢી નાખવી છે? આ ફાઇલ રિસાયકલ બિનમાં જશે. પુષ્ટિ કરો અથવા રદ કરો.",
    },
    "error": {
        "en": "The action could not be completed. Reason: {reason}.",
        "hi": "कार्रवाई पूरी नहीं हो सकी। कारण: {reason}।",
        "gu": "ક્રિયા પૂર્ણ થઈ શકી નથી. કારણ: {reason}.",
    },
    "greet": {"en": "Hello. How can I help you?", "hi": "नमस्ते। मैं आपकी कैसे सहायता कर सकता हूँ।",
              "gu": "નમસ્તે. હું તમારી કેવી રીતે મદદ કરી શકું."},
    "ask_name": {"en": "Should I address you as {name}?"},
    "no_name": {"en": "I do not have your name yet. You can say: my name is Priya."},
    "memory_recall": {"en": "{answer}."},
    "memory_none": {"en": "No matching fact is stored."},
    "math": {"en": "{expr} = {value}."},
    "time_now": {
        "en": "The current time is {time}.",
        "hi": "वर्तमान समय {time} है।",
        "gu": "હાલનું સમય {time} છે.",
    },
    "date_today": {
        "en": "Today's date is {date}.",
        "hi": "आज की तारीख {date} है।",
        "gu": "આજની તારીખ {date} છે.",
    },
    "ask_filename": {"en": "Which file name should I use?"},
    "ask_folder": {"en": "Which drive or folder?"},
    "ask_app": {"en": "Which application?"},
    "file_read": {"en": "Contents of {path}:\n\n{content}"},
    "file_updated": {"en": "File updated: {path}."},
    "file_deleted": {"en": "Moved to the Recycle Bin: {path}."},
    "file_found": {"en": "Found {count} file(s):\n{items}"},
    "file_none": {"en": "No files matched {query}."},
    "office_created": {"en": "Created {name} with {rows} rows in {folder}."},
    "doc_created": {"en": "Created {name} in {folder}."},
    "app_opened": {"en": "Opened {app}."},
    "app_closed": {"en": "Closed {app}."},
    "app_refused": {"en": "{app} is not on the allowed applications list."},
    "status": {"en": "CPU {cpu:.0f} percent, memory {ram:.0f} percent, disk {disk:.0f} percent used."},
    "help": {"en": "I can create, read, update, delete and search files; create Excel and Word files; "
                   "open and close allowed applications; remember facts; answer questions from your "
                   "documents; and report system status."},
    "doc_not_found": {"en": "Not found in your documents."},
    "llm_unavailable": {"en": "No language model is configured, so I cannot answer general questions. "
                              "You can search the web: {link}"},
    "llm_blocked": {"en": "Cloud use is not enabled in Settings, so I cannot send this question to a language "
                          "model. You can search the web: {link}"},
    "blocked": {"en": "This action is not permitted. Reason: {reason}."},
    "cancelled": {"en": "Action cancelled."},
}


def t(key: str, lang: str = "en", **kwargs: object) -> str:
    """Return the template for key in lang, falling back to English."""
    variants = TEMPLATES[key]
    return variants.get(lang, variants["en"]).format(**kwargs)
