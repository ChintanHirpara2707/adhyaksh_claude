"""TF-IDF features shared by all intent models (word + character n-grams, Indic-safe tokenizer)."""
from __future__ import annotations

# Split on whitespace and punctuation only, so Devanagari/Gujarati vowel signs stay inside words.
TOKEN_PATTERN = r"[^\s.,!?;:\"'()\[\]{}\u0964]+"


def build_vectorizer():
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.pipeline import FeatureUnion

    return FeatureUnion([
        ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), token_pattern=TOKEN_PATTERN,
                                 lowercase=True, sublinear_tf=True)),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), lowercase=True,
                                 sublinear_tf=True, min_df=2)),
    ])
