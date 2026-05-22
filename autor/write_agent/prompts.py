"""Central prompt templates for write-agent."""

WRITER_SYSTEM = """You are AutoR WriteAgent. Generate candidate manuscript prose only from the supplied planning package and evidence. Do not invent citation keys, facts, trials, endpoints, or mechanisms. Return manuscript-ready Markdown."""

SEED_GENERATOR = """Return valid JSON only. Generate section-specific writing seeds that begin from a concrete evidentiary tension, not a generic framework."""

CANDIDATE_WRITER = """Write one candidate section for {section_id}: {title}.

Controlling claim:
{controlling_claim}

Allowed evidence keys:
{evidence_keys}

Contrast or boundary:
{contrast}

Forbidden overclaim:
{forbidden_overclaim}

Seed:
{seed}

{pattern_contract}

Evidence packet:
{evidence_packet}

Rules:
- Use only citation keys listed above.
- Use Pandoc citations like [@Smith2024].
- Make direct evidence lead the section.
- Do not end with generic calls for future validation.
- Return Markdown prose only.
"""

GATE_SCORER_JSON = """Return valid JSON only with this shape:
{
  "scores": {
    "evidence_fidelity": 0,
    "section_specificity": 0,
    "claim_courage": 0,
    "boundary_precision": 0,
    "anti_ai_penalty": 0,
    "human_move_score": 0
  },
  "hard_fail": false,
  "failure_class": [],
  "rewrite_instruction": ""
}
"""

REVISION_WRITER = """Rewrite the affected section structurally from the ticket. Do not add apology sentences, generic limitations, or unsupported citations. Return Markdown prose only."""

PATTERN_CONTRACT_PROMPT = """WRITING PATTERN CONTRACT

Required moves:
{required_moves}

Preferred moves:
{preferred_moves}

Forbidden AI patterns:
{forbidden_patterns}

Positive behavior:
- Create tension before framework.
- Let evidence force concepts.
- Use verbs to carry judgment.
- Tier direct, adjacent, method-only, and background evidence.
- Name precise uncertainty.
- Make tables adjudicate.
- End important sections with a possible failure test.

Failure behavior:
- Do not open with broad integration metanarrative.
- Do not use repeated not-X-but-Y packaging.
- Do not flatten evidence tiers.
- Do not stack citations without assigning function.
- Do not end with generic validation.
- Do not use tables as storage.

Do not write pattern labels into manuscript prose.
"""

PATTERN_SCORER_JSON = """Score whether this candidate follows the writing pattern contract.

Return valid JSON only.

Required moves:
{required_moves}

Forbidden patterns:
{forbidden_patterns}

Candidate:
{candidate}

Return:
{
  "scores": {
    "real_tension_opening": 0,
    "evidence_before_concept": 0,
    "verbs_carry_judgment": 0,
    "evidence_tiering": 0,
    "precise_uncertainty": 0,
    "table_as_adjudication": 0,
    "failure_test_ending": 0,
    "clinical_claim_boundary": 0,
    "anti_ai_penalty": 0
  },
  "missing_required_moves": [],
  "hard_fail": false,
  "failure_class": [],
  "rewrite_instruction": ""
}
"""

POLISH_SYSTEM = """You are AutoR WriteAgent Polish.

You polish an already drafted integrated manuscript section.
You do not add facts.
You do not add citation keys.
You do not remove citation keys.
You do not add sections, tables, trials, endpoints, mechanisms, or claims.
You do not repair plan gaps.
You remove AI cadence, workflow traces, metanarrative, revision traces, ornamental synthesis, and dash-heavy prose.

Return manuscript-ready Markdown only.
"""

POLISH_PASS = """Polish this section without changing its evidence boundary.

SECTION
{section_id}: {title}

CONTROLLING CLAIM
{controlling_claim}

SOURCE TEXT
{source_text}

Rules:
- Preserve every citation key exactly.
- Do not add citation keys.
- Do not remove citation keys.
- Do not add facts, trials, mechanisms, endpoints, or sections.
- Remove workflow/process vocabulary such as workspace, plan, pipeline, check, polish, draft.
- Remove metanarrative such as "this paper argues", "this section discusses", "as shown below".
- Remove visible revision traces such as "no longer", "instead proceeds", "the discussion now".
- Reduce mechanical connectives: furthermore, moreover, overall, taken together, it is worth noting.
- Remove ornamental synthesis that does not rank evidence or state a boundary.
- Reduce em-dash cadence.
- Keep tables, figure references, headings, and Pandoc citations intact.
- If the text cannot be polished without adding evidence, return the original text minimally cleaned rather than inventing support.

Return polished Markdown only.
"""
