from value_refinery.core.chunk import chunk_markdown

SAMPLE = """# Incident Response Playbook (Sample)

## Goal
Turn messy ops notes into clean, reusable procedures with context.

## Triage Checklist
1) Identify affected hosts and users.
2) Capture volatile data (ps, netstat/ss, auth logs).
3) Snapshot configs + versions.

## Indicators
- suspicious domains: example.bad
- outbound spikes to unknown IP ranges

## Appendix
Command snippets:
  ss -lntp
  journalctl -u sshd --since "1 hour ago"
"""

def test_chunk_markdown_splits_h2_sections():
    chunks = chunk_markdown(SAMPLE)
    # Expect multiple H2 sections (Goal, Triage, Indicators, Appendix, etc.)
    assert len(chunks) >= 4

    paths = [c["path"] for c in chunks]
    assert any("Incident Response Playbook (Sample) / Goal" in p for p in paths)
    assert any("Incident Response Playbook (Sample) / Triage Checklist" in p for p in paths)

def test_chunk_markdown_no_headings_returns_whole_doc():
    txt = "just some text\nno headings here\n"
    chunks = chunk_markdown(txt)
    assert len(chunks) == 1
    assert chunks[0]["text"].strip() == txt.strip()
