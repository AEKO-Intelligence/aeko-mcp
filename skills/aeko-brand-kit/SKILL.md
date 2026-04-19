---
name: aeko-brand-kit
description: >
  View and edit the Brand Kit for an AEKO domain — brand description,
  persona, competitors, viewpoint, writing style, tone, writing guidelines,
  CTA text + link, and sample URLs / headlines / bodies. Surfaces the
  current snapshot_version + updated_at so users can see freshness.
  Bumps version on every write. Launch pad to competitive-research
  when editing the competitors field.
argument-hint: "<domain-id> [view|edit]"
allowed-tools: aeko_get_brand_kit, aeko_update_brand_kit, aeko_get_domain_info
---

# AEKO Brand Kit

> ⚠️ **Stage-1 preview.** Depends on new tools `aeko_get_brand_kit` / `aeko_update_brand_kit` (see `docs/contracts/action-item-contract.md`). Not runnable until Stage 1 tool stubs land.


Manages the live Brand Kit consumed by Plan.md and guide.md generation. The live kit is the source of truth; Plan.md snapshots point back at a `snapshot_version`. Every edit here bumps the version — downstream `aeko-run-action` / `aeko-fix-technical` runs will warn if their plan is older than the live kit.

Contract reference: `docs/contracts/action-item-contract.md` (`AekoBrandKit`, `AekoBrandKitUpdate`).

## Inputs

- `domain-id` (required) — UUID.
- mode (optional, default `view`):
  - `view` — print the full kit with version + updated_at
  - `edit` — interactive edit of one or more fields

## Step 1 — Resolve the domain

If `$1` missing, ask the user. If provided but not a UUID, call `aeko_get_domain_info` to confirm.

## Step 2 — Read the live kit

Call `aeko_get_brand_kit(domain_id)`. Render:

```
Brand Kit — <domain_id>
Snapshot version: <snapshot_version>
Last updated:     <updated_at> (<relative>)

Brand description: …
Persona:           …
Competitors:       [a, b, c]
Viewpoint (관점):   …
Writing style:     …
Tone:              …
Writing guidelines:
  - …
CTA text:          …
CTA link:          …

Sample URLs:       …
Sample headlines:  …
Sample bodies:     …

Locale:            …
Target countries:  …
Target languages:  …
```

Fields that are null/empty show as `(unset)` — never hide missing fields; missing fields are what the user should consider filling in.

## Step 3 — If mode is `view`, stop here.

Offer two follow-ups at the bottom of the output:
- "Run `/aeko-brand-kit <domain_id> edit` to change fields."
- "Run `/competitive-research <competitor>` for any competitor listed above."

## Step 4 — If mode is `edit`, gather changes

Ask which fields the user wants to change. Accept multiple at once. Every field in `AekoBrandKitUpdate` is optional and PATCH-style — omitted fields are preserved server-side.

For list fields (`competitors`, `writing_guidelines`, `sample_urls`, `sample_headlines`, `sample_bodies`):
- Ask whether the user wants to REPLACE the list or APPEND.
- Replace → send the full new list.
- Append → fetch current list from Step 2's kit, concat, send the full merged list. (Backend does not support append-patch; do the merge client-side.)

Validate before sending:
- `cta_link` — must be an absolute URL. If missing scheme, prepend `https://`.
- `competitors` — de-duplicate case-insensitively; strip whitespace.
- `sample_urls` — must all be URLs; drop invalid entries with a warning.

## Step 5 — Write the patch

Call `aeko_update_brand_kit(domain_id, fields=<patch>)`. Server returns the full updated `AekoBrandKit`.

Show a short diff-style summary:

```
Updated Brand Kit — <domain_id>
Snapshot version: <old> → <new>
Changed: tone, competitors (+2), writing_guidelines (replaced)
```

Then re-print the relevant updated sections (not the whole kit unless asked).

## Step 6 — Competitor research launch

If the user added or edited competitors, offer:
- `/competitive-research "<competitor_name>" --domain-id <domain_id>`
so they can deep-dive one in the next turn.

## Error paths

- `aeko_get_brand_kit` returns not-found → suggest the domain may not be provisioned; show domain info via `aeko_get_domain_info`.
- `aeko_update_brand_kit` returns 4xx with a field error → print the field + reason; do not re-send blindly.
- Backend stub (tool unavailable) → tell the user the Brand Kit endpoints aren't wired yet; stop.

## What this skill never does

- Never calls `aeko_get_action_plan` / `aeko_get_technical_guide`.
- Never calls `aeko_complete_item` or any store-write tool.
- Never generates artifacts. Brand Kit editing only.
