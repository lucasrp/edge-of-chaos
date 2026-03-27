# Pre-Skill — Agent Context (phenotype)

> Instance-specific configuration. The genotype pipeline already loads
> identity, rules, threads, health and anti-redundancy before this step.
> Only what is unique to this agent goes here.

---

## Voice

{{ VOICE }}

{% if CONTEXT_DIR %}
## Context directory

Check `{{ CONTEXT_DIR }}` for updated docs, specs, or transcripts before acting. This is your domain context — read what changed since last session.
{% endif %}

## Before each skill

{{ PRE_SKILL_CHECKLIST }}
