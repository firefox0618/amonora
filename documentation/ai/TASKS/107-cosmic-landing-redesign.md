# TASK 107 — Cosmic Landing Redesign

## Status
In progress

## Goal
Rebuild the public `amonoraconnect.com` landing into a cinematic ultra-short surface that presents `Amonora Connect` as a product of the broader `Amonora` ecosystem rather than as a generic VPN site.

## Why
The existing landing had already moved toward clearer client language, but it still read like a conventional SaaS/VPN page:

- too many sections competing for attention;
- copy that felt longer and more explanatory than the product positioning needed;
- visual hierarchy that undersold the ecosystem / technology angle;
- a mobile hero that needed calmer, more intentional composition.

The new public direction is:

- dark cosmic atmosphere;
- neon blue / violet glow;
- planet + orbit + digital network motif;
- CTA-first structure;
- fast 3-second scanning;
- public copy that hides protocol names behind an automatic connection narrative.

## Scope
- rebuild `landing/templates/index.html` around:
  - topbar
  - hero
  - marquee
  - three essence cards
  - automatic connection section
  - locations section
  - final CTA
  - footer
- update `landing/main.py` context to the new ultra-short content model;
- replace the public landing visual system in `landing/static/landing.css`;
- update `landing/static/landing.js` hover/parallax behavior for the new scene;
- keep legal pages and cookie consent functionality working;
- update product/docs state for the new public surface.

## Out of scope
- backend/API changes;
- payment flow changes;
- bot flow changes;
- legal document content changes;
- pricing/tariff behavior changes.

## Constraints
- public landing must keep only Germany and Denmark as visible locations;
- public copy must not expose `VLESS`, `Trojan`, or `TLS` as first-class landing content;
- `Amonora` must read as the ecosystem and `Amonora Connect` as the product;
- the page must remain mobile-safe and not use heavy WebGL/canvas rendering;
- legal pages and cookie UI must survive the redesign.

## Validation
- `/` still renders successfully;
- hero, marquee, automatic connection, locations, and final CTA are present;
- no old public wording about primary/reserve nodes remains on the main page;
- legal pages still render using the shared stylesheet;
- cookie banner/modal still works;
- landing-specific smoke strings exist:
  - `AMONORA NETWORK`
  - `Автоматическая система подключения`
  - `Германия`
  - `Дания`
