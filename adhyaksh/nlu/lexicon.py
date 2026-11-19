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
        "en": ["close", "quit", "exit", "shut", "shut down", "shutdown", "stop", "kill", "end", "terminate", "turn off",
               "switch off", "power off"],
        "hinglish": ["band karo", "band kar do", "band kar de", "band karna", "band", "bandh karo", "off karo",
                     "off kar do", "close karo", "close kar do", "exit karo"],
        "gujlish": ["bandh karo", "bandh kari do", "bandh kari nakho", "bandh karvu", "bandh", "band karo",
                    "off karo", "off kari do", "close karo", "close kari do"],
        "hi": ["बंद करो", "बंद कर दो", "बंद कर दीजिए", "बंद करना", "बंद", "ऑफ करो", "क्लोज करो", "शटडाउन करो"],
        "gu": ["બંધ કરો", "બંધ કરી દો", "બંધ કરી નાખો", "બંધ કરવું", "બંધ", "ઓફ કરો", "ક્લોઝ કરો", "શટડાઉન કરો"],
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
    # Levels (volume, brightness). "set" is also implied by a target with a number: "volume 40".
    "increase": {
        "en": ["increase", "raise", "turn up", "boost", "make louder", "louder", "brighter", "up"],
        "hinglish": ["badhao", "badha do", "badhana", "tez karo", "tez kar do", "zyada karo", "upar karo"],
        "gujlish": ["vadharo", "vadhari do", "vadharvu", "tez karo", "vadhare karo", "upar karo"],
        "hi": ["बढ़ाओ", "बढ़ा दो", "बढ़ाना", "तेज करो", "तेज़ करो", "ज़्यादा करो", "ज्यादा करो"],
        "gu": ["વધારો", "વધારી દો", "વધારવું", "તેજ કરો", "વધારે કરો"],
    },
    "decrease": {
        "en": ["decrease", "lower", "reduce", "turn down", "dim", "quieter", "softer", "make quieter", "down"],
        "hinglish": ["kam karo", "kam kar do", "kam karna", "ghatao", "ghata do", "dheema karo", "dheere karo", "neeche karo"],
        "gujlish": ["ocho karo", "ochu karo", "ochhu karo", "ochi karo", "ghatado", "ghatadi do", "dhimu karo", "niche karo"],
        "hi": ["कम करो", "कम कर दो", "कम करना", "घटाओ", "घटा दो", "धीमा करो", "धीमी करो"],
        "gu": ["ઓછું કરો", "ઓછો કરો", "ઓછી કરો", "ઓછું કરી દો", "ઓછી કરી દો", "ઘટાડો", "ઘટાડી દો", "ધીમું કરો", "ધીમી કરો"],
    },
    "set": {
        "en": ["set", "change", "adjust"],
        "hinglish": ["set karo", "set kar do", "rakho", "kar do"],
        "gujlish": ["set karo", "set kari do", "rakho", "kari do"],
        "hi": ["सेट करो", "सेट कर दो", "रखो", "कर दो"],
        "gu": ["સેટ કરો", "સેટ કરી દો", "રાખો", "કરી દો"],
    },
    "mute": {
        "en": ["mute", "silence"],
        "hinglish": ["mute karo", "mute kar do", "awaaz band karo", "awaaz band kar do", "awaz band karo"],
        "gujlish": ["mute karo", "mute kari do", "avaj bandh karo", "awaj bandh karo"],
        "hi": ["म्यूट करो", "म्यूट कर दो", "आवाज़ बंद करो", "आवाज बंद करो"],
        "gu": ["મ્યૂટ કરો", "મ્યુટ કરો", "અવાજ બંધ કરો"],
    },
    # Power. "shut down" and "turn off" are close verbs; with the PC as target they mean shut down.
    "lock": {
        "en": ["lock"], "hinglish": ["lock karo", "lock kar do"], "gujlish": ["lock karo", "lock kari do"],
        "hi": ["लॉक करो", "लॉक कर दो"], "gu": ["લૉક કરો", "લોક કરો", "લોક કરી દો"],
    },
    "restart": {
        "en": ["restart", "reboot"], "hinglish": ["restart karo", "restart kar do", "reboot karo"],
        "gujlish": ["restart karo", "restart kari do", "reboot karo"],
        "hi": ["रीस्टार्ट करो", "रीस्टार्ट कर दो", "दोबारा चालू करो"], "gu": ["રીસ્ટાર્ટ કરો", "રીસ્ટાર્ટ કરી દો"],
    },
    "sleep": {
        "en": ["put to sleep", "sleep"], "hinglish": ["sleep mode me dalo", "sleep karo", "sula do"],
        "gujlish": ["sleep mode ma muko", "sleep karo"], "hi": ["स्लीप मोड में डालो", "सुला दो"],
        "gu": ["સ્લીપ મોડમાં મૂકો", "સ્લીપ કરો"],
    },
    "cancel": {
        "en": ["cancel", "abort", "call off"], "hinglish": ["cancel karo", "cancel kar do", "rok do", "roko"],
        "gujlish": ["cancel karo", "cancel kari do", "roki do", "roko"], "hi": ["कैंसिल करो", "रद्द करो", "रोक दो", "रोको"],
        "gu": ["કેન્સલ કરો", "રદ કરો", "રોકી દો", "રોકો"],
    },
    # Windows of open apps.
    "minimize": {
        "en": ["minimize", "minimise", "hide"], "hinglish": ["minimize karo", "minimise karo", "chhota karo", "chhupa do"],
        "gujlish": ["minimize karo", "minimise karo", "nanu karo", "santadi do"], "hi": ["मिनिमाइज़ करो", "मिनिमाइज करो", "छोटा करो", "छोटी करो", "छोटे करो"],
        "gu": ["મિનિમાઇઝ કરો", "નાનું કરો", "નાની કરો", "નાનો કરો"],
    },
    "maximize": {
        "en": ["maximize", "maximise", "make full screen", "full screen"], "hinglish": ["maximize karo", "bada karo", "full screen karo"],
        "gujlish": ["maximize karo", "motu karo", "full screen karo"], "hi": ["मैक्सिमाइज़ करो", "मैक्सिमाइज करो", "बड़ा करो", "बड़ी करो", "बड़े करो", "फुल स्क्रीन करो"],
        "gu": ["મેક્સિમાઇઝ કરો", "મોટું કરો", "મોટી કરો", "મોટો કરો", "ફુલ સ્ક્રીન કરો"],
    },
    "focus": {
        "en": ["switch to", "go to", "focus on", "focus"], "hinglish": ["pe jao", "par jao", "pe switch karo"],
        "gujlish": ["par jao", "pe jao", "par switch karo"], "hi": ["पर जाओ", "पे जाओ"], "gu": ["પર જાઓ"],
    },
    "restore": {
        "en": ["restore", "unminimize", "bring back"], "hinglish": ["restore karo", "wapas lao"], "gujlish": ["restore karo", "pachu lavo"],
        "hi": ["रिस्टोर करो", "वापस लाओ"], "gu": ["રિસ્ટોર કરો", "પાછું લાવો"],
    },
    "unmute": {
        "en": ["unmute"],
        "hinglish": ["unmute karo", "unmute kar do", "awaaz chalu karo", "awaz chalu karo"],
        "gujlish": ["unmute karo", "unmute kari do", "avaj chalu karo", "awaj chalu karo"],
        "hi": ["अनम्यूट करो", "आवाज़ चालू करो", "आवाज चालू करो"],
        "gu": ["અનમ્યૂટ કરો", "અવાજ ચાલુ કરો"],
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
    # System targets: a noun names the thing ("turn up the volume", "brightness kam karo").
    "volume": {"en": ["volume", "sound", "speaker", "speakers", "audio"], "hinglish": ["volume", "awaaz", "awaz", "aawaz", "sound"],
               "gujlish": ["volume", "avaj", "awaj", "sound"], "hi": ["वॉल्यूम", "वोल्यूम", "आवाज़", "आवाज", "साउंड"],
               "gu": ["વોલ્યુમ", "વોલ્યૂમ", "અવાજ", "સાઉન્ડ"]},
    "mic": {"en": ["mic", "microphone", "mike"], "hinglish": ["mic", "microphone"], "gujlish": ["mic", "microphone"],
            "hi": ["माइक", "माइक्रोफोन"], "gu": ["માઇક", "માઇક્રોફોન"]},
    "brightness": {"en": ["brightness", "screen brightness", "display brightness"], "hinglish": ["brightness", "roshni"],
                   "gujlish": ["brightness", "prakash"], "hi": ["ब्राइटनेस", "रोशनी", "चमक"], "gu": ["બ્રાઇટનેસ", "પ્રકાશ"]},
    "wifi": {"en": ["wifi", "wi-fi", "wi fi", "wireless"], "hinglish": ["wifi", "wi-fi"], "gujlish": ["wifi", "wi-fi"],
             "hi": ["वाईफाई", "वाई-फाई", "वायफाय"], "gu": ["વાઇફાઇ", "વાઈફાઈ", "વાઇ-ફાઇ"]},
    "bluetooth": {"en": ["bluetooth", "blue tooth"], "hinglish": ["bluetooth"], "gujlish": ["bluetooth"],
                  "hi": ["ब्लूटूथ"], "gu": ["બ્લૂટૂથ", "બ્લુટુથ"]},
    "pc": {"en": ["pc", "computer", "laptop", "the system", "my system", "machine"], "hinglish": ["pc", "computer", "laptop"],
           "gujlish": ["pc", "computer", "laptop"], "hi": ["पीसी", "कंप्यूटर", "कम्प्यूटर", "लैपटॉप"],
           "gu": ["પીસી", "કમ્પ્યુટર", "કૉમ્પ્યુટર", "લેપટોપ", "લૅપટૉપ"]},
    "screen": {"en": ["screen"], "hinglish": ["screen"], "gujlish": ["screen"], "hi": ["स्क्रीन"], "gu": ["સ્ક્રીન"]},
    "window": {"en": ["window", "windows", "all windows", "every window", "everything"], "hinglish": ["window", "sab windows", "saari windows"],
               "gujlish": ["window", "badhi windows", "badha windows"], "hi": ["विंडो", "सारी विंडो", "सब विंडो"],
               "gu": ["વિન્ડો", "બધી વિન્ડો"]},
    "shutdown": {"en": ["shutdown", "shut down", "restart", "reboot"], "hinglish": ["shutdown", "restart"],
                 "gujlish": ["shutdown", "restart"], "hi": ["शटडाउन", "रीस्टार्ट"], "gu": ["શટડાઉન", "રીસ્ટાર્ટ"]},
}
# Which target nouns are system targets (checked after files, before apps), most specific first: "screen
# brightness" is brightness, "lock the screen" is the screen, "cancel the shutdown" is the scheduled shutdown.
SYSTEM_TARGETS = ("mic", "brightness", "volume", "wifi", "bluetooth", "pc", "screen", "shutdown")

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
