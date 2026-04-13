# PROJECT_CONTEXT.md

## Project summary
Amonora is a broader ecosystem. Amonora is the current primary outward product surface.
The system is centered around VPN access distribution, subscription management, user support, and administrative control surfaces.

## Main system contours
- `bot` — primary user entry point
- `support_bot` — support communication and support flows
- `landing` — public web surface
- `dashboard` — active admin/backend/API layer, includes legacy UI responsibilities
- `dashboard/ui` — newer admin UI layer
- `backend` — shared domain logic, models, and system core
- `PostgreSQL` — primary source of truth for persistent product data
- `ops` — deployment/runtime/infrastructure support
- `backups` — operational backup artifacts and related support materials

## Current architectural reality
The codebase is not yet fully normalized.
Important domain logic is still distributed across multiple components, especially:
- `backend`
- `bot`
- `dashboard`
- `support_bot`

This is expected and must be respected during changes.

## Key transition areas
- `dashboard` and `dashboard/ui` coexist
- documentation is becoming canonical, but runtime truth must still be checked against real deployment
- some operational assumptions require verification against production configs

## Priority goals
1. Preserve working behavior
2. Improve clarity of structure
3. Reduce architectural ambiguity
4. Make changes safer for both humans and AI agents
5. Move toward smaller, well-scoped tasks instead of broad refactors

## What success looks like
- clear understanding of active vs legacy surfaces
- safe feature work without breaking inter-component flows
- documentation stays aligned with implementation
- AI agents can work from written context instead of guessing
