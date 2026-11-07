from adhyaksh.nlu import dataset as ds


def test_dataset_files_validate():
    assert ds.validate() == []


def test_requirements_met():
    df = ds.load()
    assert len(df) >= 500 and df["text"].str.lower().duplicated().sum() == 0
    assert df["intent"].value_counts().min() >= 40
    assert all((df["language"] == l).mean() >= 0.15 for l in ds.LANGS)
    assert (df["reviewed"] == "false").all()  # stays UNREVIEWED until the author confirms
    assert len(ds.load(ds.TEST_CSV)) >= 100


def test_test_file_disjoint_from_training():
    a = set(ds.load()["text"].str.lower())
    b = set(ds.load(ds.TEST_CSV)["text"].str.lower())
    assert not (a & b)


def test_split_is_stratified_reproducible():
    df = ds.load()
    a, b = ds.split(df, 42), ds.split(df, 42)
    assert all(x["text"].tolist() == y["text"].tolist() for x, y in zip(a, b))
    train, val, test = a
    assert len(train) + len(val) + len(test) == len(df)
    assert not (set(train["text"]) & set(test["text"]))
    assert set(test["intent"]) == set(ds.INTENTS)


def test_validator_catches_bad_rows():
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    (d / "t.csv").write_text("text,intent,language,script,source,reviewed\nhello,bogus,en,latin,generated,false\n"
                             "hello,greet,en,latin,generated,false\n", encoding="utf-8")
    errs = ds.validate(d / "t.csv", ds.TEST_CSV)
    assert any("unknown intent" in e for e in errs) and any("duplicate" in e for e in errs)
    (d / "u.csv").write_text("text,intent\nx,greet\n", encoding="utf-8")
    assert any("missing columns" in e for e in ds.validate(d / "u.csv", ds.TEST_CSV))
