---
name: review-response
description: Draft point-by-point responses to peer review comments. Locates supporting evidence from workspace papers and the original manuscript. Use when the user receives reviewer feedback and needs to write a rebuttal or revision response letter.
---

# Response to Reviewers

Draft point-by-point responses to reviewer comments, locating supporting evidence from workspace papers and the original manuscript.

## Prerequisites

The user provides:
1. **Reviewer comments**: pasted inline or as a file path
2. **Original manuscript**: a paper draft in the workspace or a file path
3. **Workspace**: the associated literature workspace (for retrieving supporting evidence)
4. **Language**: English or Chinese (the response letter typically matches the manuscript language)

## Execution Logic

### 1. Parse Reviewer Comments

Split the reviewer comments into individual items and categorize each:
- **MAJOR**: requires substantive changes (additional experiments, revised methods, further analysis)
- **MINOR**: wording changes, formatting adjustments, clarifications
- **POSITIVE**: positive feedback (acknowledge with thanks)
- **QUESTION**: questions that need an answer

### 2. Address Each Comment

For each comment:
1. Understand what the reviewer is fundamentally asking for
2. Locate the relevant passage in the manuscript
3. Search the workspace literature for supporting evidence:
   ```bash
   autor ws search <name> "<keywords from reviewer concern>"
   autor show <dir_name> --level 3      # read conclusion for evidence
   autor show <dir_name> --level 4      # read full text if needed
   ```
4. Find additional support from the citation graph:
   ```bash
   autor refs "<id>"                    # references of relevant papers
   autor usearch "<supplementary keywords>"  # search full library
   ```

### 3. Draft the Response

Structure for each response item:

```
> **Reviewer X, Comment N:** [original comment quoted]

**Response:** [response text]

[If revised] **Revision:** We have revised Section X.X as follows: "..." (Page X, Line X)
```

Response strategies:
- **Agree and revise**: clearly state what was changed and where
- **Partially agree**: acknowledge the valid point, explain why full adoption is not appropriate, and provide evidence
- **Respectful rebuttal**: support your position with data and literature; remain professional but firm
- **Additional experiments/analysis**: describe the new content and results

**Multi-modal support**:
- When a reviewer questions a figure, read the original image from the paper (`images/`) and re-analyze
- When a reviewer questions a numerical value, write Python code to independently reproduce the calculation and use the output as evidence
- When a reviewer questions a derivation, read the relevant formulas from the paper and verify step by step

### 4. Output

- Save the response letter to `workspace/<name>/response-letter.md`
- If new papers need to be added to the workspace:
  ```bash
  autor ws add <name> <dir_name>
  ```

## Writing Principles

- **Address every comment without exception**: every item must receive a clear response
- **Evidence first**: answer with data and literature wherever possible; avoid empty rhetoric
- **Professional tone**: thank the reviewers for constructive feedback; remain respectful even when disagreeing
- **Traceable revisions**: clearly indicate the location of changes (Section, Page, Line)
- **Don't sidestep weaknesses**: if the reviewer has identified a genuine problem, acknowledge it honestly and explain how it has been addressed

## Examples

User says: "The review is back; help me write the response letter."
→ Parse comments, categorize, find evidence in the workspace for each, draft responses

User says: "Reviewer 2 says my method is no different from Smith (2023). How do I respond?"
→ Find Smith (2023) in the workspace, compare the methods, draft a well-reasoned rebuttal
