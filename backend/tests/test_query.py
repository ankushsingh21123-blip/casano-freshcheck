"""Tests for deterministic query derivation."""

from app.query import derive_query


def test_extracts_keywords_lowercase_without_stopwords():
    query = derive_query(
        "What is the capital of France?",
        "Paris is the capital of France, known for the Eiffel Tower.",
    )
    assert query == "capital france eiffel known paris tower"


def test_deterministic_same_input_same_output():
    args = ("Solar panel efficiency records?", "New panels reached 26% efficiency.")
    assert derive_query(*args) == derive_query(*args)


def test_caps_term_count_and_length():
    question = " ".join(f"uniquequestionterm{i}" for i in range(30))
    answer = " ".join(f"uniqueanswerterm{i}" for i in range(30))
    query = derive_query(question, answer)
    assert len(query.split()) <= 8
    assert len(query) <= 200


def test_question_terms_outrank_single_answer_terms():
    query = derive_query(
        "qubit coherence times",
        "apple apple apple banana",
    )
    terms = query.split()
    assert terms.index("qubit") < terms.index("banana")
    assert terms.index("coherence") < terms.index("banana")


def test_stopwords_only_falls_back_to_question_text():
    assert derive_query("What is the?", "It is a.") == "What is the?"


def test_repeated_terms_rank_higher():
    query = derive_query("battery", "battery battery battery charger")
    assert query.split()[0] == "battery"
