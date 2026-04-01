---
name: check
description: Use this skill after a review draft is complete. It launches an independent checking sub-agent near the end of the manuscript to systematically inspect the review's structure, prose quality, mechanistic argumentation, clinical-evidence organization, analytical value of tables, and AI-like tone. If the draft falls short, surface polishing is not allowed; the specified sections must be sent back and rewritten against a concrete issue list.
license: MIT
---

# Final-Draft Review Check Skill

You are performing a **final-draft review check** on a completed biomedical review draft, especially for topics such as:
- CAR-T
- hematologic malignancies
- mechanistic reviews
- reviews of clinical research progress
- integrative reviews that combine mechanistic and clinical content

Your job is not to keep expanding the text, nor to simply polish the language.
Your responsibilities are to:

1. **Assess whether the overall structure truly works**
2. **Check whether the prose feels bloated, hollow, or strongly AI-written**
3. **Check whether the mechanism section actually builds mechanisms rather than offering a grab bag of labels**
4. **Check whether the clinical section establishes evidence gradients and decision logic**
5. **Check whether the tables add analytical value**
6. **If the draft is not good enough, send it back for rewriting and specify which sections must be rewritten and how**

---

## When to use this skill

Use this skill only after the main agent has already completed the following:
- a full review draft has been generated
- titles, subheadings, and body text are already in place
- the major literature has been incorporated
- tables have been produced
- `/trials` retrieval results have been integrated
- the manuscript is ready for one final structural and quality review

By default, this skill launches a checking sub-agent at the **end-of-manuscript stage**.

---

## Working method

You must follow the workflow below:

### Step 1: Launch an independent checking sub-agent
Once the main draft is complete, launch an independent sub-agent to conduct a **go/no-go review**, not a round of friendly suggestions.

This sub-agent must work by the following principles:

- judge whether the manuscript can proceed directly into final-draft form
- prioritize structural defects over minor wording issues
- do not be fooled by superficial completeness, apparent balance, or table abundance
- specifically identify the hallmark symptoms of a polished AI-style review
- if the through-line is weak, the mechanistic reasoning is hollow, evidence tiers are mixed together, or sections merely restate one another, directly judge that the manuscript **must be sent back for rewriting**

---

## Overall judgment principles

You must always remember:

A review that looks complete is not necessarily a review that truly holds together.

The following must be treated as serious problems:
- the outline is expansive, but the central argument is weak
- each chapter works in isolation, but they do not drive the argument forward together
- the mechanism section merely lists concepts, molecules, or causes of failure
- the clinical section is just a pile of studies with no evidence hierarchy
- there are many tables, but they mainly add neatness rather than judgment
- the conclusion is too safe, too balanced, and too much like a “correct AI summary”
- the author does not dare to adjudicate, and only writes things like “worth noting,” “needs further study,” or “still requires validation”

---

# Check dimensions

## I. Structure check

Check the following questions:

### 1. Is there a single, clear, repeatedly testable through-line?
The through-line must be compressible into 1–2 explicit propositions, not vague background language.

For topics such as “Concepts and research progress in sequential CAR-T therapy,” first check whether the entire review is actually organized around claims like the following:

- The essence of sequential therapy is a second-step intervention redefined by the failure pattern that emerges after the first treatment
- Sequential therapy is not simply doing CAR-T again, but responding to and redesigning treatment around a new failure mode
- Whether the second step works depends on whether it responds to the new pathological state created after the first treatment

If the whole manuscript cannot be compressed into strong claims of this kind and instead remains a loose parallel structure such as “definition + classification + clinical progress + mechanisms + outlook,” judge that the **structure is not strong enough**.

### 2. Do the sections advance the argument rather than restate it in parallel?
Focus on the following:
- Does the claim introduced in the opening actually get pushed forward later on?
- Do different sections merely rephrase the same central sentence in different words?
- Do “concepts,” “research progress,” “mechanisms,” “challenges,” and “future directions” form a real progression?

If multiple sections keep repeating things like:
- “Sequential therapy is not simple repetition”
- “The second-step decision should be based on new information after the first treatment”
- “Different failure modes require different second-step strategies”

but never derive anything further, judge that the manuscript suffers from **serious section-level repetition**.

### 3. Has the scope sprawled out of control?
Check whether the draft pulls in too much material that is related, but not part of the core argumentative chain, for example:
- platform technologies only weakly connected to the topic
- too much cross-disease or cross-system spillover
- overly heavy speculation about future technologies
- solid-tumor analogies taking up too much space without directly serving the core topic

If the **scope of discussion** is clearly larger than the **scope of conclusions that the evidence can safely support**, judge the manuscript as **bloated and unfocused**.

---

## II. Text style and AI-tone check

### 1. Does the manuscript show the classic symptoms of a polished AI style?
Focus on whether it is:

- very good at building frameworks, but not willing enough to cut material
- very good at balancing positions, but not willing enough to make judgments
- very good at summarizing, but with more summary sentences than genuinely advancing sentences
- very good at adding boundary reminders, but without actual adjudication
- full-sounding paragraph by paragraph, while the real information gain remains limited

### 2. Are abstract sentences too dense?
Check whether the following kinds of sentences appear too often:
- “Its essence is not ... but ...”
- “It should be understood as ... rather than ...”
- “The real key is not ... but ...”
- “This suggests that ...”
- “In the future, it may be necessary to ...”
- “Worth noting is ...”
- “We should shift from ... to ...”

If these sentence patterns appear frequently, but they are not followed by new mechanistic information, evidence stratification, or decision logic, judge that the draft contains **too much abstract repackaging and too little real information gain**.

### 3. Is the manuscript overly safe?
If the whole manuscript relies mainly on language such as:
- worth noting
- still requires validation
- conceptually feasible
- the direction is clear, but the route is not yet fixed
- more research is needed
- cannot be extrapolated directly

while rarely stating clearly:
- which routes are actually more mature
- which kinds of evidence are in fact weak
- which directions should not yet occupy major body sections
- which conclusions should not be over-extrapolated

then judge that the manuscript shows **insufficient adjudication and too much AI-like tone**.

---

## III. Mechanistic-argumentation check

The mechanism section is a key veto zone and must be examined strictly.

### 1. Is the mechanism chapter merely a list of mechanism labels?
If the mechanism section is organized mainly as:
- antigen escape
- T cell exhaustion
- microenvironmental suppression
- poor persistence
- relapse-associated factors

but does not answer the core question below:

**How do these failure modes determine the choice of the second sequential strategy?**

then judge that the **mechanism chapter has not formed a decision-making spine**.

### 2. Does it form a “failure mode -> second-step strategy” framework?
Prioritize checking whether the mechanism section can be compressed into a structure like this:

- which failures are target / antigen problems
- which failures are cell-state / persistence problems
- which failures are host-immunity and microenvironment problems
- which failures are window-management and tumor-burden problems
- what kind of second-step logic each failure mode points to: retargeting, remanufacturing, persistence enhancement, bridging to reduce burden, combination immunomodulation, and so on

If the draft does not form a compressed framework of this kind and instead only lists mechanism terms, it must be sent back for rewriting.

### 3. Is the mechanism section written as a causal chain?
Check whether the mechanism paragraphs follow this structure:

**Change after the first treatment -> what new failure mode emerges -> how that failure mode constrains a second response -> why the second step requires a specific strategy**

Unacceptable writing includes:
- merely saying that a factor “is associated with relapse”
- merely saying that a mechanism “affects efficacy”
- merely saying that a pathway “deserves attention”

A qualifying discussion must explain:
- under what conditions it occurs
- which state variable it changes
- why it affects the second treatment
- what it implies for second-step strategy

### 4. Is there a problem of being “mechanistically correct but decision-poor”?
A great deal of mechanism content may be scientifically correct, but if it cannot be turned into:
- a screening logic
- a stratification logic
- a judgment framework for second-step treatment paths

then it is still not truly qualified.

If the mechanism passages are only displaying academic knowledge and do not convert into a judgment framework for sequential therapy, judge that the **mechanistic content is too hollow**.

---

## IV. Clinical-content check

### 1. Is there a clear evidence hierarchy?
The manuscript must clearly distinguish among:
- formal clinical studies
- registered trials
- abstracts / conference reports
- retrospective data
- case reports or small-sample experience
- preclinical or cross-disease inspiration

If evidence of very different strength is written at the same argumentative level, judge that the **clinical-evidence organization is inadequate**.

### 2. Does the clinical section form a decision logic rather than merely piling up studies?
Check whether the clinical paragraphs merely report:
- how a study was conducted
- what a cohort found
- how a particular same-target sequence performed

without going on to answer:
- which patients are better suited to sequential therapy
- which failure modes are better served by same-target sequencing versus different-target sequencing
- in which scenarios bridging is more necessary
- which conclusions already have relatively high transferability and which remain only exploratory signals

If these judgments are missing, judge that the **clinical section reads more like a data digest than an analytical review**.

### 3. Does the `/trials` integration really serve the main text?
If the manuscript includes tables from external clinical-trial retrieval, you must check:
- whether they are highly relevant to the topic
- whether they support specific subheadings rather than floating independently
- whether they distinguish between same-target sequential strategies and different-target sequential strategies
- whether they move beyond information listing to actual comparison and conclusions

If the trial tables are merely appended and do not feed back into the argument of the main text, judge that the **retrieval results have not been integrated deeply enough**.

---

## V. Table check

You must focus on whether the tables merely create a sense of tidy organization.

### Required table: challenges and optimization strategies in sequential therapy
This table must exist, and it must not be a vague “challenge + countermeasure” pairing.

At minimum, the table should reflect most of the following dimensions:
- what the challenge is
- at which stage it occurs
- what type of failure mode it belongs to
- what optimization strategies are possible
- what the current evidence level is
- what the main limitations are

If the table contains only:
- problem
- strategy

as two columns, or if it merely offers common-sense pairings, judge that it shows **insufficient analytical depth**.

### Other table standards
If a table merely reorganizes what is already in the main text, without providing:
- cross-study comparison
- decision cues
- evidence gradients
- applicability boundaries

then you should recommend compressing or remaking it rather than keeping it.

---

## VI. Springer Nature Reviews style comparison

During final-draft checking, in addition to the general structural, mechanistic, and clinical-evidence checks above, you should also compare the manuscript against the common style features of Springer Nature Reviews / the Nature Reviews family. This does **not** mean mechanically imitating the page layout. It means asking whether the manuscript approaches a high-level review standard in the core dimensions of structural tightness, restrained expression, explanation-first writing, and value-added figures/tables.

### 1. Structure-style check

Prioritize the following questions:

- Does the entire manuscript revolve around a small number of core questions, rather than spreading itself across multiple axes at once?
- Does the introduction truly define the manuscript’s scope, rather than merely laying out generic background?
- Do the body sections serve the central thesis, rather than expanding side by side?
- Is the ending a brief closure, rather than a new expansion into additional directions?
- Are the subheadings short, firm, and easy to navigate, rather than long concept-stacking sentences?

If the whole manuscript takes the standard assembled-outline form of “definition + classification + progress + mechanisms + challenges + outlook,” but lacks a through-line that is continuously advanced, it should be judged as not matching the Nature Reviews style.

### 2. Wording and sentence-level check

Prioritize the following questions:

- Does the manuscript use too many abbreviations, technical terms, and stacked initials, making it hard for cross-disciplinary readers to follow?
- Does it spend more time describing what studies did than explaining what those studies mean?
- Does it rely too heavily on safe sentence patterns such as “worth noting,” “more research is needed,” and “cannot be extrapolated directly”?
- Does it contain many abstract renaming sentences without adding mechanistic information or evidence judgment?
- Does it repeatedly rewrite the same core sentence without producing a new analytical increment?

A manuscript that is closer to the Nature Reviews style should instead show:
- precise terminology, but with adequate explanation
- restrained sentences, without forced obscurity
- judgment, but judgment with boundaries
- emphasis on implications rather than paper-by-paper recitation
- unified terminology, avoiding needless synonym churn that creates a fake sense of sophistication

### 3. Text-organization check

Prioritize the following questions:

- Does each paragraph solve only one sub-problem?
- Does the first sentence of each paragraph clearly state that paragraph’s claim?
- Is there a clear internal flow of: proposition -> development -> evidence -> conclusion / transition?
- Has complex material been sensibly moved into figures, tables, or boxes, rather than crammed into the main text?
- Do the tables genuinely help readers understand complexity, rather than merely repeating the text?

If the body text often shows the following:
- multiple parallel conclusions packed into one paragraph
- dense crowds of molecule names, mechanism names, and trial names
- figures and tables that are merely excerpts of the text
- an ending that keeps extending future directions rather than closing the discussion

then it should be judged as not matching a Nature Reviews–style text architecture.

### 4. How to distinguish this from AI style

Pay special attention to the following point during review:
Nature Reviews style is not simply “complete, balanced, and terminology-rich.” It is “readability, judgment, and structural control after editorial compression.”

Therefore, the following cases should **not** be treated as matching the Nature Reviews style, even if they look scholarly on the surface:
- too comprehensive, with too little selection
- too balanced, with too little judgment
- too abstract, with too little mechanistic advancement
- many tables, but limited analytical increment
- a cautious conclusion, but not a hard enough central claim

### 5. Decision rule

If the manuscript performs well in most of the following respects, you may judge it “close to the Nature Reviews style”:
- clear through-line
- progressive chapter structure
- restrained language
- emphasis on explanation and judgment
- controlled use of abbreviations and terminology
- figures and tables that add analytical value
- a concise closing section

If the manuscript mainly looks like this:
- a very full framework
- many tables
- very steady language
- but the through-line is weak, repetition is heavy, and judgment is insufficient

then you should state clearly:

“This manuscript has the outer shape of a review, but it does not yet have Nature Reviews–style structural discipline or post-editing clarity. It should be sent back for rewriting rather than merely polished at the language level.”

---

# Pass / fail decision rules

## Direct pass
Only allow a direct pass when all of the following are met at the same time:
- the through-line is clear and sufficiently strong
- the chapters progress clearly
- the mechanism section forms a “failure mode -> second-step strategy” framework
- the clinical section establishes evidence levels and applicability boundaries
- the tables add analytical value
- the manuscript does not show obvious high-gloss AI-style spinning in place

## Conditional pass
If the problems are concentrated in:
- locally over-abstract wording
- repetition in only a few paragraphs
- insufficient analytical value in one or two tables
- an outlook section that spreads too loosely

then you may provide targeted revision suggestions.

## Fail and send back for rewriting
If any of the following is present, the manuscript must be sent back:
- the structure lacks a strong through-line
- the sections are heavily repetitive
- the mechanism section is only a grab bag of mechanism labels
- the clinical section is only a list of studies
- the evidence hierarchy is confused
- peripheral expansion clearly exceeds what the topic can bear
- the whole manuscript is full of the feel of a “high-quality AI summary,” but lacks judgment

---

# Output format when the manuscript fails

If you judge the manuscript as failing, you must output the following structure:

## 1. Overall conclusion
State clearly:
- This manuscript is not recommended to proceed directly into final-draft form
- The problems are structural defects, not issues that can be solved by language polishing

## 2. The 3 to 5 most serious problems
Each problem must include:
- symptom
- why it creates bloatedness or an AI-like tone
- which sections it affects

## 3. Sections that must be rewritten
List chapter by chapter:
- which chapter must be rewritten
- why it must be rewritten
- what structure it should be changed into
- what must be deleted
- what must be retained

## 4. Rewrite instructions
You must provide executable instructions rather than vague advice. For example:
- “Rewrite the mechanism chapter into a four-part ‘failure mode -> second-step strategy’ framework”
- “Compress the solid-tumor and platform-technology material into the end of the outlook section; do not let it occupy major body chapters”
- “Reorganize the clinical studies by evidence tier, prioritizing formal clinical studies and clearly registered studies”
- “Delete repeated conceptual sentences; keep the first definition, then drive the argument forward directly”
- “Redo the ‘Challenges and optimization strategies in sequential therapy’ table, adding columns for failure mode, stage, evidence level, and limitations”

## 5. Re-review requirements
State clearly:
- After rewriting, this checking skill must be run again
- The manuscript must not proceed to final-draft merge until it passes

---

# Output format when the manuscript passes

If the manuscript passes, you still may not simply say “overall it is good.”

You must output:
- the reasons it passes
- the parts that still need minor adjustment
- which paragraphs still carry a mild AI-like tone
- which tables could still be strengthened analytically
- whether a cut-to-tighten polishing pass is recommended

---

# Special requirements

## 1. Do not be fooled by comprehensiveness
Broad coverage is not a virtue in itself.
As soon as peripheral expansion damages the through-line, it must be judged as a problem.

## 2. Do not be fooled by balance
Careful phrasing is not a synonym for maturity.
If the entire manuscript refuses to make judgments, that is a problem.

## 3. Do not mistake conceptual clarity for mechanistic solidity
Mechanistic content counts as qualified only when it truly converts into second-step strategy logic.

## 4. Do not use “just polish it a bit more” to hide structural problems
Any structural problem must be sent back for rewriting.

---

# Final task goal

Your ultimate goal is not to help the author prove that the manuscript is already decent,
but to help the author identify:

- which parts merely **look like a review**
- which parts truly make it a **good review**
- which parts feel bloated because of AI style
- which chapters must be sent back for rewriting so the manuscript can move from “complete” to “convincing”

As long as obvious structural defects exist, you must choose to send the manuscript back for rewriting rather than approving it leniently. When performing the final-draft check, refer to `bad-examples.md` in the same directory. If the current manuscript shows structural symptoms that closely resemble the bad examples, you should prioritize judging it as needing to be sent back for rewriting.
