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
    "ask_memory": {
        "en": "What should I remember?",
        "hi": "मुझे क्या याद रखना है?",
        "gu": "મારે શું યાદ રાખવું છે?",
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
    "memory_updated": {
        "en": "Updated in memory: {fact} (was: {previous}).",
        "hi": "स्मृति में बदला गया: {fact} (पहले: {previous})।",
        "gu": "મેમરીમાં બદલ્યું: {fact} (પહેલાં: {previous}).",
    },
    "memory_forgotten": {
        "en": "Forgotten: {fact}.",
        "hi": "भुला दिया: {fact}।",
        "gu": "ભૂલી ગયો: {fact}.",
    },
    "confirm_forget": {
        "en": "Forget this: {fact}? Say yes to confirm or no to cancel.",
        "hi": "क्या इसे भुला दूँ: {fact}? हाँ या नहीं कहें।",
        "gu": "આ ભૂલી જાઉં: {fact}? હા અથવા ના કહો.",
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
    "volume_level_set": {"en": "The {name} is at {level} percent.", "hi": "{name} अब {level} प्रतिशत है।",
                         "gu": "{name} હવે {level} ટકા છે."},
    "volume_muted": {"en": "The {name} is muted.", "hi": "{name} म्यूट कर दिया।", "gu": "{name} મ્યૂટ કર્યું."},
    "volume_unmuted": {"en": "The {name} is on again, at {level} percent.", "hi": "{name} फिर चालू है, {level} प्रतिशत पर।",
                       "gu": "{name} ફરી ચાલુ છે, {level} ટકા પર."},
    "battery_on": {"en": "Battery {percent} percent, on battery power.", "hi": "बैटरी {percent} प्रतिशत, बैटरी पर।",
                   "gu": "બેટરી {percent} ટકા, બેટરી પર."},
    "battery_charging": {"en": "Battery {percent} percent, plugged in.", "hi": "बैटरी {percent} प्रतिशत, चार्जर लगा है।",
                         "gu": "બેટરી {percent} ટકા, ચાર્જર લાગેલું છે."},
    "window_focus": {"en": "Switched to {title}.", "hi": "{title} पर आ गया।", "gu": "{title} પર આવ્યો."},
    "window_minimize": {"en": "Minimized {title}.", "hi": "{title} छोटा कर दिया।", "gu": "{title} નાનું કર્યું."},
    "window_maximize": {"en": "Maximized {title}.", "hi": "{title} बड़ा कर दिया।", "gu": "{title} મોટું કર્યું."},
    "window_restore": {"en": "Restored {title}.", "hi": "{title} वापस ले आया।", "gu": "{title} પાછું લાવ્યો."},
    "window_close": {"en": "Asked {title} to close.", "hi": "{title} को बंद करने को कहा।", "gu": "{title}ને બંધ કરવા કહ્યું."},
    "window_minimize_all": {"en": "Minimized all windows.", "hi": "सारी विंडो छोटी कर दीं।", "gu": "બધી વિન્ડો નાની કરી."},
    "window_restore_all": {"en": "Restored all windows.", "hi": "सारी विंडो वापस ले आया।", "gu": "બધી વિન્ડો પાછી લાવ્યો."},
    "radio_set": {"en": "{radio} is {state}.", "hi": "{radio} अब {state} है।", "gu": "{radio} હવે {state} છે."},
    "confirm_system": {"en": "Do you want me to {what}? Say yes to confirm or no to cancel.",
                       "hi": "क्या मैं यह करूँ: {what}? हाँ या नहीं कहें।", "gu": "શું હું આ કરું: {what}? હા અથવા ના કહો."},
    "power_lock": {"en": "Locked the PC.", "hi": "पीसी लॉक कर दिया।", "gu": "પીસી લૉક કર્યું."},
    "power_sleep": {"en": "Putting the PC to sleep.", "hi": "पीसी को स्लीप में डाल रहा हूँ।", "gu": "પીસીને સ્લીપમાં મૂકું છું."},
    "power_restart": {"en": "The PC will restart in {seconds} seconds. Say cancel the shutdown to stop it.",
                      "hi": "पीसी {seconds} सेकंड में रीस्टार्ट होगा। रोकने के लिए कहें: cancel the shutdown।",
                      "gu": "પીસી {seconds} સેકન્ડમાં રીસ્ટાર્ટ થશે. રોકવા માટે કહો: cancel the shutdown."},
    "power_shutdown": {"en": "The PC will shut down in {seconds} seconds. Say cancel the shutdown to stop it.",
                       "hi": "पीसी {seconds} सेकंड में बंद होगा। रोकने के लिए कहें: cancel the shutdown।",
                       "gu": "પીસી {seconds} સેકન્ડમાં બંધ થશે. રોકવા માટે કહો: cancel the shutdown."},
    "power_cancel": {"en": "The scheduled shutdown is cancelled.", "hi": "तय किया गया शटडाउन रद्द कर दिया।",
                     "gu": "નક્કી કરેલું શટડાઉન રદ કર્યું."},
    "brightness_set": {"en": "Brightness is at {level} percent.", "hi": "ब्राइटनेस अब {level} प्रतिशत है।",
                       "gu": "બ્રાઇટનેસ હવે {level} ટકા છે."},
    "app_closed": {"en": "Closed {app}."},
    "negated": {"en": "Okay, I won't {what}. Nothing was changed.",
                "hi": "ठीक है, {target} के साथ कुछ नहीं किया गया।",
                "gu": "બરાબર, {target} સાથે કંઈ કરવામાં આવ્યું નથી."},
    "negated_plain": {"en": "Okay, I won't do that. Nothing was changed.",
                      "hi": "ठीक है, कुछ नहीं किया गया।", "gu": "બરાબર, કંઈ કરવામાં આવ્યું નથી."},
    "app_close_waiting": {"en": "Asked {app} to close. It is showing a save prompt, so answer it there to finish."},
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
    "ask_web_url": {"en": "Which website, or what should I search for?",
                    "hi": "कौन सी वेबसाइट खोलूं, या क्या खोजूं?",
                    "gu": "કયી વેબસાઇટ ખોલવી, અથવા શું શોધવું?"},
    "smalltalk_thanks": {
        "en": "You're welcome.",
        "hi": "आपका स्वागत है।",
        "gu": "તમારું સ્વાગત છે.",
    },
    "smalltalk_bye": {
        "en": "Goodbye. Have a good day.",
        "hi": "अलविदा। आपका दिन शुभ रहे।",
        "gu": "અલવિદા. તમારો દિવસ શુભ રહે.",
    },
    "smalltalk_how_are_you": {
        "en": "I am doing well, thank you. How can I help you?",
        "hi": "मैं ठीक हूँ, धन्यवाद। मैं आपकी कैसे सहायता कर सकता हूँ?",
        "gu": "હું બરાબર છું, આભાર. હું તમને કેવી રીતે મદદ કરી શકું?",
    },
    "cannot_do_yet": {
        "en": "I cannot do that yet. {capabilities}",
        "hi": "मैं अभी वह काम नहीं कर सकता। {capabilities}",
        "gu": "હું હજી એ કામ કરી શકતો નથી. {capabilities}",
    },
    "needs_cowork": {
        "en": "That action needs Cowork mode. Switch to Cowork to run it.",
        "hi": "यह क्रिया करने के लिए कॉर्क मोड की आवश्यकता है। कॉर्क मोड पर स्विच करें।",
        "gu": "આ ક્રિયા ચલાવવા માટે કોર્ક મોડની જરૂર છે. કોર્ક મોડ પર સ્વિચ કરો.",
    },
}


def t(key: str, lang: str = "en", **kwargs: object) -> str:
    """Return the template for key in lang, falling back to English."""
    variants = TEMPLATES[key]
    return variants.get(lang, variants["en"]).format(**kwargs)
