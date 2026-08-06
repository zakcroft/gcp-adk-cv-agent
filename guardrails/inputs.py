"""Input validation — called from load_customer_documents before state is
written. Ordinary upload checks, same as any web form."""

# Character counts, measured on the decoded str (not file bytes).
# Floor: smallest real CV in examples/cases is 375 chars, so 200 leaves
# headroom while rejecting junk. Ceiling: far above any real document;
# bounds token cost. Also catches empty strings (len 0 < MIN_CHARS).
MIN_CHARS = 200
MAX_CHARS = 50_000


def check_readable(data: bytes, mime_type: str) -> bool:
    """Bytes level: is this a plain-text file we can decode?"""
    if mime_type != "text/plain":
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def check_size(cv_text: str, jd_text: str) -> bool:
    """String level: each document big enough to be real, small enough
    to be sane."""
    for text in (cv_text, jd_text):
        n = len(text.strip())
        if n < MIN_CHARS or n > MAX_CHARS:
            return False
    return True

def check_duplicates(cv_text: str, jd_text: str) -> bool:
    """String level: two distinct documents — the same file uploaded twice
    means one of the slots is not what it claims to be."""
    if cv_text == jd_text:
        return False
    return True


def check_inputs(cv_data: bytes, cv_mime: str, jd_data: bytes, jd_mime: str) -> bool:
    """Entry point for the tool: run every input check in order, cheapest
    first. Bytes checks must pass BEFORE decoding is safe."""
    if not check_readable(cv_data, cv_mime):
        return False
    if not check_readable(jd_data, jd_mime):
        return False

    cv_text = cv_data.decode("utf-8")
    jd_text = jd_data.decode("utf-8")

    if not check_duplicates(cv_text, jd_text):
        return False
    return check_size(cv_text, jd_text)


# TODO:
# - plausibly a CV / plausibly a JD (keyword heuristics; small LLM fallback)