# TASK 108 — Denmark Golden Node Hardening and Safe Fleet Baseline

## Status
Completed

## Goal
Make Denmark the current golden anti-DPI node, while applying only safe baseline hardening to Germany and Estonia without forcing the old `3x-ui` regions into a new transport model.

## Why
Task `105` made Denmark operational as a standalone `Xray core` node and task `106` integrated Denmark into the product flow through a provider seam, but the wider fleet still lacked:

- a documented golden-node policy;
- a safe cross-fleet baseline for sysctl / limits / firewall;
- official client routing packs with MTU guidance;
- a persistence-safe torrent-block posture across both standalone `Xray` and `3x-ui` nodes.

## Scope
- harden Denmark as the only `VLESS + Reality + XHTTP` golden node in this pass;
- keep Germany as the compatibility route;
- keep Estonia reserve-only and not user-facing;
- apply safe host-level baseline to `DK/DE/EE`;
- keep torrent block active on all nodes;
- document and publish official client packs;
- update operational docs and operator knowledge surfaces.

## Out of scope
- fleetwide migration of Germany or Estonia to standalone `Xray core`;
- making Denmark the default route for all users without compatibility validation;
- removing Germany fallback;
- changing the public service topology outside the documented baseline.

## Constraints
- Denmark stays standalone `Xray core`
- Germany and Estonia stay `3x-ui`-backed
- Denmark is the only node that gets full `XHTTP/HTTP3` hardening in this pass
- Germany and Estonia receive only safe baseline hardening plus torrent-block persistence
- operator-facing evidence must include backups, runtime proof, client packs, and rollback references

## Validation
- Denmark runtime shows the intended primary and reserve profiles
- Germany and Estonia keep working on `3x-ui` while retaining persistence-safe torrent blocking
- official client pack JSON artifacts exist and parse cleanly
- docs/knowledge surfaces reflect the current DK/DE/EE posture
- final operator report includes a completion table with evidence
