"""Document size limits shared by the input gate and the output gate.

One source of truth on purpose: a final draft is held to the same size
window as an uploaded document, so recalibrating here moves both gates.

Character counts, measured on decoded text (not file bytes).
Floor: the smallest real CV in examples/cases is 375 chars, so 200 leaves
headroom while rejecting junk (and catches empty: len 0 < floor).
Ceiling: a dense three-page CV from a 20-year career measures ~10k chars;
doubling that admits any real document while bounding token cost.
"""

MIN_DOC_CHARS = 200
MAX_DOC_CHARS = 20_000
