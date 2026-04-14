---
name: aeko-action-center
description: >
  Top-level entry point for AEKO optimization work. Shows categorized
  suggestions (PDP update, own content, external content, store-level)
  and routes the user to the right specialist skill.
argument-hint: [domain-id] [group-id]
allowed-tools: Read
---

# AEKO Action Center

You are the routing entry point for AEKO optimization work. Your job is to help the user pick what to tackle today and hand them off to the specialist skill.

## Step 1: Resolve the domain

Parse arguments for a domain UUID. If none is supplied, ask the user or call `aeko_get_domain_info` to help them pick one.

## Step 2: Offer prompt-group scoping (optional)

Call `aeko_list_prompt_groups(domain_id)`. If groups exist, show them and ask whether the user wants to scope today's work to a group (e.g. "mattress category"). If they pick one, remember the `group_id`.

If the endpoint is unavailable, continue without group scoping — that's fine.

## Step 3: Fetch categorized suggestions

Call `aeko_get_suggestions_v2(domain_id, group_id=<optional>)`.

**If the tool reports the v2 endpoint is unavailable** (message starts with "Suggestions v2 unavailable"):
- Tell the user plainly that the backend hasn't shipped the v2 contract yet.
- Call `aeko_get_suggestions(domain_id)` instead and surface the flat legacy list.
- Do **not** route to `/aeko-update-pdp`, `/aeko-create-own-content`, `/aeko-create-external-content`, or `/aeko-fix-store-level` — those all require v2 briefs and will dead-end.
- Instead, point the user at the existing skills: `/aeo-optimize`, `/aeo-audit`, `/generate-jsonld`, `/create-blog-article`. Pick the one that matches the top-priority legacy suggestion's `mcp_tool_hint` or `category`.
- Stop after this; no further routing in legacy mode.

## Step 4: Summarize the 4 buckets

Present a short summary: how many suggestions live in each of the four categories, and which category has the highest-priority items.

The 4 categories and their specialist skills:

| Category | Skill |
|---|---|
| Own Store · Product Detail Update | `/aeko-update-pdp` |
| Own Store · Content | `/aeko-create-own-content` |
| Other Media · Content | `/aeko-create-external-content` |
| Own Store · Store-Level | `/aeko-fix-store-level` |

## Step 5: Print ready-to-copy commands for each bucket

For each of the 4 categories that has at least one suggestion, print a **ready-to-copy code block** with the exact slash command + top-priority `suggestion_key` from that bucket. Example:

````
# Own Store · Product Detail Update (3 suggestions, top priority: critical)
/aeko-update-pdp sugg_abc123
````

Do this for all non-empty buckets, highest-priority-first. Then ask the user which one they want to tackle today. They will copy the command block from your message and run it themselves — this skill is a router, not a dispatcher. Do not execute the specialist skill yourself.

If the user asks you to "just run them all," tell them to run each specialist skill one at a time so they can review the output between runs.
