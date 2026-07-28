# ADR-0025 — Hermes profiles share through `edge_group`

**Status:** Accepted
**Date:** 2026-07-28

## Context

Hermes isolates profiles under separate configuration directories, while Edge already uses
`edge_group` as the network in which an installation exposes learned knowledge. The Hermes
adapter must preserve profile isolation without inventing a second ACL or changing the other
surfaces.

## Decision

Hermes resolves one effective `edge_group` per profile:

1. `~/.hermes/config.yaml` supplies the value for the default profile.
2. `~/.hermes/profiles/<profile>/config.yaml` supplies the value for that named profile.
3. An absent `edge_group` disables Edge in that profile.
4. A present empty value means `origin-only` for that profile.
5. A non-empty value names an existing Edge exposure network. Every string has identical
   semantics: `global`, if used, is merely a group whose name happens to be `global`.
6. Legacy Hermes sessions without `profile_name` belong to `default`.

`origin-only` resolves to a profile-private network. Two profiles with empty `edge_group` do not
share knowledge.

Physical Edge state and cursors remain shared. At the Hermes ingestion seam, evidence keeps the
existing Hermes `profile_name` from its source session and the resolved `edge_group`. No new
configuration variable or parallel profile identity is introduced.

A derived artifact receives the most restrictive classification among its evidence. Global or
named-group evidence combined with `origin-only` remains `origin-only`. Evidence from two
different `origin-only` profiles must not be consolidated; the conflict is recorded.

At Hermes gateway startup, reconciliation compares every profile configuration with the installed
Edge state. A newly configured profile receives the Edge skill wrappers. A changed `edge_group`
migrates only artifacts linked exclusively to sessions from that `profile_name`; mixed-profile
artifacts remain in their previous group.

Removing the `edge_group` key disables Edge for that profile. Reconciliation removes that
profile's Edge skill wrappers and deletes Edge memories and derived artifacts linked exclusively
to its sessions. Mixed-profile artifacts and the original Hermes sessions remain intact.

## Consequences

- Hermes profiles using the same non-empty group name share the same Edge network.
- An empty override isolates one profile without adding configuration variables.
- Provenance cannot be reconstructed only at recall time; it must survive the full
  `sweep → event log → consolidation → memory` path.
- Group changes need no daemon or gateway startup hook.
- Disabling a profile is destructive for its exclusive derived Edge knowledge, but never for its
  Hermes source sessions.
- Claude, Codex, and Grok behavior is unchanged.

## Rejected

- One Edge installation per Hermes profile: duplicates state and cursors.
- New profile or exposure configuration variables: duplicate `edge_group` and `profile_name`.
- Stamping only final memories: loses provenance during consolidation.
- Automatic promotion from `origin-only` to a named group: leaks restricted evidence.
