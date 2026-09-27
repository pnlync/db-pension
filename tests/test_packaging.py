"""M12 acceptance tests (SPEC §9 M12, §11): every public number comes from outputs/; figures are labelled;
the page's links resolve; the disclosure note is complete."""
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
import yaml

from pension import figures
from pension.io import CONFIG, OUTPUTS, ROOT

DOCS = {"README": ROOT / "README.md", "memo": ROOT / "reports" / "trustee_memo.md", "page": ROOT / "docs" / "index.html"}
# structural numbers that are not results: years, figure and section numbers, horizons, the scheme's own rules
STRUCTURAL = {str(y) for y in range(2000, 2033)} | {str(n) for n in range(0, 11)} | {"20", "30", "31", "65", "60", "40",
                                                                                     "1/60", "19", "34", "53B", "44"}


def leaves(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from leaves(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from leaves(v)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        yield float(obj)


def formats(x):
    x = abs(x)
    out = set()
    for scale in (1, 1e-6, 100, 1e4, 1e-3):
        v = x * scale
        for d in (0, 1, 2):
            out.add(f"{v:,.{d}f}")
            out.add(f"{v:.{d}f}")
    return out


@pytest.fixture(scope="module")
def allowed():
    values = set()
    for path in OUTPUTS.glob("*.json"):
        for x in leaves(json.loads(path.read_text())):
            values |= formats(x)
    for path in CONFIG.glob("*.yaml"):
        for x in leaves(yaml.safe_load(path.read_text())):
            values |= formats(x)
    return values | STRUCTURAL


def numbers_in(text):
    text = re.sub(r"<style>.*?</style>|<head>.*?</head>", " ", text, flags=re.S)   # CSS and metadata
    text = re.sub(r"https?://\S+|\([^)]*\.(?:png|md|csv|xlsx)\)|`[^`]*`|<code>.*?</code>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return [n.strip(",.") for n in re.findall(r"(?<![A-Za-z])\d[\d,]*(?:\.\d+)?", text)]   # skip PV01, IAS19-style terms


@pytest.mark.parametrize("name", list(DOCS))
def test_every_number_comes_from_outputs(name, allowed):
    text = DOCS[name].read_text()
    missing = sorted({n for n in numbers_in(text) if n not in allowed})
    assert not missing, f"{name}: numbers not found in outputs/ or config/: {missing}"


def test_cv_numbers_come_from_outputs(allowed):
    cv = json.loads((OUTPUTS / "cv_numbers.json").read_text())
    for key, value in cv.items():
        assert f"{abs(value):.1f}" in allowed or f"{abs(value):.0f}" in allowed, key


def test_every_figure_states_synthetic_members_and_date():
    source = Path(figures.__file__).read_text()
    bodies = re.split(r"\ndef ", source)
    fig_bodies = [b for b in bodies if b.startswith("fig")]
    assert len(fig_bodies) >= 6
    for body in fig_bodies:
        assert "Synthetic members" in body and "market_date" in body, body.split("(")[0]


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if k in ("href", "src"):
                self.refs.append(v)


def test_page_links_resolve():
    parser = Links()
    parser.feed(DOCS["page"].read_text())
    docs = ROOT / "docs"
    for ref in parser.refs:
        if ref.startswith("#"):
            assert f'id="{ref[1:]}"' in DOCS["page"].read_text(), ref
        elif ref.startswith("./"):
            assert (docs / ref[2:]).exists(), ref
        elif ref.startswith("https://github.com/pnlync/db-pension/blob/main/"):
            assert (ROOT / ref.split("/blob/main/")[1]).exists(), ref


def test_disclosure_note_complete():
    text = (ROOT / "reports" / "disclosure_note.md").read_text()
    for n in range(1, 8):
        assert re.search(rf"^## {n}\. ", text, re.M), f"table {n} missing"
    assert "Produced by the 2025 analysis of change" not in text


def test_buyin_loss_always_qualified():
    for name, path in DOCS.items():
        text = path.read_text()
        if "OCI" in text or "loss" in text:
            assert "exact" in text and "match" in text, name
