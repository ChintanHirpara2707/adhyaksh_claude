"""Intent dataset: generation, validation, loading and splitting.

CLI: python -m adhyaksh.nlu.dataset generate|augment|validate|report
All generated rows are marked reviewed=false until the author confirms them.
"""
from __future__ import annotations

import hashlib
import random
import re
import sys
from itertools import product
from pathlib import Path

from adhyaksh import config

INTENTS = ["greet", "set_identity", "get_identity", "memory_save", "memory_recall", "file_create",
           "file_read", "file_update", "file_delete", "file_search", "office_create", "app_open",
           "app_close", "system_status", "doc_question", "knowledge_question", "help", "unknown",
           "out_of_scope", "bot_identity", "time_date", "folder_create", "screenshot",
           "special_folder_open", "web_open"]
LANGS = ["en", "hi", "gu", "hinglish", "gujlish"]
SCRIPTS = ["latin", "devanagari", "gujarati"]
SOURCES = ["generated", "author", "corrected"]
COLUMNS = ["text", "intent", "language", "script", "source", "reviewed"]
MIN_PER_INTENT, MIN_TOTAL, MIN_LANG_SHARE, MIN_CODEMIXED = 40, 500, 0.15, 100
TRAIN_CSV = config.ROOT / "data" / "intents.csv"
TEST_CSV = config.ROOT / "data" / "test_codemixed.csv"

_FILES = ["report.txt", "notes.txt", "budget.xlsx", "todo.docx", "resume.pdf", "data.csv",
          "summary.txt", "invoice.docx", "marks.xlsx", "diary.txt", "plan.docx", "list.txt"]
_OFFICE = ["names.xlsx", "sales.xlsx", "marks.xlsx", "letter.docx", "report.docx", "minutes.docx"]
_LAT_APPS = ["notepad", "calculator", "chrome", "vs code", "paint", "word", "excel"]
_LAT_NAMES = ["Chintan", "Priya", "Raj", "Amit", "Hiral", "Neha", "Karan", "Meera", "Jay", "Pooja"]
_LAT_D = ["project deadline", "budget", "conclusion", "methodology", "main findings", "safety rules"]
_LAT_T = ["car", "favorite color", "dog", "room number", "exam", "bike"]
POOLS: dict[str, dict[str, list[str]]] = {
    "en": {"f": _FILES, "o": _OFFICE, "a": _LAT_APPS, "n": _LAT_NAMES,
           "x": ["my car is Audi", "my favorite color is blue", "my exam is on Friday",
                 "my dog is named Bruno", "my room number is 204", "my bike is a Honda"],
           "t": _LAT_T, "d": ["the project deadline", "the budget", "the conclusion", "the methodology",
                              "the main findings", "the safety rules"],
           "q": ["what is the capital of France", "explain photosynthesis", "how fast is light",
                 "who wrote Hamlet", "why is the sky blue", "what is machine learning",
                 "how do airplanes fly", "tell me about black holes"]},
    "hi": {"f": _FILES, "o": _OFFICE, "a": ["नोटपैड", "कैलकुलेटर", "क्रोम", "पेंट"],
           "n": ["अमित", "प्रिया", "राज", "नेहा", "करण", "मीरा"],
           "x": ["मेरी कार ऑडी है", "मेरा पसंदीदा रंग नीला है", "मेरी परीक्षा शुक्रवार को है",
                 "मेरा कुत्ता ब्रूनो है", "मेरा कमरा नंबर 204 है"],
           "t": ["कार", "पसंदीदा रंग", "कुत्ता", "कमरा नंबर", "परीक्षा", "बाइक"],
           "d": ["परियोजना की समय सीमा", "बजट", "निष्कर्ष", "कार्यप्रणाली", "मुख्य निष्कर्ष"],
           "q": ["फ्रांस की राजधानी क्या है", "प्रकाश संश्लेषण समझाओ", "प्रकाश की गति कितनी है",
                 "हैमलेट किसने लिखा", "आसमान नीला क्यों होता है", "मशीन लर्निंग क्या है",
                 "हवाई जहाज कैसे उड़ता है", "ब्लैक होल के बारे में बताओ"]},
    "gu": {"f": _FILES, "o": _OFFICE, "a": ["નોટપેડ", "કેલ્ક્યુલેટર", "ક્રોમ", "પેઇન્ટ"],
           "n": ["હિરલ", "ચિંતન", "જય", "પૂજા", "કરણ", "મીરા"],
           "x": ["મારી કાર ઓડી છે", "મારો ગમતો રંગ વાદળી છે", "મારી પરીક્ષા શુક્રવારે છે",
                 "મારો કૂતરો બ્રુનો છે", "મારો રૂમ નંબર 204 છે"],
           "t": ["કાર", "ગમતો રંગ", "કૂતરો", "રૂમ નંબર", "પરીક્ષા", "બાઇક"],
           "d": ["પ્રોજેક્ટની સમયમર્યાદા", "બજેટ", "નિષ્કર્ષ", "પદ્ધતિ", "મુખ્ય તારણો"],
           "q": ["ફ્રાન્સની રાજધાની શું છે", "પ્રકાશસંશ્લેષણ સમજાવો", "પ્રકાશની ગતિ કેટલી છે",
                 "હેમલેટ કોણે લખ્યું", "આકાશ વાદળી કેમ હોય છે", "મશીન લર્નિંગ શું છે",
                 "વિમાન કેવી રીતે ઉડે છે", "બ્લેક હોલ વિશે કહો"]},
    "hinglish": {"f": _FILES, "o": _OFFICE, "a": _LAT_APPS, "n": _LAT_NAMES,
                 "x": ["meri car Audi hai", "mera favorite color blue hai", "meri exam Friday ko hai",
                       "mera dog ka naam Bruno hai", "mera room number 204 hai"],
                 "t": _LAT_T, "d": _LAT_D,
                 "q": ["france ki capital kya hai", "photosynthesis samjhao", "light ki speed kitni hoti hai",
                       "hamlet kisne likha", "aasman neela kyun hota hai", "machine learning kya hai",
                       "airplane kaise udta hai", "black hole ke baare mein batao"]},
    "gujlish": {"f": _FILES, "o": _OFFICE, "a": _LAT_APPS, "n": _LAT_NAMES,
                "x": ["mari car Audi che", "maro favorite color blue che", "mari exam Friday e che",
                      "maro dog Bruno che", "maro room number 204 che"],
                "t": _LAT_T, "d": _LAT_D,
                "q": ["france ni capital shu che", "photosynthesis samjavo", "light ni speed ketli che",
                      "hamlet koe lakhyu", "aakash vadlu kem hoy che", "machine learning shu che",
                      "airplane kevi rite ude che", "black hole vishe kaho"]},
}
PRE = {"en": ["", "please ", "hey, ", "assistant, "], "hi": ["", "कृपया ", "सुनो, "],
       "gu": ["", "કૃપા કરીને ", "સાંભળો, "], "hinglish": ["", "please ", "suno, "],
       "gujlish": ["", "please ", "sambhdo, "]}
SUF = {"en": ["", " please", " now"], "hi": ["", " जल्दी", " अभी"], "gu": ["", " જલ્દી", " હમણાં"],
       "hinglish": ["", " jaldi", " abhi"], "gujlish": ["", " jaldi", " atyare"]}

T = "templates"
TEMPLATES: dict[str, dict[str, list[str]]] = {
    "greet": {
        "en": ["hello", "hi", "hey", "good morning", "good evening", "hello assistant", "hi there",
               "hey there", "good afternoon", "greetings"],
        "hi": ["नमस्ते", "नमस्कार", "हेलो", "हाय", "सुप्रभात", "शुभ संध्या", "नमस्ते सहायक", "हेलो दोस्त",
               "राम राम", "प्रणाम"],
        "gu": ["નમસ્તે", "કેમ છો", "હેલો", "હાય", "સુપ્રભાત", "શુભ સંધ્યા", "નમસ્તે સહાયક", "જય શ્રી કૃષ્ણ",
               "હેલો મિત્ર", "કેમ છો દોસ્ત"],
        "hinglish": ["namaste", "hello yaar", "hi bhai", "kaise ho", "good morning dost", "suprabhat",
                     "hey kya haal hai", "ram ram", "hello assistant ji", "namaskar"],
        "gujlish": ["kem cho", "hello dost", "hi bhai", "su chale che", "good morning mitra",
                    "jai shree krishna", "hello assistant", "kem chho yaar", "hey su khabar", "namaskar mitra"]},
    "set_identity": {
        "en": ["my name is {n}", "call me {n}", "i am your new user {n}", "you can call me {n}"],
        "hi": ["मेरा नाम {n} है", "मुझे {n} कहो", "मैं आपका नया उपयोगकर्ता {n} हूँ"],
        "gu": ["મારું નામ {n} છે", "મને {n} કહો", "હું તમારો નવો વપરાશકર્તા {n} છું"],
        "hinglish": ["mera naam {n} hai", "mujhe {n} bulao", "main aapka naya user {n} hoon"],
        "gujlish": ["maru naam {n} che", "mane {n} kaho", "hu tamaro navo user {n} chu"]},
    "get_identity": {
        "en": ["what is my name", "who am i", "do you know my name", "tell me my name"],
        "hi": ["मेरा नाम क्या है", "मैं कौन हूँ", "क्या तुम्हें मेरा नाम पता है", "मेरा नाम बताओ"],
        "gu": ["મારું નામ શું છે", "હું કોણ છું", "શું તને મારું નામ ખબર છે", "મારું નામ કહો"],
        "hinglish": ["mera naam kya hai", "main kaun hoon", "kya tumhe mera naam pata hai", "mera naam batao"],
        "gujlish": ["maru naam shu che", "hu kon chu", "tane maru naam khabar che", "maru naam kaho"]},
    "memory_save": {
        "en": ["remember that {x}", "{x}", "note down that {x}", "save this: {x}"],
        "hi": ["याद रखो कि {x}", "{x}", "यह नोट करो कि {x}", "सहेज लो: {x}"],
        "gu": ["યાદ રાખો કે {x}", "{x}", "નોંધ કરો કે {x}", "સાચવો: {x}"],
        "hinglish": ["yaad rakhna ki {x}", "{x}", "note kar lo ki {x}", "save karo: {x}"],
        "gujlish": ["yaad rakhjo ke {x}", "{x}", "note kari lo ke {x}", "save karo: {x}"]},
    "memory_recall": {
        "en": ["what is my {t}", "do you remember my {t}", "tell me my {t}"],
        "hi": ["मेरा {t} क्या है", "क्या तुम्हें मेरा {t} याद है", "मुझे मेरा {t} बताओ"],
        "gu": ["મારો {t} શું છે", "શું તને મારો {t} યાદ છે", "મને મારો {t} કહો"],
        "hinglish": ["mera {t} kya hai", "kya tumhe mera {t} yaad hai", "mujhe mera {t} batao"],
        "gujlish": ["maro {t} shu che", "tane maro {t} yaad che", "mane maro {t} kaho"]},
    "file_create": {
        "en": ["create a file named {f}", "make a new file {f}", "create {f}", "new file called {f}"],
        "hi": ["{f} नाम की फाइल बनाओ", "नई फाइल {f} बनाओ", "{f} बनाओ"],
        "gu": ["{f} નામની ફાઇલ બનાવો", "નવી ફાઇલ {f} બનાવો", "{f} બનાવો"],
        "hinglish": ["{f} naam ki file banao", "nayi file {f} create karo", "{f} banao"],
        "gujlish": ["{f} naam ni file banavo", "navi file {f} create karo", "{f} banavo"]},
    "file_read": {
        "en": ["read {f}", "open file {f} and show its content", "show me what is inside {f}", "display {f}"],
        "hi": ["{f} पढ़ो", "{f} की सामग्री दिखाओ", "फाइल {f} में क्या है"],
        "gu": ["{f} વાંચો", "{f} ની સામગ્રી બતાવો", "ફાઇલ {f} માં શું છે"],
        "hinglish": ["{f} padho", "{f} ka content dikhao", "file {f} mein kya hai"],
        "gujlish": ["{f} vancho", "{f} nu content batavo", "file {f} ma shu che"]},
    "file_update": {
        "en": ["add a line to {f}", "append text to {f}", "update {f} with new content",
               "write something into {f}"],
        "hi": ["{f} में एक पंक्ति जोड़ो", "{f} में नया टेक्स्ट लिखो", "{f} को अपडेट करो"],
        "gu": ["{f} માં એક લીટી ઉમેરો", "{f} માં નવું લખાણ લખો", "{f} અપડેટ કરો"],
        "hinglish": ["{f} mein ek line add karo", "{f} mein naya text likho", "{f} update karo"],
        "gujlish": ["{f} ma ek line umero", "{f} ma navu text lakho", "{f} ma update karo"]},
    "file_delete": {
        "en": ["delete {f}", "remove the file {f}", "erase {f}", "get rid of {f}"],
        "hi": ["{f} हटाओ", "फाइल {f} डिलीट करो", "{f} मिटा दो"],
        "gu": ["{f} કાઢી નાખો", "ફાઇલ {f} ડિલીટ કરો", "{f} ભૂંસી નાખો"],
        "hinglish": ["{f} delete karo", "file {f} hata do", "{f} mita do"],
        "gujlish": ["{f} ne delete karo", "file {f} kadhi nakho", "{f} bhusi nakho"]},
    "file_search": {
        "en": ["search for {f}", "find the file {f}", "where is {f}", "look for files named {f}"],
        "hi": ["{f} खोजो", "फाइल {f} कहाँ है", "{f} नाम की फाइलें ढूंढो"],
        "gu": ["{f} શોધો", "ફાઇલ {f} ક્યાં છે", "{f} નામની ફાઇલો શોધો"],
        "hinglish": ["{f} search karo", "file {f} kahan hai", "{f} naam ki files dhundo"],
        "gujlish": ["{f} ne search karo", "file {f} kya che", "{f} naam ni files shodho"]},
    "office_create": {
        "en": ["create an excel sheet named {o}", "make a word document called {o}", "generate a spreadsheet {o}",
               "write a new word file {o}", "open excel and write 5 names in 5 rows"],
        "hi": ["{o} नाम की एक्सेल शीट बनाओ", "{o} नाम का वर्ड डॉक्यूमेंट बनाओ", "{o} स्प्रेडशीट तैयार करो",
               "एक्सेल खोलो और 5 पंक्तियों में 5 नाम लिखो"],
        "gu": ["{o} નામની એક્સેલ શીટ બનાવો", "{o} નામનો વર્ડ દસ્તાવેજ બનાવો", "{o} સ્પ્રેડશીટ તૈયાર કરો",
               "એક્સેલ ખોલો અને 5 હરોળમાં 5 નામ લખો"],
        "hinglish": ["{o} naam ki excel sheet banao", "{o} naam ka word document banao",
                     "{o} spreadsheet taiyar karo", "excel kholo aur 5 rows mein 5 naam likho"],
        "gujlish": ["{o} naam ni excel sheet banavo", "{o} naam no word document banavo",
                    "{o} spreadsheet taiyar karo", "excel kholo ane 5 rows ma 5 naam lakho"]},
    "app_open": {
        "en": ["open {a}", "launch {a}", "start {a}", "run {a} for me"],
        "hi": ["{a} खोलो", "{a} चालू करो", "{a} शुरू करो"],
        "gu": ["{a} ખોલો", "{a} ચાલુ કરો", "{a} શરૂ કરો"],
        "hinglish": ["{a} kholo", "{a} chalu karo", "{a} start karo"],
        "gujlish": ["{a} kholi do", "{a} chalu kari do", "{a} sharu karo"]},
    "app_close": {
        "en": ["close {a}", "quit {a}", "stop {a}", "shut down {a}"],
        "hi": ["{a} बंद करो", "{a} से बाहर निकलो", "{a} रोक दो"],
        "gu": ["{a} બંધ કરો", "{a} માંથી બહાર નીકળો", "{a} રોકી દો"],
        "hinglish": ["{a} band karo", "{a} se bahar niklo", "{a} ruk do"],
        "gujlish": ["{a} bandh karo", "{a} mathi bahar niklo", "{a} roki do"]},
    "system_status": {
        "en": ["show system status", "how is my cpu usage", "check ram and disk", "system health report",
               "how much memory is free", "what is the cpu load"],
        "hi": ["सिस्टम की स्थिति दिखाओ", "सीपीयू उपयोग कितना है", "रैम और डिस्क जांचो", "सिस्टम हेल्थ रिपोर्ट",
               "कितनी मेमोरी खाली है", "सीपीयू लोड कितना है"],
        "gu": ["સિસ્ટમની સ્થિતિ બતાવો", "સીપીયુ વપરાશ કેટલો છે", "રેમ અને ડિસ્ક તપાસો", "સિસ્ટમ હેલ્થ રિપોર્ટ",
               "કેટલી મેમરી ખાલી છે", "સીપીયુ લોડ કેટલો છે"],
        "hinglish": ["system status dikhao", "cpu usage kitna hai", "ram aur disk check karo",
                     "system health report do", "kitni memory khaali hai", "cpu load kitna hai"],
        "gujlish": ["system status batavo", "cpu usage ketlo che", "ram ane disk check karo",
                    "system health report apo", "ketli memory khali che", "cpu load ketlo che"]},
    "doc_question": {
        "en": ["what does the document say about {d}", "according to my pdf, what is {d}",
               "search my documents for {d}"],
        "hi": ["दस्तावेज़ में {d} के बारे में क्या लिखा है", "मेरी पीडीएफ के अनुसार {d} क्या है",
               "मेरे दस्तावेज़ों में {d} खोजो"],
        "gu": ["દસ્તાવેજમાં {d} વિશે શું લખ્યું છે", "મારી પીડીએફ મુજબ {d} શું છે",
               "મારા દસ્તાવેજોમાં {d} શોધો"],
        "hinglish": ["document mein {d} ke baare mein kya likha hai", "meri pdf ke according {d} kya hai",
                     "mere documents mein {d} search karo"],
        "gujlish": ["document ma {d} vishe shu lakhyu che", "mari pdf mujab {d} shu che",
                    "mara documents ma {d} shodho"]},
    "knowledge_question": {
        "en": ["{q}", "{q} please", "quick question: {q}"],
        "hi": ["{q}", "{q} कृपया", "एक सवाल: {q}"],
        "gu": ["{q}", "{q} કૃપા કરીને", "એક સવાલ: {q}"],
        "hinglish": ["{q}", "{q} please", "ek sawal: {q}"],
        "gujlish": ["{q}", "{q} please", "ek sawal: {q}"]},
    "help": {
        "en": ["help", "what can you do", "show me the commands", "how do i use you", "list your features",
               "i need help"],
        "hi": ["मदद", "तुम क्या कर सकते हो", "कमांड दिखाओ", "तुम्हें कैसे इस्तेमाल करूँ", "अपनी सुविधाएँ बताओ",
               "मुझे मदद चाहिए"],
        "gu": ["મદદ", "તું શું કરી શકે", "આદેશો બતાવો", "તને કેવી રીતે વાપરું", "તારી સુવિધાઓ કહો",
               "મને મદદ જોઈએ"],
        "hinglish": ["madad", "tum kya kar sakte ho", "commands dikhao", "tumhe kaise use karun",
                     "apne features batao", "mujhe help chahiye"],
        "gujlish": ["madad karo", "tame shu kari shako", "commands batavo", "tamne kevi rite vaparu",
                    "tamara features kaho", "mane help joiye"]},
    "unknown": {
        "en": ["hmm", "ok then", "blah blah", "qwerty", "umm", "lol", "random words here", "asdfgh"],
        "hi": ["हम्म", "ठीक है", "अरे यार", "कुछ नहीं", "पता नहीं", "बस ऐसे ही", "ऊं ऊं", "छोड़ो"],
        "gu": ["હમ્મ", "બરાબર", "અરે યાર", "કંઈ નહીં", "ખબર નથી", "બસ એમ જ", "ઊં ઊં", "છોડો"],
        "hinglish": ["hmm theek hai", "arre yaar", "kuch nahi", "pata nahi", "bas aise hi", "oho", "chalo ji",
                     "kuch bhi"],
        "gujlish": ["hmm barabar", "are yaar", "kai nahi", "khabar nathi", "bas em j", "are wah", "chalo ne",
                    "kai pan"]},
}

# Held-out code-mixed test phrasings (different wording from TEMPLATES; never used for training).
_TQ = {"hinglish": ["moon kitni door hai", "python kya hota hai", "gold ka rate kyun badhta hai",
                    "internet kaise chalta hai"],
       "gujlish": ["moon ketlo dur che", "python shu hoy che", "gold no bhav kem vadhe che",
                   "internet kevi rite chale che"]}
TEST_TEMPLATES: dict[str, dict[str, list[str]]] = {
    "greet": {"hinglish": ["hey assistant kya haal chaal", "oye hello", "yo bhai kya chal raha hai", "good morning yaar"],
              "gujlish": ["are hello bhai", "kem chho assistant", "oye su thyu", "good evening dost"]},
    "set_identity": {"hinglish": ["bas itna jaan lo ki mera naam {n} hai", "aap mujhe {n} naam se pukaro"],
                     "gujlish": ["bas etlu jani lo ke maru naam {n} che", "tame mane {n} kahine bolavjo"]},
    "get_identity": {"hinglish": ["batao na mera naam kya tha", "tumhe yaad hai main kaun hoon", "zara bolo mera naam",
                                  "mera naam yaad hai kya"],
                     "gujlish": ["kaho ne maru naam shu hatu", "tamne khabar che hu kon chu", "jara bolo maru naam",
                                 "maru naam yaad che ke nahi"]},
    "memory_save": {"hinglish": ["ek baat note kar lo {x}", "dhyan rakhna ki {x}"],
                    "gujlish": ["ek vaat note kari lo {x}", "dhyan rakhjo ke {x}"]},
    "memory_recall": {"hinglish": ["yaad hai mera {t} kya tha", "zara batao mera {t}"],
                      "gujlish": ["yaad che maro {t} shu hato", "jara kaho maro {t}"]},
    "file_create": {"hinglish": ["ek nayi file {f} bana do", "{f} naam se file create kar dena"],
                    "gujlish": ["ek navi file {f} bani do", "{f} naam thi file create kari dejo"]},
    "file_read": {"hinglish": ["zara {f} ka content dikha do", "{f} khol ke padh do"],
                  "gujlish": ["jara {f} nu content batavi do", "{f} kholi ne vanchi apo"]},
    "file_update": {"hinglish": ["{f} ke end mein ek line jod do", "{f} mein kuch aur likh do"],
                    "gujlish": ["{f} na end ma ek line umari do", "{f} ma kai bijun lakhi do"]},
    "file_delete": {"hinglish": ["{f} ko hamesha ke liye hata do", "bekaar file {f} delete maar do"],
                    "gujlish": ["{f} ne kadhi nakho ne", "bekar file {f} delete kari do"]},
    "file_search": {"hinglish": ["{f} kis folder mein padi hai dhundo", "zara dekho {f} kahan hai"],
                    "gujlish": ["{f} kai folder ma padi che shodho", "jara juo {f} kya che"]},
    "office_create": {"hinglish": ["excel mein {o} naam se ek sheet bana do", "word mein {o} document tayar karo"],
                      "gujlish": ["excel ma {o} naam thi ek sheet bani do", "word ma {o} document tayar karo"]},
    "app_open": {"hinglish": ["zara {a} chala do", "{a} on kar do"],
                 "gujlish": ["jara {a} chalu kari do", "{a} on kari do"]},
    "app_close": {"hinglish": ["{a} ko off kar do", "{a} ki zarurat nahi ab band kar do"],
                  "gujlish": ["{a} ne off kari do", "{a} ni jarur nathi have bandh kari do"]},
    "system_status": {"hinglish": ["laptop ki speed kaisi chal rahi hai cpu ram dikhao", "check karo system slow to nahi",
                                   "kitna storage bacha hai", "processor ka load batao"],
                      "gujlish": ["laptop ni speed kevi che cpu ram batavo", "check karo system slow to nathi",
                                  "ketlu storage baki che", "processor no load batavo"]},
    "help": {"hinglish": ["bhai tum kya kya kar lete ho", "mujhe samajh nahi aa raha kaise use karun",
                          "kuch commands bata do", "madad kar do yaar"],
             "gujlish": ["bhai tame shu shu kari lo cho", "mane samajtu nathi kevi rite vaparvu",
                         "kai commands kaho", "madad kari do yaar"]},
    "doc_question": {"hinglish": ["meri file ke document mein {d} kya bola hai", "pdf se batao {d}"],
                     "gujlish": ["mara document ma {d} shu kahyu che", "pdf mathi kaho {d}"]},
    "knowledge_question": {"hinglish": ["yaar ye batao {q}", "{q} zara samjha do"],
                           "gujlish": ["yaar aa kaho {q}", "{q} jara samjavi do"]},
    "unknown": {"hinglish": ["hmm pata nahi yaar", "kuch bhi bol raha hu", "qazwsx edcrfv", "arre chhodo na"],
                "gujlish": ["hmm khabar nathi yaar", "kai pan bolu chu", "zxcv bnm", "are chhodo ne"]},
}


def script_of(text: str) -> str:
    if re.search(r"[\u0900-\u097F]", text):
        return "devanagari"
    if re.search(r"[\u0A80-\u0AFF]", text):
        return "gujarati"
    return "latin"


def _slots(t: str) -> list[str]:
    return re.findall(r"\{(\w)\}", t)


def _candidates(template: str, lang: str, pools: dict[str, list[str]], wrap: bool) -> list[str]:
    keys = _slots(template)
    pres, sufs = (PRE[lang], SUF[lang]) if wrap else ([""], [""])
    out = []
    for combo in product(*[pools[k] for k in keys]):
        body = template.format(**dict(zip(keys, combo)))
        out += [f"{p}{body}{s}".strip() for p in pres for s in sufs]
    return out


def generate(seed: int = 42, per_cell: int = 14) -> tuple[list[dict], list[dict]]:
    rng = random.Random(seed)
    seen: set[str] = set()
    train: list[dict] = []

    def add(rows: list[dict], text: str, intent: str, lang: str) -> bool:
        key = text.lower().strip()
        if not key or key in seen:
            return False
        seen.add(key)
        rows.append({"text": text, "intent": intent, "language": lang, "script": script_of(text),
                     "source": "generated", "reviewed": "false"})
        return True

    for intent in INTENTS:
        for lang in LANGS:
            wrap = intent not in ("greet", "unknown")
            lists = []
            for tpl in TEMPLATES[intent][lang]:
                c = list(dict.fromkeys(_candidates(tpl, lang, POOLS[lang], wrap)))
                rng.shuffle(c)
                lists.append(c)
            taken = 0
            while taken < per_cell and any(lists):
                for c in lists:
                    if c and taken < per_cell:
                        text = c.pop()
                        if lang in ("en", "hinglish", "gujlish") and rng.random() < 0.4:
                            text = text.lower()
                        taken += add(train, text, intent, lang)
    test: list[dict] = []
    for intent in INTENTS:
        for lang in ("hinglish", "gujlish"):
            pools = dict(POOLS[lang])
            pools["q"] = _TQ[lang]
            for tpl in TEST_TEMPLATES[intent][lang]:
                if _slots(tpl):
                    for text in rng.sample(_candidates(tpl, lang, pools, False), 2):
                        add(test, text, intent, lang)
                else:
                    add(test, tpl, intent, lang)
    return train, test


def write_csv(rows: list[dict], path: Path) -> None:
    import pandas as pd

    pd.DataFrame(rows, columns=COLUMNS).to_csv(path, index=False, encoding="utf-8")


def load(path: Path | str = TRAIN_CSV):
    import pandas as pd

    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")


def dataset_hash(path: Path | str = TRAIN_CSV) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def split(df, seed: int = 42):
    """Stratified 70/15/15 split on intent with a fixed seed."""
    from sklearn.model_selection import train_test_split

    train, rest = train_test_split(df, test_size=0.30, stratify=df["intent"], random_state=seed)
    val, test = train_test_split(rest, test_size=0.50, stratify=rest["intent"], random_state=seed)
    return train.reset_index(drop=True), val.reset_index(drop=True), test.reset_index(drop=True)


_SCRIPT_FOR_LANG = {"hi": "devanagari", "gu": "gujarati", "en": "latin", "hinglish": "latin", "gujlish": "latin"}


def validate(train_path: Path | str = TRAIN_CSV, test_path: Path | str = TEST_CSV) -> list[str]:
    """Return a list of problems; an empty list means the dataset is valid."""
    errors: list[str] = []
    frames = {}
    for label, path in (("train", train_path), ("test", test_path)):
        if not Path(path).exists():
            errors.append(f"{label}: file missing: {path}")
            continue
        df = load(path)
        missing = [c for c in COLUMNS if c not in df.columns]
        if missing:
            errors.append(f"{label}: missing columns {missing}")
            continue
        frames[label] = df
        bad = df[~df["intent"].isin(INTENTS)]
        if len(bad):
            errors.append(f"{label}: {len(bad)} rows with unknown intent, e.g. {bad.iloc[0]['intent']!r}")
        for col, allowed in (("language", LANGS), ("script", SCRIPTS), ("source", SOURCES), ("reviewed", ["true", "false"])):
            n = int((~df[col].isin(allowed)).sum())
            if n:
                errors.append(f"{label}: {n} rows with invalid {col}")
        if (df["text"].str.strip() == "").any():
            errors.append(f"{label}: empty text")
        dups = int(df["text"].str.lower().str.strip().duplicated().sum())
        if dups:
            errors.append(f"{label}: {dups} exact duplicate texts")
        wrong = df[df.apply(lambda r: script_of(r["text"]) != r["script"] or _SCRIPT_FOR_LANG.get(r["language"]) != r["script"], axis=1)]
        if len(wrong):
            errors.append(f"{label}: {len(wrong)} rows with script inconsistent with text or language")
    if "train" in frames:
        df = frames["train"]
        if len(df) < MIN_TOTAL:
            errors.append(f"train: only {len(df)} rows, need {MIN_TOTAL}")
        for intent, n in df["intent"].value_counts().items():
            if n < MIN_PER_INTENT:
                errors.append(f"train: intent {intent} has {n} rows, need {MIN_PER_INTENT}")
        for intent in INTENTS:
            if intent not in set(df["intent"]):
                errors.append(f"train: intent {intent} has no rows")
        for lang in LANGS:
            share = (df["language"] == lang).mean()
            if share < MIN_LANG_SHARE:
                errors.append(f"train: language {lang} share {share:.2%} below {MIN_LANG_SHARE:.0%}")
    if "test" in frames and len(frames["test"]) < MIN_CODEMIXED:
        errors.append(f"test: only {len(frames['test'])} rows, need {MIN_CODEMIXED}")
    if len(frames) == 2:
        overlap = set(frames["train"]["text"].str.lower()) & set(frames["test"]["text"].str.lower())
        if overlap:
            errors.append(f"test: {len(overlap)} texts also present in the training file")
        if not set(frames["test"]["language"]) <= {"hinglish", "gujlish"}:
            errors.append("test: contains languages other than hinglish and gujlish")
    return errors


def add_example(text: str, intent: str, language: str, source: str = "author", path=None, test_path=None):
    """Append an author-provided or corrected example. Returns (ok, message)."""
    text = " ".join(text.split())
    if not text or len(text) > 300:
        return False, "Enter text of 1 to 300 characters."
    if intent not in INTENTS or language not in LANGS or source not in ("author", "corrected"):
        return False, "Invalid intent, language or source."
    script = script_of(text)
    if _SCRIPT_FOR_LANG[language] != script:
        return False, f"The text is in {script} script, which does not match language {language}."
    path, test_path = path or TRAIN_CSV, test_path or TEST_CSV
    df = load(path)
    key = text.lower()
    if key in set(df["text"].str.lower()) or key in set(load(test_path)["text"].str.lower()):
        return False, "This text already exists in the dataset."
    row = {"text": text, "intent": intent, "language": language, "script": script, "source": source, "reviewed": "true"}
    write_csv(df.to_dict("records") + [row], path)
    return True, "Example added. Retrain to use it."


def balance_report(path: Path | str = TRAIN_CSV) -> str:
    df = load(path)
    lines = [f"rows: {len(df)}", "by intent: " + ", ".join(f"{k}={v}" for k, v in df["intent"].value_counts().sort_index().items()),
             "by language: " + ", ".join(f"{k}={v}" for k, v in df["language"].value_counts().items()),
             "reviewed: " + ", ".join(f"{k}={v}" for k, v in df["reviewed"].value_counts().items())]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Extra paraphrases (synonyms, fillers, spoken style) appended by `augment`.
# They never replace existing rows, so author and corrected examples are kept.
# ---------------------------------------------------------------------------
EXTRA_TEMPLATES: dict[str, dict[str, list[str]]] = {
    "app_open": {
        "en": ["fire up {a}", "bring up {a}", "can you open {a}", "i need {a}", "get {a} running", "load {a}"],
        "hinglish": ["{a} on karo", "zara {a} khol do", "{a} chalu kar do", "mujhe {a} chahiye"],
        "gujlish": ["{a} on karo", "jara {a} kholi do", "mane {a} joiye che", "{a} chalu karjo"],
        "hi": ["{a} को खोलिए", "ज़रा {a} चालू कर दो"], "gu": ["{a} ખોલી આપો", "જરા {a} ચાલુ કરી દો"]},
    "app_close": {
        "en": ["kill {a}", "exit {a}", "terminate {a}", "i am done with {a}", "turn off {a}", "close down {a}"],
        "hinglish": ["{a} band kar do", "{a} off karo", "{a} ko hata do screen se", "{a} ka kaam khatam, band karo"],
        "gujlish": ["{a} bandh kari do", "{a} off karo", "{a} nu kam puru, bandh karo", "{a} bandh karjo"],
        "hi": ["{a} को बंद कर दो", "{a} बंद कर दीजिए"], "gu": ["{a} બંધ કરી દો", "{a} બંધ કરજો"]},
    "screenshot": {
        "en": ["grab a screenshot", "capture my screen", "snap the screen", "take a screen capture",
               "screenshot please", "save what is on my screen as an image"],
        "hinglish": ["screenshot lo", "screen ka photo le lo", "screenshot le lo yaar", "screen capture karo"],
        "gujlish": ["screenshot lo", "screen no photo lai lo", "screenshot kari lo", "screen capture karo"],
        "hi": ["स्क्रीनशॉट लो", "स्क्रीन की फोटो ले लो", "स्क्रीन कैप्चर करो"],
        "gu": ["સ્ક્રીનશોટ લો", "સ્ક્રીનનો ફોટો લઈ લો", "સ્ક્રીન કેપ્ચર કરો"]},
    "system_status": {
        "en": ["is my laptop slow", "how is my pc doing", "how much storage is left", "check battery and cpu",
               "what is eating my ram", "give me a performance summary"],
        "hinglish": ["laptop slow kyun hai check karo", "pc ki health dikhao", "kitna storage bacha hai",
                     "cpu aur ram ka status batao"],
        "gujlish": ["laptop slow kem che check karo", "pc ni health batavo", "ketlu storage baki che",
                    "cpu ane ram nu status kaho"],
        "hi": ["लैपटॉप धीमा क्यों है जांचो", "पीसी की सेहत दिखाओ"], "gu": ["લેપટોપ ધીમું કેમ છે તપાસો", "પીસીની હેલ્થ બતાવો"]},
    "time_date": {
        "en": ["what time is it", "what is today's date", "tell me the time", "what day is it today",
               "current time please", "date today"],
        "hinglish": ["kitne baje hain", "aaj ki date kya hai", "time kya hua hai", "aaj kaun sa din hai"],
        "gujlish": ["ketla vagya", "aajni date shu che", "time shu thayo", "aaje kyo divas che"],
        "hi": ["अभी कितने बजे हैं", "आज की तारीख क्या है", "समय बताओ"],
        "gu": ["અત્યારે કેટલા વાગ્યા છે", "આજની તારીખ શું છે", "સમય કહો"]},
    "memory_save": {
        "en": ["keep in mind that {x}", "note that {x}", "please remember {x}", "don't forget {x}"],
        "hinglish": ["yaad rakho {x}", "ye note kar lo {x}", "bhulna mat {x}"],
        "gujlish": ["yaad rakho {x}", "aa note kari lo {x}", "bhulta nahi {x}"],
        "hi": ["यह याद रखना {x}", "भूलना मत {x}"], "gu": ["આ યાદ રાખજો {x}", "ભૂલતા નહીં {x}"]},
    "memory_recall": {
        "en": ["what did i tell you about my {t}", "remind me of my {t}", "recall my {t}"],
        "hinglish": ["maine apne {t} ke baare mein kya bataya tha", "mere {t} ki yaad dilao"],
        "gujlish": ["me mara {t} vishe shu kahyu hatu", "mara {t} ni yaad apavo"],
        "hi": ["मैंने अपने {t} के बारे में क्या बताया था"], "gu": ["મેં મારા {t} વિશે શું કહ્યું હતું"]},
    "file_create": {
        "en": ["make a file called {f}", "touch {f}", "i need a new file {f}", "start a new file {f}"],
        "hinglish": ["ek nayi file {f} bana do", "{f} naam ki file taiyar karo"],
        "gujlish": ["ek navi file {f} bani do", "{f} naam ni file taiyar karo"],
        "hi": ["{f} नाम की नई फाइल तैयार करो"], "gu": ["{f} નામની નવી ફાઇલ તૈયાર કરો"]},
    "file_read": {
        "en": ["show me {f}", "view {f}", "cat {f}", "print the contents of {f}", "let me see {f}"],
        "hinglish": ["{f} dikha do", "{f} mein kya likha hai dikhao"],
        "gujlish": ["{f} batavi do", "{f} ma shu lakhyu che te batavo"],
        "hi": ["{f} दिखा दो", "{f} में क्या लिखा है"], "gu": ["{f} બતાવી દો", "{f} માં શું લખ્યું છે"]},
    "file_delete": {
        "en": ["trash {f}", "wipe {f}", "i don't need {f} anymore, delete it", "remove {f} permanently"],
        "hinglish": ["{f} ko trash karo", "{f} ki ab zarurat nahi, delete karo"],
        "gujlish": ["{f} ne trash karo", "{f} ni have jarur nathi, delete karo"],
        "hi": ["{f} को ट्रैश करो", "{f} अब नहीं चाहिए, हटा दो"], "gu": ["{f} ને ટ્રેશ કરો", "{f} હવે નથી જોઈતી, કાઢી નાખો"]},
    "file_search": {
        "en": ["locate {f}", "find {f} on my computer", "do i have a file called {f}", "look up {f}"],
        "hinglish": ["{f} kahan rakhi hai", "mere computer mein {f} dhundo"],
        "gujlish": ["{f} kya rakhi che", "mara computer ma {f} shodho"],
        "hi": ["{f} कहाँ रखी है", "मेरे कंप्यूटर में {f} ढूंढो"], "gu": ["{f} ક્યાં મૂકી છે", "મારા કમ્પ્યુટરમાં {f} શોધો"]},
    "knowledge_question": {
        "en": ["explain {q}", "i am curious: {q}", "can you tell me, {q}", "help me understand: {q}"],
        "hinglish": ["batao {q}", "ek cheez samjhao, {q}"], "gujlish": ["kaho {q}", "ek vaat samjavo, {q}"],
        "hi": ["बताइए, {q}", "समझाइए, {q}"], "gu": ["કહો, {q}", "સમજાવો, {q}"]},
    "help": {
        "en": ["what are you capable of", "what commands do you support", "how does this assistant work"],
        "hinglish": ["tum kya kya kar sakte ho", "ye assistant kaise kaam karta hai"],
        "gujlish": ["tame shu shu kari shako", "aa assistant kevi rite kaam kare"],
        "hi": ["तुम क्या क्या कर सकते हो"], "gu": ["તું શું શું કરી શકે"]},
}


def augment(path: Path | str = TRAIN_CSV, test_path: Path | str = TEST_CSV, seed: int = 7,
            per_template: int = 6) -> int:
    """Append EXTRA_TEMPLATES rows to the training CSV. Existing rows are kept; duplicates and
    anything already in the test file are skipped. Returns the number of rows added."""
    rng = random.Random(seed)
    df = load(path)
    seen = set(df["text"].str.lower().str.strip()) | set(load(test_path)["text"].str.lower().str.strip())
    rows = df.to_dict("records")
    added = 0
    for intent, by_lang in EXTRA_TEMPLATES.items():
        for lang, templates in by_lang.items():
            for tpl in templates:
                cands = list(dict.fromkeys(_candidates(tpl, lang, POOLS[lang], False)))
                rng.shuffle(cands)
                for text in cands[:per_template]:
                    key = text.lower().strip()
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append({"text": text, "intent": intent, "language": lang, "script": script_of(text),
                                 "source": "generated", "reviewed": "false"})
                    added += 1
    write_csv(rows, path)
    return added


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else ""
    if cmd == "generate":
        train, test = generate()
        write_csv(train, TRAIN_CSV)
        write_csv(test, TEST_CSV)
        print(f"wrote {len(train)} training rows and {len(test)} code-mixed test rows")
        return 0
    if cmd == "augment":
        print(f"added {augment()} rows")
        return 0
    if cmd == "validate":
        errs = validate()
        print("\n".join(errs) if errs else "dataset valid")
        return 1 if errs else 0
    if cmd == "report":
        print(balance_report())
        return 0
    print("Usage: python -m adhyaksh.nlu.dataset generate|augment|validate|report")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
