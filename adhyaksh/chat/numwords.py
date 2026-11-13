"""Number words to digits for spoken arithmetic: English, Hindi (Devanagari and Roman) and Gujarati (script and Roman).

Covers 0 to 100 as single words, English compounds ("twenty five"), and "N hundred". Hindi and Gujarati numbers
21 to 99 are irregular, so only the common words listed below are understood; unknown words are left alone."""
from __future__ import annotations

import re

_EN = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen "
    "eighteen nineteen twenty".split())}
_EN.update({"thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90})

_HI_ROMAN = {
    "shunya": 0, "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "pach": 5, "chhe": 6, "chhah": 6,
    "chhai": 6, "saat": 7, "sat": 7, "aath": 8, "ath": 8, "nau": 9, "das": 10, "gyarah": 11, "barah": 12, "terah": 13,
    "chaudah": 14, "pandrah": 15, "solah": 16, "satrah": 17, "atharah": 18, "unnis": 19, "bees": 20, "tees": 30,
    "chalis": 40, "pachas": 50, "saath": 60, "sattar": 70, "assi": 80, "nabbe": 90, "sau": 100}
_HI_DEV = {
    "शून्य": 0, "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "छः": 6, "छे": 6, "सात": 7, "आठ": 8,
    "नौ": 9, "दस": 10, "ग्यारह": 11, "बारह": 12, "तेरह": 13, "चौदह": 14, "पंद्रह": 15, "पन्द्रह": 15, "सोलह": 16,
    "सत्रह": 17, "अठारह": 18, "उन्नीस": 19, "बीस": 20, "तीस": 30, "चालीस": 40, "पचास": 50, "साठ": 60, "सत्तर": 70,
    "अस्सी": 80, "नब्बे": 90, "सौ": 100}
_GU_ROMAN = {
    "ek": 1, "be": 2, "bey": 2, "tran": 3, "char": 4, "panch": 5, "paanch": 5, "chha": 6, "chh": 6, "saat": 7,
    "aath": 8, "nav": 9, "das": 10, "agiyar": 11, "bar": 12, "ter": 13, "chaud": 14, "pandar": 15, "sol": 16,
    "sattar": 17, "adhar": 18, "ogniss": 19, "vis": 20, "trees": 30, "chalis": 40, "pachas": 50, "saith": 60,
    "sitter": 70, "ensi": 80, "nevu": 90, "so": 100}
_GU = {
    "એક": 1, "બે": 2, "ત્રણ": 3, "ચાર": 4, "પાંચ": 5, "છ": 6, "સાત": 7, "આઠ": 8, "નવ": 9, "દસ": 10, "અગિયાર": 11,
    "બાર": 12, "તેર": 13, "ચૌદ": 14, "પંદર": 15, "સોળ": 16, "સત્તર": 17, "અઢાર": 18, "ઓગણીસ": 19, "વીસ": 20,
    "ત્રીસ": 30, "ચાલીસ": 40, "પચાસ": 50, "સાઠ": 60, "સિત્તેર": 70, "એંસી": 80, "નેવું": 90, "સો": 100}

# Words that are also ordinary words in a command ("do" = "please do", "so", "be") are only numbers next to an operator.
_AMBIGUOUS = {"do", "be", "so", "bey", "sat", "ath", "pach", "sau", "bar", "ter", "sol", "ek"}
_OPERATORS = r"(?:plus|minus|times|into|divided|multiplied|power|mod|jama|jod|ghata|gunaa?|bhaag?|\+|-|\*|/|x|गुणा|गुना|भाग|प्लस|माइनस|" \
             r"ગુણા|ગુણાકાર|ભાગ|પ્લસ|માઇનસ)"
_TABLE = {**_EN, **_HI_ROMAN, **_HI_DEV, **_GU_ROMAN, **_GU}


def _value(tok: str) -> int | None:
    return _TABLE.get(tok)


def normalize(text: str) -> str:
    """Replace number words with digits. 'twenty five plus paanch' -> '25 plus 5'."""
    toks = re.findall(r"[\wऀ-ॿ઀-૿.]+|[+\-*/()%^]", text.casefold())
    if not any(re.fullmatch(_OPERATORS, t) for t in toks):
        return text
    out: list[str] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        v = _value(t)
        ambiguous = t in _AMBIGUOUS
        near_op = any(re.fullmatch(_OPERATORS, toks[k]) for k in (i - 1, i + 1) if 0 <= k < len(toks))
        near_num = any(k < len(toks) and (toks[k].isdigit() or _value(toks[k]) is not None)
                       for k in (i - 1, i + 1) if k >= 0)
        if v is None or (ambiguous and not (near_op or near_num)):
            out.append(t)
            i += 1
            continue
        # English compounds: "twenty five", and "N hundred".
        if v >= 20 and v % 10 == 0 and v < 100 and i + 1 < len(toks) and toks[i + 1] in _EN and 1 <= _EN[toks[i + 1]] <= 9:
            v += _EN[toks[i + 1]]
            i += 1
        if i + 1 < len(toks) and toks[i + 1] in ("hundred", "sau", "सौ", "સો") and v < 10:
            v *= 100
            i += 1
        out.append(str(v))
        i += 1
    return " ".join(out)
