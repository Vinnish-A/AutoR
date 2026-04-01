# Bad Examples for `review-final-check-zh`

This file is not an emotional attack, nor is it a negative judgment on any specific author or paper.
Its purpose is to provide **anti-patterns** for the final-check skill, helping the agent recognize review drafts that:

- look complete
- are neatly structured on the surface
- seem very good at summarizing concepts
- yet still feel **bloated, strongly AI-like, and weak in judgment**

How to use it:
- If the manuscript under review is highly similar to any of the bad examples below, prioritize judging it as **needing to be sent back for rewriting**
- Do not settle for surface-level polishing
- You must identify the structural problems and require revision according to explicit rewrite instructions

---

# Bad Example A: The overextended mechanistic review

## Pattern name
**The overextended mechanistic review**

## Typical topic profile
Common in topics such as:
- a broad biological process + a class of organelles / pathways / metabolic modules
- for example: mitochondrial quality control and transfer, metabolic reprogramming and drug resistance, inflammation and immune escape

These manuscripts often begin from what looks like a strong angle, but when they unfold, they spread across too many dimensions at once and lose the main thread.

---

## Main symptoms

### 1. Too many classification axes are expanded at the same time
The full manuscript is often organized simultaneously by several dimensions such as:
- mechanism modules
- stages of a biological process
- organs or microenvironments
- cancer types or disease types
- therapeutic implications

The result is that every dimension matters, but each can only be treated shallowly.
The article turns into a **taxonomy review** rather than a **mechanistic review**.

### 2. The framework gets broader and broader, but the argument does not sharpen with it
The table of contents may look extremely complete, for example:
- basic mechanisms
- stage-specific roles
- organ specificity
- cross-cancer comparison
- bidirectional regulation
- therapeutic opportunities
- future directions

Each heading may be reasonable in isolation, but taken together, if there is no real central proposition governing the whole manuscript, the review will feel like it “covers everything, but never really works through the most important question.”

### 3. The chapters do not progress; they restate the same point on a new axis
A central sentence introduced earlier keeps getting restated later under new classification axes, for example:
- it is stated once in the stage section
- then restated differently in the organ section
- then restated again in the cancer-type section
- then abstracted again in the conclusion

The reader feels that the content is moving, but the underlying argument is not actually advancing.

### 4. The mechanism section becomes a sampler platter of module labels
For example, the manuscript keeps invoking:
- dynamics
- mitophagy
- biogenesis
- proteostasis
- stress adaptation
- redox buffering

but never compresses them into a few causal propositions that can genuinely explain phenotypes.
The review remains stuck at the middle layer of “module -> function,” without making clear:
- what stressor triggers the process
- through what executor it works
- which state variable changes
- why it leads to a specific metastatic or drug-resistant phenotype

### 5. Evidence strength is not pulled apart clearly enough
Common manifestations:
- established causal findings
- trend-level support
- author inference
- plausible hypotheses

are all written in the same tonal register.
The result may look balanced on the surface, but it lacks evidence stratification, so it easily creates the impression that “AI is smoothing everything onto the same plane.”

### 6. There is too much abstract naming and conceptual packaging
Common sentence types include:
- “Its essence is not ... but ...”
- “It should be better understood as ...”
- “It forms an integrated control system”
- “It reflects a stage-specific logic of adaptation”
- “It reveals a framework of dynamic remodeling control”

None of these sentences is necessarily wrong on its own, but when too many of them appear without increasing mechanistic granularity, the text starts to feel as if it is repeatedly giving new names to the same phenomena.

---

## Why this kind of manuscript feels grand but hollow

### Reason 1: It tries to cover every relevant dimension
The author does not want to cut anything that seems related, so the **scope of coverage** exceeds the manuscript’s **capacity to sustain a real argument**.

### Reason 2: The main thread has not been compressed into a small set of core propositions
If the full manuscript cannot ultimately converge into 2–4 mechanistic propositions, then even the most complete table of contents is only an information panorama.

### Reason 3: There are too many abstract sentences and too few hard mechanisms
The reader gains a sense of framework, but not enough causal chains or real judgments.

### Reason 4: The review has been written as high-level organization rather than scholarly adjudication
The text is good at arranging concepts, but not good enough at selecting, ranking, excluding, and adjudicating evidence.

---

## The strongest AI-like warning signs

If a mechanistic review shows the following combination of signals, treat it with great caution:

- there are many subheadings, and every one of them looks reasonable
- the text repeatedly emphasizes “not A but B”
- it repeatedly emphasizes “context-dependent”
- it frequently uses phrases like “an integrated system” or “dynamic interplay”
- it mentions many modules, but seldom writes out a full causal chain
- when it handles conflicting literature, it only says that “results differ” without explaining why
- the ending often re-abstracts the earlier sections instead of compressing them into testable propositions

---

## Typical consequences of this writing style

- readers feel that “this review is very comprehensive”
- but they still cannot say what its strongest judgment is
- no chapter is outright wrong, but no chapter feels central either
- the mechanism section looks scholarly, yet its explanatory power is weak
- in the end, it reads like a **polished AI review** rather than an **authorial review shaped by difficult choices**

---

## How to decide that it fails during final checking

If any of the following is present, prioritize judging the manuscript as **send back for rewriting**:

1. It expands along 3 or more major classification axes simultaneously, but without a clear primary axis  
2. Chapters restate instead of progressing  
3. The mechanism section cannot be compressed into a few causal propositions  
4. There is no explicit evidence stratification  
5. Abstract naming clearly outnumbers mechanistic advancement  
6. The conclusion mainly “elevates and re-summarizes” rather than adjudicating evidence

---

## The correct fix

### Fix 1: Cut one or two dimensions
If the manuscript is already organized by stage, then organs and cancer types should not also become major body sections.
One or two of those dimensions can instead be downgraded into a **modifier layer** or a **context note** at the end of each section.

### Fix 2: Compress the whole manuscript into 2–4 central mechanistic propositions
For example:
- Which state variable is the real bottleneck?
- Which process determines early survival?
- Which process determines later expansion?
- Which dependencies are stage-specific rather than universal?

### Fix 3: Force every section to be written as a causal chain
Every section must include:
- trigger condition
- regulatory node
- execution process
- state-variable change
- phenotypic output
- evidence level
- boundary conditions

### Fix 4: Write organ / cancer-type differences as “why this proposition changes here”
Do not open a whole new chapter just to retell the same argument from the beginning.

### Fix 5: Handle conflicts explicitly
Do not simply say that “heterogeneity exists.” Instead, explain:
- differences in stage
- differences in readout
- differences in model
- confusion between flux and marker
- differences between acute and chronic perturbation

---

## One-sentence summary of this bad example
**It looks like an advanced mechanistic review, but it is really a stack of multi-axis classification schemes; the bigger the framework gets, the blurrier the main thread becomes.**

---

# Bad Example B: The “complete but unfocused” sequential-therapy review

## Pattern name
**The complete but unfocused sequential-therapy review**

## Typical topic profile
Common in topics such as:
- the concept and research progress of a treatment strategy
- especially when the manuscript tries to cover all of the following at once:
  - concept definition
  - classification
  - clinical-study synthesis
  - mechanistic explanation
  - challenges and future directions

For example:
- sequential CAR-T therapy
- combination immunotherapy pathways
- bridging-treatment strategies
- progress in second-line / third-line immunotherapy regimens

These topics are very easy to write in a way that feels “extremely complete,” yet still lacks a real argument.

---

## Main symptoms

### 1. It has a complete outer shape, but no real central judgment
The table of contents often looks perfectly standard:
- definition
- classification
- clinical progress
- mechanisms
- challenges
- future directions

But after finishing the manuscript, the reader still cannot clearly say:
- what the core conclusion of the review actually is
- what judgment it adds beyond a generic background summary
- which route the author truly thinks is most promising, and which routes should be downgraded

### 2. It keeps repeating the central sentence, but never derives anything from it
For example, the same judgment keeps coming back:
- “Sequential therapy is not simple repetition of treatment”
- “The second-step decision should be made using the new information generated after the first treatment”
- “The key is to respond to the newly emerged failure mode”
- “The second-step design should target the new pathological state created after the first treatment”

These are good sentences in themselves. But if they are repeated across several chapters without advancing toward:
- how failure modes should be typed
- which second-step strategy matches which failure mode
- what evidence supports which strategy
- which routes are still immature

then the whole manuscript ends up sounding like “the same idea rephrased over and over.”

### 3. The clinical section reads like a research compilation rather than an analytical review
Typical symptoms:
- one batch of same-target studies
- one batch of different-target studies
- one batch of bridging / integration studies
- another batch split by disease type
- then another batch from external trial retrieval

But it still does not converge into answers such as:
- which kinds of patients are better suited to which sequencing strategy
- which failure modes support same-target sequencing versus different-target sequencing
- which signals are still only exploratory
- which conclusions already show relatively high transferability

### 4. The mechanism section reads like “an overview of CAR-T failure mechanisms,” not “a mechanism chapter for sequential decision-making”
The mechanism chapter often lists:
- antigen escape
- T cell exhaustion
- microenvironmental suppression
- poor persistence
- tumor burden and bridging windows

All of these are relevant. But unless they are further compressed into:
**failure mode -> choice of second-step strategy**

then the result is only a **background mechanism review**, not a **mechanistic review that actually serves sequential-treatment decisions**.

### 5. It likes to pull in a large amount of peripheral material
Common directions of expansion include:
- solid-tumor inspiration
- CAR-NK
- SynNotch
- mRNA platforms
- nanodelivery
- checkpoint blockade, radiotherapy, macrophages, microglia, brain lymphatic drainage, and so on

None of these topics is forbidden. But if the link between them and the **decision-making through-line of sequential therapy** is weak, they dilute the center of gravity of the manuscript.

### 6. There are many tables, but some of them only create a sense of tidy organization
For example, the main text is reformatted into columns like:
- study
- features
- results
- risks
- strategies

This looks rich, but unless the table additionally provides:
- cross-study comparison
- evidence gradients
- applicability boundaries
- failure-mode mapping
- decision cues

then the table merely makes the manuscript look more like a “complete review” without truly adding analytical depth.

---

## Why this kind of manuscript feels grand but hollow

### Reason 1: It wants to include everything, so the central issue keeps getting diluted
It tries to include concepts, classifications, trials, bridging, mechanisms, and future platforms all at once, so the manuscript’s outward scope becomes larger than the firmness of its conclusions.

### Reason 2: It mistakes completeness for persuasiveness
A complete structure, rich tables, and many trials do not automatically produce a stronger argument.
If the through-line does not run through the whole manuscript, completeness only makes the loss of focus worse.

### Reason 3: It is too good at cautious phrasing and not good enough at making judgments
If the manuscript relies mainly on statements like:
- worth noting
- conceptually feasible
- the route is not yet fixed
- more research is needed
- cannot simply be extrapolated

to preserve balance, it may sound careful, but it also sounds like a text that “offends nobody and stakes nothing.”

### Reason 4: It keeps renaming phenomena without continuously increasing analytical density
For example, it may keep redefining sequential therapy as:
- “post-treatment redirection”
- “responding to new failure modes”
- “not repetition, but reconstruction of the second step”
- “redesign based on a new pathological state”

All of these formulations can be valid. But if they are not turned into an actionable framework for clinical stratification, the manuscript is only spinning in place.

---

## The strongest AI-like warning signs

If a sequential-therapy review shows the following traits, treat it with great caution:

- it is very good at defining boundaries and terminology
- it is very good at writing “not A but B” conceptual sentences
- it is very good at balancing different research directions
- it is very good at making tables and summaries
- it often reminds the reader that “evidence is still limited”
- but it is reluctant to rank what matters more, what is more mature, and what should be downgraded
- the mechanism chapter reads very much like textbook background
- the ending often returns to high-level generalities such as “future work will require multidimensional integration and more precise stratification”

---

## Typical consequences of this writing style

- the manuscript looks very much like a “mature review”
- but readers still end up asking: so what clinical framework are the authors actually arguing for?
- each chapter is reasonable, yet no strong central axis emerges
- there are many trials and mechanisms, yet they do not collapse into a decision logic
- the manuscript reads like **high-quality synthesis and organization** rather than **an analytical review with real adjudicative force**

---

## How to decide that it fails during final checking

If any of the following is present, prioritize judging the manuscript as **send back for rewriting**:

1. The manuscript cannot be compressed into 1–2 strong claims  
2. Multiple chapters keep repeating a central sentence such as “sequential therapy is not simple repeat treatment”  
3. The mechanism chapter has not been converted into “failure mode -> second-step strategy”  
4. The clinical section mainly piles up studies, without applicability boundaries or a decision framework  
5. Peripheral material clearly exceeds what the topic can bear  
6. The tables add tidiness, but not judgment  
7. The manuscript has more caution than adjudication

---

## The correct fix

### Fix 1: First compress the whole manuscript into two sentences
For example:
1. The essence of sequential therapy is a second-step intervention after the failure pattern has been redefined by the first treatment  
2. The value of the second step lies not in treating again per se, but in whether it responds to the newly formed failure mode

Every chapter in the manuscript must serve these two sentences.

### Fix 2: Rewrite the mechanism chapter into a “failure mode -> second-step strategy” framework
At minimum, it is recommended to organize it by:
- antigen / target-dominant failure
- persistence / cell-state-dominant failure
- microenvironment / host-immunity-dominant failure
- high-tumor-burden and window-management-dominant failure

For each category, the manuscript must answer:
- how the failure forms
- why it affects the second treatment
- what strategies are better suited to the second step

### Fix 3: Reorganize the clinical studies by “evidence tier + applicable scenario”
Do not just list studies.
You must clearly distinguish among:
- formal clinical studies
- registered trials
- small-sample or exploratory data
- preclinical / external inspiration

And you must explain:
- which evidence supports same-target sequencing
- which evidence supports different-target sequencing
- which lines of evidence still cannot support stable conclusions

### Fix 4: Compress the peripheral material
Topics such as solid-tumor inspiration, platform technologies, and future combinations should be kept only as:
- a short outlook subsection
- or a brief supplement at the end of the mechanism / future-directions section

They must not occupy major body chapters.

### Fix 5: Redo the key tables
In particular, the table on “Challenges and optimization strategies in sequential therapy” must contain at least:
- challenge
- the associated failure mode
- stage of occurrence
- corresponding optimization path
- current evidence level
- major limitations

Otherwise, the table is only a common-sense “challenge–countermeasure” pairing.

---

## One-sentence summary of this bad example
**The outer shape is complete, the material is rich, the tables are plentiful, and the tone is cautious, but the through-line is not hard enough and the mechanisms are not translated into decisions, so the result looks like an AI review that is very good at organizing material.**

---

# Unified rules for using bad examples during final checking

When the manuscript under review closely resembles any of the patterns above, do not lower the bar just because it reads smoothly, seems comprehensive, or includes many tables.
Instead, ask first:

1. What is the single strongest claim of this manuscript?  
2. If all the abstract summary sentences were deleted, how many hard judgments would remain?  
3. Does the mechanism section truly guide decision-making?  
4. Does the clinical section truly establish stratification and applicability boundaries?  
5. Do the tables provide analytical value that the main text does not already provide?  
6. Is there a problem where the “feeling of high-quality organization” outweighs real adjudicative force?

As long as several of these questions receive a negative answer, the judgment should be:
**The manuscript is not unpublishable, but in its current form it is not yet established enough; it must be sent back for rewriting.**
