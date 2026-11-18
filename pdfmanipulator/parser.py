"""No-AI natural-language templates. Unknown requests fail closed, not guessed."""
from __future__ import annotations
import re
from .engine import WorkflowError, validate_steps

def two_pdf_request(prompt: str, aliases: list[str]) -> list[dict] | None:
    """Handle ordered, multi-step instructions without silently dropping clauses.

    Input2 is inserted as a complete PDF; its first page becomes output page 1
    when the user asks for the second document first.
    """
    if len(aliases) < 2:
        return None
    words = re.sub(r"\s+", " ", prompt.lower()).strip()
    refers_second = bool(re.search(r"\b(?:second|2nd)\s+(?:pdf|file|document)\b", words))
    has_add = bool(re.search(r"\b(?:add|insert|append|merge|combine|join|put|place)\b", words))
    if not (refers_second and has_add):
        return None
    wants_first = bool(
        re.search(r"\b(?:second|2nd)\s+(?:pdf|file|document)\b.{0,85}"
                  r"(?:\b(?:first|page\s*(?:1|one)|start|beginning|before)\b)", words)
        or re.search(r"\b(?:first|start|beginning)\b.{0,55}"
                     r"\b(?:second|2nd)\s+(?:pdf|file|document)\b", words)
    )
    # Isolate delete clauses from 'second PDF is page 1' so that unrelated
    # page numbers are never mistaken for a page-to-delete instruction.
    delete_clauses = re.findall(
        r"\b(?:delete|remove|discard)\b(.{0,140}?)(?=[.!?]|\b(?:add|insert|append|merge|combine|join|put|place)\b|$)",
        words
    )
    delete_page = None
    for clause in delete_clauses:
        first_page = re.search(r"\b(?:first|1st)\s+page\b", clause)
        explicit_page = re.search(r"\bpage\s*(\d+)\b", clause)
        if first_page:
            delete_page = "1"
        elif explicit_page:
            delete_page = explicit_page[1]
        else:
            raise WorkflowError("Specify which page to delete from the first PDF.")
        if re.search(r"\b(?:second|2nd)\s+(?:pdf|file|document)\b", clause):
            raise WorkflowError("Specify a deletion from the first PDF before combining documents.")
    steps = [{"op": "load", "source": aliases[0]}]
    if delete_page is not None:
        steps.append({"op": "delete", "pages": delete_page})
    steps.append({"op": "insert_pdf", "source": aliases[1],
                  "position": 1 if wants_first else "end"})
    return validate_steps(steps)


def interpret(prompt: str, aliases: list[str]) -> list[dict]:
    """Parse a constrained, useful subset of English into safe operation dictionaries."""
    if not prompt.strip() or len(prompt) > 2000:
        raise WorkflowError("Enter a short instruction (up to 2,000 characters).")
    words = prompt.lower().strip()
    # Normalize everyday instructions like "every three pages" and "pages 2 and 7".
    words = re.sub(r"(?<=\d)\s+and\s+(?=\d)", ",", words)
    for word, number in {"one": 1, "two": 2, "three": 3, "four": 4,
                         "five": 5, "six": 6, "seven": 7, "eight": 8,
                         "nine": 9, "ten": 10}.items():
        words = re.sub(r"\bevery\s+" + word + r"(?=\s+pages?\b)",
                       f"every {number}", words)
    special = two_pdf_request(prompt, aliases)
    if special is not None:
        return special
    source = aliases[0] if aliases else "input1"
    base = [{"op": "load", "source": source}]
    steps: list[dict] = []
    duo = bool(re.search(r"\b(duplex|fronts?\s+and\s+backs?|front\s+pages|back\s+pages|single.sided scans)\b", words))
    if duo:
        if len(aliases) < 2:
            raise WorkflowError("The duplex preset needs two PDFs: fronts and backs.")
        result = [{"op": "duplex", "fronts": aliases[0], "backs": aliases[1],
                   "reverse_backs": not bool(re.search(r"\bbacks?\s+in\s+(ascending|normal)\s+order\b", words)),
                   "rotate_backs": bool(re.search(r"rotate\s+(the\s+)?backs?", words))}]
        return validate_steps(result)
    if re.search(r"\b(merge|combine|join)\b", words) and len(aliases) > 1:
        base = [{"op": "merge", "sources": aliases}]
    if re.search(r"\b(batch|each pdf|each file|all files separately)\b", words) and len(aliases) > 1:
        base = [{"op": "load_each", "sources": aliases}]
    split_every = re.search(r"\b(?:split|separate|divide)\b.*?\b(?:every|each|into groups? of)\s+(\d+)\s+pages?\b", words)
    if not split_every:
        split_every = re.search(r"\b(?:split|separate)\b.*?\binto\s+(\d+)[-\s]?page\b", words)
    if split_every:
        steps.append({"op": "split_every", "n": int(split_every[1])})
    elif re.search(r"\b(?:split|make)\b.*?\b(?:pages?\s+\d+|one pdf containing)\b", words):
        # Ranges written as "pages 1-5 ... pages 6-12 ... everything remaining".
        ranges = re.findall(r"\bpages?\s+(\d+\s*[-–]\s*\d+)\b", words)
        if ranges:
            steps.append({"op": "split_ranges", "ranges": [r.replace("–", "-") for r in ranges],
                          "include_remaining": bool(re.search(r"remain|rest|everything else", words))})
    if re.search(r"\b(extract|keep only|select)\b", words):
        pages = re.search(r"\bpages?\s+(\d+(?:\s*(?:,|-|–|and)\s*\d+)*)", words)
        if pages:
            steps.append({"op": "extract", "pages": pages[1].strip(" ,").replace("–", "-")})
    if re.search(r"\b(delete|remove)\s+(?:the\s+)?(?:pages?\s+)?(?:blank|empty)\s+pages?\b|\bdelete blank\b", words):
        steps.append({"op": "remove_blanks"})
    elif re.search(r"\b(delete|remove)\b.*?\bpages?\s+", words):
        pages = re.search(r"\bpages?\s+(\d+(?:\s*(?:,|-|–|and)\s*\d+)*)", words)
        if pages:
            steps.append({"op": "delete", "pages": pages[1].strip(" ,").replace("–", "-")})
    if re.search(r"\b(reverse|flip)\s+(the\s+)?page\s+order\b|\breverse\s+(this|the|my)\s+pdf\b", words):
        steps.append({"op": "reverse"})
    if re.search(r"\brotate\b", words):
        degrees = re.search(r"(90|180|270)\s*(?:degrees?|°)", words)
        pages = re.search(r"\bpages?\s+(\d+(?:\s*(?:,|-|–|and)\s*\d+)*)", words)
        selector = "even" if re.search(r"\beven(?:-numbered)?\s+pages?\b", words) else (
            "odd" if re.search(r"\bodd(?:-numbered)?\s+pages?\b", words) else (
                pages[1].strip(" ,").replace("–", "-") if pages else "all"))
        steps.append({"op": "rotate", "pages": selector, "degrees": int(degrees[1]) if degrees else 90})
    if re.search(r"\bduplicate\b", words):
        pages = re.search(r"\bpages?\s+(\d+(?:\s*(?:,|-|–|and)\s*\d+)*)", words)
        steps.append({"op": "duplicate", "pages": pages[1].strip(" ,") if pages else "all"})
    if not steps and base[0]["op"] == "load":
        raise WorkflowError("I couldn't safely interpret that request offline. Try a suggested prompt, a preset, or configure an AI provider.")
    return validate_steps(base + steps)

EXAMPLES = [
    "Split this PDF every 3 pages",
    "Combine these PDFs into one document",
    "Turn front and back scans into one duplex PDF",
    "Rotate every even page 180 degrees",
    "Reverse the page order",
    "Remove blank pages",
    "Extract pages 1-5",
    "Split pages 1-5, pages 6-12, and everything remaining",
]
