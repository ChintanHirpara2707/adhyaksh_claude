"""Personal memory: facts stored in SQLite with duplicate detection and keyword recall."""
from __future__ import annotations

import re

from adhyaksh import db, responses
from adhyaksh.result import E_ACTION_FAILED, E_FILE_NOT_FOUND, Result

PREFIXES = [r"remember that", r"remember", r"note down that", r"note that", r"save this:?", r"yaad rakhna ki",
            r"yaad rakhjo ke", r"note kar lo ki", r"note kari lo ke", r"save karo:?", r"याद रखो कि",
            r"यह नोट करो कि", r"सहेज लो:?", r"યાદ રાખો કે", r"નોંધ કરો કે", r"સાચવો:?", r"ek baat note kar lo",
            r"dhyan rakhna ki", r"dhyan rakhjo ke", r"ek vaat note kari lo"]
_STOP = set("""what is my the a an tell me do you remember who which where when kya hai hain mera meri mere mujhe
batao bata tum tumhe yaad maro mari maru shu che mane kaho tane tamne zara batavo kaun tha thi hato hati
मेरा मेरी मेरे क्या है मुझे बताओ तुम्हें याद मारो મારો મારી મારું શું છે મને કહો""".split())
_SKIP_WORDS = {"hai", "che", "is", "are", "ka", "ki", "ke", "है", "છે"}


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.casefold()).split())


def clean_fact(text: str) -> str:
    t = text.strip()
    for p in PREFIXES:
        t = re.sub(rf"^\s*{p}\s*", "", t, flags=re.IGNORECASE)
    return t.strip().rstrip(".!?। ")


def _category(fact: str) -> str:
    return "personal" if re.match(r"^(my|meri|mera|mere|mari|maro|maru|मेरा|मेरी|મારો|મારી|મારું)\b", fact, re.I) else "general"


def save_fact(text: str) -> Result:
    fact = clean_fact(text)
    if not fact:
        return Result.failure(E_ACTION_FAILED, "There is nothing to store.")
    for row in db.query_all("SELECT id, fact FROM memory_facts"):
        if _norm(row["fact"]) == _norm(fact):
            return Result.success({"id": row["id"], "fact": row["fact"], "duplicate": True})
    now = db.utcnow()
    fid = db.execute("INSERT INTO memory_facts(fact,category,created_at,updated_at) VALUES(?,?,?,?)",
                     (fact, _category(fact), now, now))
    return Result.success({"id": fid, "fact": fact, "duplicate": False})


def _tokens(text: str) -> set[str]:
    return {w for w in _norm(text).split() if w not in _STOP and w not in _SKIP_WORDS}


def _speak(fact: str) -> str:
    return re.sub(r"^my\b", "Your", fact, flags=re.I)


def recall(query: str) -> Result:
    q = _tokens(query)
    best, best_score = None, 0
    for row in db.query_all("SELECT id, fact FROM memory_facts ORDER BY id DESC"):
        score = len(q & _tokens(row["fact"]))
        if score > best_score:
            best, best_score = row, score
    if best is None:
        return Result.failure(E_FILE_NOT_FOUND, responses.t("memory_none"))
    return Result.success({"id": best["id"], "fact": best["fact"], "answer": _speak(best["fact"])})


def list_facts(search: str | None = None) -> list[dict]:
    rows = db.query_all("SELECT * FROM memory_facts ORDER BY id DESC")
    if search:
        s = search.casefold()
        rows = [r for r in rows if s in r["fact"].casefold() or s in r["category"].casefold()]
    return rows


def update_fact(fact_id: int, text: str) -> Result:
    fact = clean_fact(text)
    if not fact:
        return Result.failure(E_ACTION_FAILED, "The fact cannot be empty.")
    db.execute("UPDATE memory_facts SET fact=?, category=?, updated_at=? WHERE id=?",
               (fact, _category(fact), db.utcnow(), fact_id))
    return Result.success({"id": fact_id, "fact": fact})


def delete_fact(fact_id: int) -> Result:
    db.execute("DELETE FROM memory_facts WHERE id=?", (fact_id,))
    return Result.success()
