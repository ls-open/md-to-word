---
title: "Native Markdown-to-Word for AI-Assisted Writing"
author: [Jane Doe, John Smith]
bibliography: refs.bib
---

%% Abstract Title Abstract

%% Abstract Academic writing in the age of AI assistants needs a text-first source of truth. This demo shows the same manuscript compiled to a publication-ready Word file: numbered headings, a three-line table, a captioned figure, a centred equation with a right-aligned number, and an automatically generated bibliography.

%% Keywords Markdown, Word, typesetting, citations, reproducible research

# Introduction

Writing with an AI assistant means writing in Markdown: plain text, versioned in Git, diffable line by line [@smith2024]. The deliverable, however, is still a `.docx` that a journal or an institution will accept [@doe2023]. This demo is the shortest path between the two.

# Method

The pipeline reads a fixed Markdown dialect, builds a document model, and writes OOXML directly — no external binary is called. Citations come from a `.bib` file and a CSL style; everything else comes from a plain-text requirements file.

%% Table Caption Table 1. What each input file contributes

| Input | Role | Edited by |
|:--|:--|:--|
| `paper.md` | content and structure | the author |
| `refs.bib` | bibliography entries | reference manager |
| `requirements.txt` | fonts, spacing, page setup | the institution |

%% Table Note Note. Only the first row is written by hand; the bibliography is generated.

## Equations and cross-references

The model is deliberately simple:

$$y = \beta_0 + \sum_{k} \beta_k x_k + \varepsilon$$ {#eq-model}

As shown in @eq-model, the relation is linear in the coefficients.

![](figures/pipeline.png){width=12cm}

%% Image Caption Figure 1. From Markdown source to a Word deliverable

# Discussion

Two properties matter more than any single feature. First, the source stays readable: a paragraph is one line, and a style is a line prefix, so nothing has to be remembered beyond `#` and `%%`. Second, the result is deterministic: the same inputs produce the same document, which is what makes a diff meaningful [@lee2022].

%% References Title References
