---
name: polish
description: Polish academic writing for publication — remove AI and workflow artifacts, sharpen conclusion-led judgment, normalize terminology, improve clarity, and rewrite draft-like or self-referential prose into submission-ready scholarly text. Supports both Chinese and English.
license: MIT
---

# Final-Stage Academic Polishing (Publication-Oriented)

Use this skill to turn existing academic prose into a **publication-ready final text**, not a draft that still sounds as though it is being actively revised.

Core goals:
- remove AI traces
- remove pipeline / review / self-correction traces
- remove metanarrative and “writing action” language
- sharpen conclusion-led judgment
- normalize terminology
- improve clarity, judgment, and publication readiness
- ensure the prose presents **the research facts and argument themselves**, rather than the author's visible effort to organize them

This skill supports both Chinese and English.

---

## General principle: output only submission-ready prose, not “revision-process prose”

The polished manuscript text must satisfy the following principles:

1. **The main text must not reveal that the author is “writing this paper” in real time**
2. **The main text must not reveal how the author is organizing sections, tables, or variables**
3. **The main text must not reveal how the author is correcting, compressing, or restating earlier text**
4. **The main text must not contain system-environment vocabulary such as pipeline, plan, check, polish, or workspace**
5. **The text must read like a finished manuscript ready for submission, not an intermediate version still being repaired by AI**

Any sentence that sounds more like an editorial instruction, self-explanation, or revision note must be rewritten into a real scholarly statement—or deleted outright.

The target voice is an author who has already finished reading the evidence and is now making disciplined judgments from it. The prose should feel chosen, not auto-completed.

---

## Workflow

### 1. Understand the request

Confirm with the user:
- **Text to polish**: pasted directly, a file path, or a file inside the workspace
- **Polishing goal**: de-AI, academic-standard cleanup, style adaptation, or all of the above
- **Target language**: Chinese / English (and whether translation is also required)
- **Target style**: general academic journal, high-level review, Nature Reviews-style prose, or a user-supplied reference style

If the user does not specify a target, default to:
**a publication-oriented, high-level academic review style**.

---

### 2. Style analysis (if a reference text is provided)

If the user provides a style reference, analyze:
- **Sentence profile**: average sentence length, active/passive balance, depth of clause nesting
- **Term preferences**: preferred field-specific terminology
- **Paragraph structure**: where the topic sentence sits, how facts are developed, how paragraphs close
- **Citation style**: citation density, citation placement, whether references are appended after claims or embedded into the factual narrative
- **Level of formality**: restraint, abstraction, and strength of judgment

Then polish accordingly.

---

### 2.1 Mandatory exemplar pass for Nature Reviews-style polishing

If the target style is **Nature Reviews** or **Springer Nature Reviews**, and the example bank exists under `example/`, you must complete the following **before each generation or major rewrite pass**:

1. read `example/originals.md`
2. read the **full original text** of every exemplar listed there — prefer the portable copies under `reference/` (e.g. `reference/White-2012.md`); fall back to `data/papers/.../paper.md` if `reference/` is unavailable
3. then read `example/excerpts.md` and `example/strategies.md`
4. internalize only the **stylistic feel after reading** — rhythm, restraint, explanatory compression, paragraph turns, judgment density, and editorial control
5. do **not** memorize or transplant any specific topic content, claims, examples, citations, metaphors, coined phrases, or structure labels from the exemplars
6. write only from the user's source text and evidence

Hard rule:

- the examples are for **style transfer by felt register**, not for content reuse
- the originals must be read **before each generation**, not just once per session
- after reading them, the agent should remember **how the prose feels**, not **what the papers say**
- if the polished text visibly imports exemplar-specific content, the pass has failed and the text must be rewritten

---

## 3. High-priority cleanup targets

This skill has eight high-priority cleanup categories. Handle them systematically rather than merely smoothing wording on the surface.

---

### Category 1: system traces, workflow traces, and task-execution traces

Priority cleanup targets include:

- `workspace`
- `plan`
- `trial curation`
- `check`
- `pipeline`
- `draft`
- `polish`
- `This paper will`
- `The following section will`
- `This section discusses`
- `In this workspace`
- `This section answers`
- `As explained in the previous section`
- `If Section 2 answers ..., then Section 3 answers ...`

Revision direction:

- delete traces of the author visibly organizing the text
- delete section-function explanations
- delete “execution action” descriptions
- write objective facts, evidence relationships, and mechanistic judgments directly

Examples of sentence patterns that must not remain:

- `This paper therefore advances a narrower, more discriminating proposition ...`
- `This review includes four categories of direct evidence.`
- `If Section 2 answers ..., then Section 3 answers ...`
- `Table 1 compresses this point into ...`
- `From here onward, the discussion is organized not by ..., but by ...`

Even if these sentences are logically true, they describe the **writing process**, not final manuscript prose.

---

### Category 2: metanarrative and self-directed phrasing

AI-generated or heavily corrected text often preserves a conspicuous sense that “the author is still present on stage,” directing the writing in front of the reader.

Priority cleanup targets include:

- `This paper argues that`
- `This paper focuses on`
- `This paper no longer ... but instead ...`
- `As shown below`
- `This suggests to us that`
- `The key point here is`
- `In this sense`
- `More precisely`
- `In other words`
- `That is`

Revision direction:

- rewrite “what the author says” into “what the evidence supports”
- rewrite “writing actions” into “scholarly conclusions”
- if a sentence adds no new fact or judgment, delete it

For example:

Poor:
- `This paper therefore advances a narrower, more discriminating proposition ...`

Better:
- state the proposition itself directly, without narrating the action of “this paper advancing it”

Poor:
- `This review includes four categories of direct evidence.`

Better:
- move directly into those four evidence categories without separately announcing the inclusion action

---

### Category 3: mechanical connectives and template-balanced sentences

Priority cleanup targets include:

- `Furthermore`
- `Moreover`
- `Meanwhile`
- `Therefore`
- `Thereby`
- `It is worth noting that`
- `It should not be overlooked that`
- `Overall`
- `Taken together`
- `Rather than A, B`
- `The real key is not A but B`
- `X should be understood as B rather than A`
- `This suggests that`

Revision direction:

- reduce cues that explain the act of explanation itself
- let factual order, clause structure, and causal logic carry the paragraph naturally
- do not prop up the prose with oral-sounding signal phrases

Special caution:
`not A but B` should be kept only when it expresses a **substantive theoretical contrast**. If it exists only to create the impression of strong synthesis, rewrite it.

---

### Category 4: ornamental synthesis without adjudication

Priority cleanup targets include:

- `The evidence reveals ...`
- `occupies a distinctive niche`
- `rich in mechanistic ingenuity`
- `translational trajectory`
- `broad therapeutic spectrum`
- `underscores the versatility of`
- polished closing lines that sound authoritative but do not rank evidence, state a boundary, or identify the decisive comparison

Revision direction:

- replace ornamental synthesis with the actual ranked conclusion
- state which branch is strongest, which evidence is thin, and what should not yet be claimed
- let some sentences stay plain if plainness carries more truth
- if a sentence would still sound impressive after deleting its citations, it is probably too abstract and should be rewritten

---

### Category 5: overt self-correction traces and visible revision traces

When a model keeps polishing a text after being corrected, it often leaves the revision process inside the prose, for example:

- `This paper therefore advances a narrower, more discriminating proposition`
- `The discussion below no longer proceeds by ...`
- `Table 1 compresses this into ...`
- `This section no longer discusses ...`
- `Unlike the previous section, this section shifts to ...`
- `If Section 2 ..., then Section 3 ...`

All of these are **editorial-process language**, not scholarly prose.

Handling rules:

1. delete all traces of “this round of revision”
2. delete all traces of “correcting the previous wording”
3. delete all traces of “explaining how the section is organized”
4. rewrite whatever remains into standalone scholarly statements

Hard constraint:
- the manuscript must not sound as though the author is visibly correcting themselves
- the reader should not be able to infer that the prose passed through a prompt / pipeline / polish / check workflow

---

### Category 6: decorative but empty modifiers and conversational phrasing

Priority cleanup targets include:

- `sophisticated solution`
- `elegant route`
- `push this further`
- `switching circuit`
- `backdrop`
- `of great theoretical and practical significance`
- `offers new ideas`
- `shows broad promise`
- `a myriad of`
- `a plethora of`
- `paving the way for`
- `paradigm shift`

Revision direction:

- replace them with language that is scientifically definable, comparable, and verifiable
- keep modifiers restrained
- remove promotional inflation
- do not let the review read like platform marketing

---

### Category 7: broken bilingual terminology and inconsistent terminology

Priority cleanup targets include:

- unnecessary English fragments left inside Chinese prose
- multiple translations for the same concept
- unexplained English technical terms abruptly embedded inside Chinese sentences
- terminology that still reads like direct translation rather than field-standard usage

Revision direction:

- in Chinese prose, prefer established Chinese technical terms unless the English term is standard and necessary
- when needed, introduce a Chinese/English pair on first mention and then keep one form consistently afterward
- keep concept naming stable; do not rotate synonyms just to sound more sophisticated

---

### Category 8: overused em dashes and dash-driven cadence

AI-polished academic prose often leans on em dashes (`—`) or sentence-level double hyphens (`--`) to create instant contrast, explanation, or rhythm. Treat repeated dash compression as a visible AI cadence unless each instance is doing necessary syntactic work.

Detection:

- Count em dashes (`—`) and sentence-level double hyphens (` -- ` or `--` used as punctuation).
- Ignore hyphens inside compounds, minus signs, page ranges, and legitimate en dashes in numeric ranges.
- Flag the text if any paragraph contains more than one dash break.
- Flag the text if adjacent paragraphs both rely on dash breaks.
- Flag the whole text if it contains more than roughly two dash breaks per 1,000 words.

Revision direction:

- Replace ornamental dashes with periods when two claims should stand independently.
- Replace explanatory dashes with commas or parentheses when the inserted phrase is minor.
- Replace contrastive dashes with a semicolon, colon, or a rewritten causal/contrastive sentence.
- Split long dash-heavy sentences into shorter sentences when the dash is compensating for weak structure.
- Keep only the few dashes that mark a genuinely necessary interruption, appositive clarification, or decisive contrast.
- After revision, rescan; if the count remains high, repeat until dashes no longer define the prose rhythm.

---

## 4. New highest-priority rule: ban metanarrative section/table explanations from the main text

Any expression of the following types should be treated as non-final-draft language.

### 4.1 Banned section-explanation phrasing
- `This section addresses ...`
- `The previous section discussed ..., and this section now turns to ...`
- `If Section 2 answers ..., then Section 3 ...`
- `The real problem this chapter solves is ...`
- `The discussion below proceeds from ...`

### 4.2 Banned table-explanation phrasing
- `Table 1 compresses this point into ...`
- `Table 2 further illustrates ...`
- `As shown in Table 3, we can see ...`
- `This table summarizes the issue from the perspective of ...`

Allowed replacements:
- if a table must be mentioned in the prose, do it in a brief, result-oriented form, such as:
  - `Current studies show ... (Table 1)`
  - `Differences among strategies in ... are summarized in Table 2`
- do not explain **how** the table was organized
- do not discuss in the main text **why** the table was organized around a particular dimension

### 4.3 Banned writing-strategy explanations
- `The discussion no longer follows A, but instead follows B`
- `To avoid a flat list, the next part is organized by ...`
- `Unlike the conventional approach, this paper instead ...`
- `This paper attempts to build a more discriminating framework`

These are instructions to an editor or a prompt, not sentences for a finished submission draft.

---

## 5. Academic-convention checks

- **Logical coherence**: paragraphs should have clear causal, contrastive, or progressive relationships
- **Judgment density**: major sections should state what is established, what is only suggestive, and what is overread
- **Precision**: reduce vague words such as “many,” “some,” or “significant” unless they are defined; be specific whenever possible
- **Terminology consistency**: the same concept should be named consistently throughout
- **Tense correctness**: methods/results usually take past tense; field-level consensus usually takes present tense
- **Stable perspective**: maintain objective third-person scholarly narration throughout
- **Cadence variation**: not every paragraph should climax in a polished synthesis flourish or repeated em-dash compression
- **Dash discipline**: em dashes should be rare; repeated dash breaks must be detected and rewritten, not merely replaced mechanically
- **Remove system-environment traces**: no workflow language should remain
- **Remove metanarrative traces**: the author should not visibly narrate the organization of the text
- **Finished-manuscript expression**: the whole text should read like a finalized paper, not a manuscript under repair

---

## 6. Rewrite citation-placeholder paragraphs (high priority)

When the source text contains sentences like the following, do not make only minor word substitutions. Recognize them as **evidence placeholders** and rewrite them into finished, fact-bearing review paragraphs:

- `Additional evidence relevant to this section includes [@a; @b; @c]`
- `Related studies further support this view [@a; @b; @c]`
- `Similar studies include ... [@a; @b; @c]`
- sentences or paragraphs that are almost nothing but a citation list, with no testable factual content

### 6.1 Handling principles

1. **Read the cited sources before writing**
2. **Group by theme, not paper-by-paper chronology**
3. **Every paragraph must contain scientific facts**
4. **State the evidence boundary clearly**
5. **Keep the original citation keys whenever possible; do not expand the reference set casually**
6. **Split the paragraph when necessary**

### 6.2 Recommended paragraph shape

A rewritten paragraph should contain:

- **Conclusion sentence**: what this group of literature collectively shows
- **Fact sentences**: 1–3 concrete findings or trends
- **Evidence-boundary sentence**: what level of evidence those findings come from

### 6.3 Forbidden paragraph shapes

- `Additional evidence relevant to this section includes [@...]`
- `Related studies support this view [@...]`
- `These studies provide ideas for future work [@...]`

---

## 7. Output requirements

- return the polished text directly
- if the user asks, also summarize the main edits
- if the user asks for categorized changes, summarize them under these seven groups:
  1. system/workflow traces
  2. metanarrative and section-organization explanations
  3. mechanical connectives
  4. self-correction and revision traces
  5. decorative modifiers and conversational phrasing
  6. mixed Chinese/English terminology issues
  7. overused em dashes and dash-driven cadence
- if citation-placeholder sentences exist, add a separate summary of how placeholder citations were rewritten into fact-bearing prose
- if polishing a file, save the polished version alongside it (for example, `polished.md`)
- optionally output docx/pdf for review if requested

---

## 8. Principles

- **Preserve the author's scholarly judgment**: change the expression, not the core argument
- **Prioritize the final-draft perspective**: make the text read like a submission draft, not like something still being edited
- **Use the smallest necessary edit, but do not preserve editorial traces**: if one word solves the problem, do not rewrite the whole sentence; but if a sentence contains metanarrative, revision traces, or self-correction traces, rewrite or delete it outright
- **Do not add content from nowhere**: do not invent new claims or new citations that were absent from the original
- **When using exemplar papers, transfer only stylistic afterimage**: retain rhythm, paragraph architecture, restraint, and judgment habits; never carry over factual content, example logic, or citation material
- **Prefer restraint**: accurate, calm, and verifiable beats more ornate language
- **Prioritize terminology consistency**
- **The revision process must be invisible to readers**: the final text must not reveal any prompt, pipeline, check, or polish trace

---

## 9. Typical rewrite examples

### Counterexample 1
Original:
`This paper therefore advances a narrower, more discriminating proposition: the value of bacteria-loaded microneedles does not lie in whether loading succeeds, but in ...`

Problem:
- the author steps onto the stage and “advances a proposition”
- this is overt revision-stage metanarrative

Fix:
- state the scholarly judgment directly, without narrating the act of “this paper advancing it”

### Counterexample 2
Original:
`This review includes four categories of direct evidence.`

Problem:
- this describes a material-organization action, not a fact in the finished manuscript

Fix:
- delete the sentence
- move straight into the four evidence categories

### Counterexample 3
Original:
`If Section 2 answers why four variables must be controlled, then Section 3 answers which structures actually control those variables.`

Problem:
- this is chapter-guide metanarrative
- it reads like an outline note, not manuscript prose

Fix:
- rewrite it as direct discussion of the relationship between structures and variables
- do not explain “what Section 2 / Section 3 each answers” inside the main text

### Counterexample 4
Original:
`Table 1 compresses this point into the perspective of how structure/process controls variables, rather than laying the discussion out by microneedle name.`

Problem:
- this explains how the table was organized
- it exposes the writing process and the author's editorial actions

Fix:
- delete this type of sentence
- if the table must be referenced, mention it only in a result-oriented way

---

## 10. Final criteria

The polished text must satisfy all of the following:

- the reader cannot tell that it passed through an AI polishing pipeline
- the reader cannot tell that the author is explaining their own writing actions in the text
- the reader cannot tell how the sections and tables were “designed” behind the scenes
- the prose reads as mature, restrained, submission-ready scholarly argumentation
- logic advances through facts and judgment, not through metanarrative signals
