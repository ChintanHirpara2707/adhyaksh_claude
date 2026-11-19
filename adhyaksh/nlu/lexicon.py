"""Multilingual action lexicon: the one source of verbs, negation words, target nouns and speech-recognition
variants for both the training-data generator (nlu/dataset.py) and the frame parser (nlu/frames.py).

Actions are separated from targets: "open" and "close" are two values of one ACTION slot, so opposite actions are
decided by which verb was said, never learned as unrelated labels. Each action lists verb forms per language
style (en, hi = Devanagari Hindi, gu = Gujarati script, hinglish, gujlish).
"""
from __future__ import annotations

LANGS = ("en", "hi", "gu", "hinglish", "gujlish")

# action -> language style -> verb forms (longest forms are matched first by the parser).
ACTIONS: dict[str, dict[str, list[str]]] = {
    "open": {
        "en": ["open", "launch", "start", "run", "fire up", "bring up", "pull up", "load up", "boot up", "turn on"],
        "hinglish": ["kholo", "khol do", "khol de", "kholna", "khol", "chalu karo", "chalu kar do", "chalu karna", "chalu",
                     "shuru karo", "start karo", "start kar do", "open karo", "open kar do", "on karo"],
        "gujlish": ["kholo", "kholi do", "kholi aapo", "kholi nakho", "kholvu", "chalu karo", "chalu kari do",
                    "sharu karo", "start karo", "open karo", "open kari do", "on karo"],
        "hi": ["खोलो", "खोल दो", "खोल दीजिए", "खोलना", "खोल", "चालू करो", "चालू कर दो", "चालू", "शुरू करो",
               "स्टार्ट करो", "ओपन करो", "ऑन करो"],
        "gu": ["ખોલો", "ખોલી દો", "ખોલી આપો", "ખોલવું", "ખોલ", "ચાલુ કરો", "ચાલુ કરી દો", "ચાલુ", "શરૂ કરો",
               "સ્ટાર્ટ કરો", "ઓપન કરો", "ઓન કરો"],
    },
    "close": {
        "en": ["close", "quit", "exit", "shut", "shut down", "stop", "kill", "end", "terminate", "turn off"],
        "hinglish": ["band karo", "band kar do", "band kar de", "band karna", "band", "bandh karo", "off karo",
                     "off kar do", "close karo", "close kar do", "exit karo"],
        "gujlish": ["bandh karo", "bandh kari do", "bandh kari nakho", "bandh karvu", "bandh", "band karo",
                    "off karo", "off kari do", "close karo", "close kari do"],
        "hi": ["बंद करो", "बंद कर दो", "बंद कर दीजिए", "बंद करना", "बंद", "ऑफ करो", "क्लोज करो"],
        "gu": ["બંધ કરો", "બંધ કરી દો", "બંધ કરી નાખો", "બંધ કરવું", "બંધ", "ઓફ કરો", "ક્લોઝ કરો"],
    },
    "create": {
        "en": ["create", "make", "generate", "set up", "start a new"],
        "hinglish": ["bana do", "banao", "bana de", "banana", "create karo", "create kar do", "bana"],
        "gujlish": ["banavo", "banavi do", "banavi aapo", "banavvu", "create karo", "create kari do"],
        "hi": ["बनाओ", "बना दो", "बना दीजिए", "बनाना", "तैयार करो", "क्रिएट करो"],
        "gu": ["બનાવો", "બનાવી દો", "બનાવી આપો", "બનાવવું", "તૈયાર કરો", "ક્રિએટ કરો"],
    },
    "delete": {
        "en": ["delete", "remove", "erase", "trash", "get rid of", "discard", "wipe"],
        "hinglish": ["delete karo", "delete kar do", "delete karna", "hata do", "hatao", "mita do", "remove karo", "delete"],
        "gujlish": ["delete karo", "delete kari do", "kadhi nakho", "kadhi nakhvu", "hatavi do", "bhunsi nakho", "delete"],
        "hi": ["हटाओ", "हटा दो", "हटाना", "डिलीट करो", "डिलीट कर दो", "मिटा दो", "मिटाओ"],
        "gu": ["કાઢી નાખો", "કાઢી નાખવું", "ડિલીટ કરો", "ડિલીટ કરી દો", "હટાવી દો", "ભૂંસી નાખો"],
    },
    "search": {
        "en": ["search for", "search", "find", "look for", "locate", "where is"],
        "hinglish": ["dhundo", "dhoondo", "dhund do", "search karo", "khojo", "kahan hai"],
        "gujlish": ["shodho", "shodhi do", "search karo", "kya che"],
        "hi": ["ढूंढो", "ढूँढो", "खोजो", "सर्च करो", "कहाँ है"],
        "gu": ["શોધો", "શોધી દો", "સર્ચ કરો", "ક્યાં છે"],
    },
}

# Words that turn a command into a refusal ("don't open", "mat kholo", "ના ખોલો"). Whole-word matches only.
NEGATION: dict[str, list[str]] = {
    "en": ["don't", "dont", "do not", "never", "no need to", "not", "stop you from", "i don't want to",
           "i do not want to", "won't", "shouldn't", "must not"],
    "hinglish": ["mat", "nahi", "nahin", "na", "mt"],
    "gujlish": ["na", "nahi", "nai", "mat", "nahin"],
    "hi": ["मत", "नहीं", "ना", "न"],
    "gu": ["ના", "નહીં", "નહિ", "મત", "નહી"],
}

# Target nouns that name the kind of thing acted on.
TARGET_NOUNS: dict[str, dict[str, list[str]]] = {
    "app": {"en": ["app", "application", "program", "software"], "hinglish": ["app", "application"],
            "gujlish": ["app", "application"], "hi": ["ऐप", "एप", "प्रोग्राम"], "gu": ["એપ", "પ્રોગ્રામ"]},
    "file": {"en": ["file", "document"], "hinglish": ["file"], "gujlish": ["file"], "hi": ["फाइल", "फ़ाइल"],
             "gu": ["ફાઇલ", "ફાઈલ"]},
    "folder": {"en": ["folder", "directory"], "hinglish": ["folder"], "gujlish": ["folder"], "hi": ["फोल्डर"],
               "gu": ["ફોલ્ડર"]},
}

# Application names: canonical allow-list key -> spellings in every script, including speech-recognition slips.
APP_NAMES: dict[str, list[str]] = {
    "notepad": ["notepad", "note pad", "notepat", "noted pad", "नोटपैड", "नोट पैड", "નોટપેડ", "નોટ પેડ"],
    "calculator": ["calculator", "calculater", "calculaor", "calc", "कैलकुलेटर", "केलकुलेटर", "કેલ્ક્યુલેટર", "કેલ્ક્યુલેટર"],
    "chrome": ["chrome", "google chrome", "crome", "krome", "chrom", "क्रोम", "गूगल क्रोम", "ક્રોમ", "ગૂગલ ક્રોમ"],
    "paint": ["paint", "ms paint", "mspaint", "पेंट", "પેઇન્ટ", "પેન્ટ"],
    "edge": ["edge", "microsoft edge", "ms edge", "एज", "એજ"],
    "brave": ["brave", "brave browser", "ब्रेव", "બ્રેવ"],
    "vs code": ["vs code", "vscode", "visual studio code", "v s code", "code editor", "वीएस कोड", "વીએસ કોડ"],
    "whatsapp": ["whatsapp", "whats app", "watsapp", "whatsap", "व्हाट्सएप", "व्हाट्सऐप", "વોટ્સએપ", "વૉટ્સએપ"],
    "spotify": ["spotify", "spotifi", "spot ify", "स्पॉटिफाई", "स्पोटिफाई", "સ્પોટિફાઇ", "સ્પોટીફાય"],
    "snipping tool": ["snipping tool", "snip tool", "snipping", "स्निपिंग टूल", "સ્નિપિંગ ટૂલ"],
    "file explorer": ["file explorer", "explorer", "windows explorer", "फाइल एक्सप्लोरर", "ફાઇલ એક્સપ્લોરર"],
}

# Filler words that carry no meaning in a command (stripped before slot extraction).
FILLERS: dict[str, list[str]] = {
    "en": ["please", "pls", "plz", "kindly", "hey", "hi", "uh", "um", "umm", "hmm", "ok", "okay", "now", "right now",
           "for me", "can you", "could you", "would you", "will you", "just", "quickly", "the", "a", "an", "my",
           "assistant", "adhyaksh", "jarvis", "wait", "yaar"],
    "hinglish": ["zara", "jaldi", "abhi", "please", "yaar", "bhai", "mere liye", "ek baar", "ko"],
    "gujlish": ["jara", "jaldi", "atyare", "please", "ne", "mara mate", "ek var", "to"],
    "hi": ["कृपया", "ज़रा", "जरा", "जल्दी", "अभी", "मेरे लिए", "प्लीज़", "प्लीज", "को", "एक बार"],
    "gu": ["મહેરબાની કરીને", "કૃપા કરીને", "જરા", "જલ્દી", "હમણાં", "હવે", "મારા માટે", "પ્લીઝ", "ને", "એક વાર"],
}

# Word order per language style: English puts the verb first, the others usually after the object.
VERB_FIRST = {"en": True, "hi": False, "gu": False, "hinglish": False, "gujlish": False}
