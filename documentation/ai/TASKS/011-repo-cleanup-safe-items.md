# TASK 011 — Repo cleanup safe items

## Status
Completed

## Goal
Perform a safe cleanup pass on clearly non-architectural, non-runtime repository clutter.

## Why
The repo is becoming more structured, but local artifacts, duplicate notes, and old organization layers still create noise.

## Context
Relevant docs:
- `documentation/REPO_RULES.md`
- `documentation/INDEX.md`
- `documentation/ai/PHASES.md`
- `documentation/ai/STATE.md`

Potential targets:
- temporary docs
- local artifacts
- obsolete note layers
- residual imported structure

## Current behavior
The repository contains both canonical docs and leftover auxiliary layers.

## Desired behavior
The repository should retain:
- canonical docs
- operational docs
- strategy/product docs
- business docs
- AI task workflow

And reduce:
- duplicate indexing
- obvious clutter
- misleading legacy entry points

## Scope
- identify safe cleanup candidates
- remove or archive clearly non-canonical clutter
- update indexes if needed

## Out of scope
- broad code moves
- risky deletions
- changing runtime assets

## Constraints
- archive before deleting when in doubt
- do not remove files that still serve as historical references without replacement

## Risks
- deleting context too early
- breaking references between docs

## Acceptance criteria
- safe cleanup candidates are processed
- canonical entry points remain clear
- archive references remain understandable

## Validation
Manual review:
- no important doc path became orphaned
- no runtime config was affected

## Deliverables
- cleanup pass
- updated doc index if needed
- short cleanup summary
