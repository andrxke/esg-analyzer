"""Tier-2 pre-filter: reduce a full report to the claim/number sections under a
token budget, so the expensive LLM pass stays bounded.

This is ONLY for Tier-2 (quoted-evidence on presence tells). Omission tells are
handled by Tier-1 over the WHOLE document (see rubric.scan_tier1) precisely
because you cannot detect an omission from a filtered excerpt.

Approach (cheap, deterministic, no LLM):
- Split into paragraph-ish blocks.
- Keep blocks that contain claim/number signal (targets, neutrality language,
  superlatives, percentages, tonnage, years).
- Accumulate kept blocks until a character budget that approximates the token
  cap is reached (~4 chars/token heuristic; conservative).
"""

from __future__ import annotations

import re

# ~15-30k token target from DESIGN.md. Use the low end and a conservative
# 4 chars/token estimate -> ~60k chars. Keeps cost predictable.
DEFAULT_CHAR_BUDGET = 60_000

_SIGNAL_RE = re.compile(
    r"""
    net[\s\-]?zero | carbon\s+neutral | offset          # neutrality / offsets
    | scope[\s\-]?[123]                                  # emissions scopes
    | \d+(?:\.\d+)?\s*%                                  # percentages
    | \b20[2-6]\d\b                                      # target/baseline years
    | co2 | emission | tco2                              # emissions terms
    | industry[\s\-]?leading | world[\s\-]?class         # superlatives
    | commit(?:ment|ted)? | target | reduc              # commitment/target/reduction
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _blocks(text: str) -> list[str]:
    # Split on blank lines; fall back to single-newline if the doc has none.
    parts = re.split(r"\n\s*\n", text)
    if len(parts) == 1:
        parts = text.split("\n")
    
    # PDF extraction can result in massive blocks (e.g., a whole page as one line).
    # If a block is too large, it will consume the entire token budget just because
    # one signal word was in it. We forcefully split huge blocks into ~1000 char chunks.
    MAX_BLOCK_SIZE = 1000
    refined_blocks = []
    
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if len(p) <= MAX_BLOCK_SIZE:
            refined_blocks.append(p)
        else:
            # Force split large blocks into chunks to prevent budget hoarding
            words = p.split()
            current_chunk = []
            current_len = 0
            for w in words:
                if current_len + len(w) > MAX_BLOCK_SIZE:
                    refined_blocks.append(" ".join(current_chunk))
                    current_chunk = [w]
                    current_len = len(w) + 1
                else:
                    current_chunk.append(w)
                    current_len += len(w) + 1
            if current_chunk:
                refined_blocks.append(" ".join(current_chunk))
                
    return refined_blocks


def filtered_size(text: str) -> int:
    """Total chars of all claim-signal blocks BEFORE the budget cap is applied.

    The eval compares this against DEFAULT_CHAR_BUDGET: if it exceeds the budget,
    prefilter() truncated real claim-signal content, meaning some presence-tell
    evidence may have been dropped before ever reaching the LLM. That's a
    lost-signal risk the cost-validation report should flag, distinct from a
    report that simply fit.
    """
    total = 0
    for block in _blocks(text):
        if _SIGNAL_RE.search(block) is not None:
            total += len(block)
    return total


def prefilter(text: str, char_budget: int = DEFAULT_CHAR_BUDGET) -> str:
    """Return the claim/number-bearing subset of `text`, capped at char_budget.

    If nothing matches (no claim signal at all), returns "" — the caller treats
    an empty Tier-2 input as "no presence tells to check" and relies on Tier-1.
    """
    kept: list[str] = []
    used = 0
    for block in _blocks(text):
        if _SIGNAL_RE.search(block) is None:
            continue
            
        block_len = len(block)
        # Account for the \n\n that will be added
        if kept:
            block_len += 2
            
        if used + block_len > char_budget:
            # Truncate the final block to fit the budget exactly, then stop.
            remaining = char_budget - used
            if kept:
                remaining -= 2
            if remaining > 0:
                kept.append(block[:remaining])
            break
            
        kept.append(block)
        used += block_len

    return "\n\n".join(kept)
