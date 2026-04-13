# TASK 030 — One-click restore script

## Status
Completed

## Goal
Create a single local operator script that performs the PostgreSQL restore drill end-to-end with one command.

## Why
The project already has:
- local off-host backups for core PostgreSQL
- local off-host backups for VPN node `3x-ui` artifacts
- daily local automation for both backup paths
- a verified manual local PostgreSQL import drill

The next useful ops-hardening step is to remove manual restore-drill choreography and make the PostgreSQL validation path repeatable with one local command.

## Scope
- local machine only
- PostgreSQL restore drill only
- temporary Docker PostgreSQL container
- automatic restore checks after import
- no production changes

## Out of scope
- no server changes
- no production restore
- no VPN service restore automation
- no scheduler automation for restore drills
- no cloud backup work

## Deliverables
- one local PowerShell restore script
- updated local restore recipe
- task result note with verified execution output
