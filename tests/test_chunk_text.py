from value_refinery.core.chunk import chunk_text


def test_chunk_jsonl_splits_records():
    text = "\n".join([f'{{"i":{i}}}' for i in range(1, 51)]) + "\n"
    chunks = chunk_text(text, ext=".jsonl", max_chunk_chars=120, min_chunk_chars=1)
    assert len(chunks) > 1
    assert all(c["text"].strip() for c in chunks)


def test_chunk_csv_repeats_header_and_splits():
    header = "a,b,c\n"
    rows = "".join([f"{i},{i+1},{i+2}\n" for i in range(1, 51)])
    text = header + rows
    chunks = chunk_text(text, ext=".csv", max_chunk_chars=180, min_chunk_chars=1)
    assert len(chunks) > 1
    # each chunk should include header
    assert all(c["text"].splitlines()[0].strip() == "a,b,c" for c in chunks)
