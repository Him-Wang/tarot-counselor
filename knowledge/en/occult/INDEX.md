<!-- SPDX-License-Identifier: CC-BY-NC-SA-4.0 -->
<!-- Copyright (c) 2026 Him-Wang -->
# Occult Context Library (occult)

This directory only participates in retrieval when the user turns on **occult mode**; when it is off, none of these files enter the context.

## What to put here
- Add `.md` files directly in this directory; subdirectories are fine (for example `occult/rituals/lesser-key-of-solomon.md`).
- The filename is the path shown in retrieval results; specific names are easier to hit: "Hermeticism · seven principles.md" beats "notes1.md".
- Keep a README or INDEX (this file) for navigation — `INDEX.md` itself is not retrieved.

## What is most useful
1. Systems and lineages: Hermeticism, the Kabbalistic tree of life, the three stages of alchemy, the Wiccan year wheel, planetary hours and lunar phases.
2. Symbol correspondences: element–direction–colour–planet–minor-suit tables.
3. Anthropological accounts of ritual: how seances, ouija, invocation and banishment were historically performed (description, not an instruction manual).
4. Psychological and clinical perspectives: reliable frameworks for framing mystical experience as psychology (Jungian synchronicity, dissociation, imaginary companions).
5. Boundaries and risks: which practices carry real-world harm risks (fasting, oxygen deprivation, psychedelics, long solitary channeling, paid "blessing" services) and how to warn about them.

## What not to write
- Step-by-step practical instructions (summoning steps, dosages, durations, equipment lists).
- Any claim of verifiable psychic results, verbatim words from the dead, or diagnoses of possession.
- Specific medical, legal, or financial conclusions.

These are not matters of style: the occult prompt hard-codes "no practical instructions that could harm anyone," and similar content in the documents is still bound by that rule even when quoted as text.

## Retrieval behaviour
- Uses the keyword scoring in `agent/knowledge.py`, `top_k=3`, at most 9000 characters per turn.
- With occult mode off, `knowledge.retrieve(..., include_occult=False)` filters these files out, and `/api/knowledge` does not list them.
