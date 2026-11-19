"""Personal memory: structured facts in SQLite.

A fact is (subject, attribute, value) plus the sentence it came from: "my locker code is 4417" is
("user", "locker code", "4417"). Saving the same subject and attribute again UPDATES the fact, so the memory never
holds two contradicting answers. Recall looks for the asked attribute first, then for a similar fact (the local
embedding model when it is installed, else shared words). Forgetting goes through the safety gateway (L2: the user
confirms). Sentences that are not of the form "my X is Y" are kept as free text, as before.
"""
from __future__ import annotations

import re

from adhyaksh import db, responses
from adhyaksh.memory import facts
from adhyaksh.result import E_ACTION_FAILED, E_FILE_NOT_FOUND, Result

PREFIXES = [r"remember that", r"remember", r"note down that", r"note that", r"save this:?", r"yaad rakhna ki",
            r"yaad rakhjo ke", r"note kar lo ki", r"note kari lo ke", r"save karo:?", r"याद रखो कि",
            r"यह नोट करो कि", r"सहेज लो:?", r"યાદ રાખો કે", r"નોંધ કરો કે", r"સાચવો:?", r"ek baat note kar lo",
            r"dhyan rakhna ki", r"dhyan rakhjo ke", r"ek vaat note kari lo", r"(?:don'?t|do not|never) forget(?: that)?"]
_STOP = set("""what is my the a an tell me do you remember who which where when kya hai hain mera meri mere mujhe
batao bata tum tumhe yaad maro mari maru shu che mane kaho tane tamne zara batavo kaun tha thi hato hati
मेरा मेरी मेरे क्या है मुझे बताओ तुम्हें याद मारो મારો મારી મારું શું છે મને કહો""".split())
_SKIP_WORDS = {"hai", "che", "is", "are", "ka", "ki", "ke", "है", "છે"}
SEMANTIC_MIN = 0.55  # cosine similarity a recalled fact needs when the embedding model is used


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.casefold()).split())


def clean_fact(text: str) -> str:
    t = text.strip()
    for p in PREFIXES:
        t = re.sub(rf"^\s*{p}\s*", "", t, flags=re.IGNORECASE)
    return t.strip().rstrip(".!?। ")


def _category(fact: str) -> str:
    return "personal" if re.match(r"^(my|meri|mera|mere|mari|maro|maru|मेरा|मेरी|મારો|મારી|મારું)\b", fact, re.I) else "general"


def _backfill() -> None:
    """Give rows saved before structured memory their subject, attribute and value (once per row)."""
    for row in db.query_all("SELECT id, fact FROM memory_facts WHERE parsed=0"):
        f = facts.parse_statement(row["fact"])
        if f:
            db.execute("UPDATE memory_facts SET subject=?, attribute=?, value=?, parsed=1 WHERE id=?",
                       (f.subject, f.attribute, f.value, row["id"]))
        else:
            db.execute("UPDATE memory_facts SET parsed=1 WHERE id=?", (row["id"],))


def save_fact(text: str, source: str = "user", confidence: float = 1.0) -> Result:
    """Store a fact. Data: id, fact, duplicate (same sentence already stored), updated (same attribute, new value),
    previous (the old sentence when updated), attribute and value (when structured)."""
    _backfill()
    fact = clean_fact(text)
    if not fact:
        return Result.failure(E_ACTION_FAILED, "There is nothing to store.")
    for row in db.query_all("SELECT id, fact FROM memory_facts"):
        if _norm(row["fact"]) == _norm(fact):
            return Result.success({"id": row["id"], "fact": row["fact"], "duplicate": True, "updated": False})
    parsed = facts.parse_statement(fact)
    now = db.utcnow()
    if parsed:
        old = db.query_one("SELECT id, fact, source FROM memory_facts WHERE subject=? AND attribute=? ORDER BY id DESC LIMIT 1",
                           (parsed.subject, parsed.attribute))
        if old and not (source == "auto" and old["source"] == "user"):  # an automatic guess never overwrites the user
            db.execute("UPDATE memory_facts SET fact=?, category=?, value=?, source=?, confidence=?, updated_at=?, parsed=1 "
                       "WHERE id=?", (fact, _category(fact), parsed.value, source, confidence, now, old["id"]))
            return Result.success({"id": old["id"], "fact": fact, "duplicate": False, "updated": True, "previous": old["fact"],
                                   "attribute": parsed.attribute, "value": parsed.value})
        if old:
            return Result.success({"id": old["id"], "fact": old["fact"], "duplicate": True, "updated": False})
    fid = db.execute(
        "INSERT INTO memory_facts(fact,category,created_at,updated_at,subject,attribute,value,source,confidence,parsed) "
        "VALUES(?,?,?,?,?,?,?,?,?,1)",
        (fact, _category(fact), now, now, parsed.subject if parsed else facts.GENERAL, parsed.attribute if parsed else None,
         parsed.value if parsed else None, source, confidence))
    out = {"id": fid, "fact": fact, "duplicate": False, "updated": False}
    if parsed:
        out.update(attribute=parsed.attribute, value=parsed.value)
    return Result.success(out)


def _tokens(text: str) -> set[str]:
    return {w for w in _norm(text).split() if w not in _STOP and w not in _SKIP_WORDS}


def _speak(fact: str) -> str:
    return re.sub(r"^my\b", "Your", fact, flags=re.I)


def _answer(row: dict, how: str) -> dict:
    return {"id": row["id"], "fact": row["fact"], "answer": _speak(row["fact"]), "attribute": row.get("attribute"),
            "value": row.get("value"), "match": how}


def by_attribute(attribute: str) -> dict | None:
    """The fact stored for this attribute (exact, after normalisation), newest first."""
    if not attribute:
        return None
    return db.query_one("SELECT * FROM memory_facts WHERE attribute=? ORDER BY updated_at DESC, id DESC LIMIT 1",
                        (facts.normalize_attribute(attribute),))


def _semantic_best(query: str, rows: list[dict]) -> dict | None:
    """The most similar fact by the local embedding model (never a cloud model), or None when it is not installed."""
    try:
        from adhyaksh.rag import embedder
        if not rows or not embedder.available():
            return None
        import numpy as np
        vecs = np.asarray(embedder.embed([query] + [r["fact"] for r in rows]), dtype=float)
        vecs /= np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9
        sims = vecs[1:] @ vecs[0]
        i = int(sims.argmax())
        return rows[i] if sims[i] >= SEMANTIC_MIN else None
    except Exception:  # an optional model must never break recall
        return None


def recall(query: str) -> Result:
    """Answer a question about a stored fact: by attribute first, then by similarity, then by shared words."""
    _backfill()
    attr = facts.question_attribute(query)
    hit = by_attribute(attr) if attr else None
    if hit:
        return Result.success(_answer(hit, "attribute"))
    rows = db.query_all("SELECT * FROM memory_facts ORDER BY id DESC")
    sem = _semantic_best(query, rows)
    if sem:
        return Result.success(_answer(sem, "semantic"))
    q = _tokens(query)
    best, best_score = None, 0
    for row in rows:
        score = len(q & _tokens(row["fact"]))
        if score > best_score:
            best, best_score = row, score
    if best is None:
        return Result.failure(E_FILE_NOT_FOUND, responses.t("memory_none"))
    return Result.success(_answer(best, "words"))


def _same(a: str, b: str) -> bool:
    """Token match that tolerates endings: name/named, book/booking."""
    return a == b or (len(a) >= 4 and len(b) >= 4 and (a.startswith(b) or b.startswith(a)))


def best_match(query: str) -> dict | None:
    """The stored fact that clearly answers a question, or None. An asked attribute that is stored always answers;
    otherwise at least two shared content words covering half of the question's content words are needed (or the
    only content word), so unrelated questions are left alone."""
    _backfill()
    attr = facts.question_attribute(query)
    hit = by_attribute(attr) if attr else None
    if hit:
        return {**_answer(hit, "attribute"), "score": 99}
    q = _tokens(query)
    if not q:
        return None
    best, best_score = None, 0
    for row in db.query_all("SELECT id, fact FROM memory_facts ORDER BY id DESC"):
        ft = _tokens(row["fact"])
        score = sum(1 for a in q if any(_same(a, b) for b in ft))
        if score > best_score:
            best, best_score = row, score
    if best is None:
        return None
    if (best_score >= 2 and best_score / len(q) >= 0.5) or (best_score == 1 and len(q) == 1):
        return {"id": best["id"], "fact": best["fact"], "answer": _speak(best["fact"]), "score": best_score}
    return None


def find_for_forget(text: str) -> dict | None:
    """The fact a forget request names: by attribute, else the clear best word match."""
    _backfill()
    attr = facts.forget_attribute(text)
    if not attr:
        return None
    hit = by_attribute(attr)
    if hit:
        return hit
    m = best_match(f"what is my {attr}")
    return db.query_one("SELECT * FROM memory_facts WHERE id=?", (m["id"],)) if m else None


def forget(text: str, *, ctx: dict | None = None) -> Result:
    """Delete the fact a request names ("forget my locker code"). L2: needs the user's confirmation."""
    from adhyaksh.safety import policy
    ctx = ctx or {}
    row = find_for_forget(text)
    if row is None:
        attr = facts.forget_attribute(text) or text
        return Result.failure(E_FILE_NOT_FOUND, f"There is nothing saved about {attr}.")

    def go() -> Result:
        db.execute("DELETE FROM memory_facts WHERE id=?", (row["id"],))
        return Result.success({"id": row["id"], "fact": row["fact"], "attribute": row.get("attribute")})

    return policy.run_guarded("memory_delete", row["fact"], go, user_text=ctx.get("user_text", ""),
                              intent=ctx.get("intent", ""), token=ctx.get("token"))


def list_facts(search: str | None = None) -> list[dict]:
    _backfill()
    rows = db.query_all("SELECT * FROM memory_facts ORDER BY id DESC")
    if search:
        s = search.casefold()
        rows = [r for r in rows if s in r["fact"].casefold() or s in r["category"].casefold()
                or s in (r.get("attribute") or "").casefold()]
    return rows


def update_fact(fact_id: int, text: str) -> Result:
    fact = clean_fact(text)
    if not fact:
        return Result.failure(E_ACTION_FAILED, "The fact cannot be empty.")
    parsed = facts.parse_statement(fact)
    db.execute("UPDATE memory_facts SET fact=?, category=?, updated_at=?, subject=?, attribute=?, value=?, source='user', "
               "confidence=1.0, parsed=1 WHERE id=?",
               (fact, _category(fact), db.utcnow(), parsed.subject if parsed else facts.GENERAL,
                parsed.attribute if parsed else None, parsed.value if parsed else None, fact_id))
    return Result.success({"id": fact_id, "fact": fact})


def delete_fact(fact_id: int) -> Result:
    db.execute("DELETE FROM memory_facts WHERE id=?", (fact_id,))
    return Result.success()


def notice(text: str) -> Result | None:
    """With the auto_memory setting on, keep a personal fact the user states in passing ("my exam is on friday").
    Saved as source 'auto' with lower confidence; it never replaces something the user saved deliberately."""
    from adhyaksh import config
    if not config.get_bool("auto_memory"):
        return None
    parsed = facts.parse_statement(clean_fact(text))
    if parsed is None or len(text) > 200 or "?" in text:
        return None
    return save_fact(text, source="auto", confidence=0.7)
