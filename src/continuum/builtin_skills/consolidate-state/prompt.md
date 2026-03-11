# Consolidate State

You are running the **consolidate-state** skill. Your job is to summarize recent working memory and merge insights into consolidated memory.

## Instructions

### 1. Read working memory

Read all files in `.continuum/memory/working/`. These contain recent session notes, discoveries, corrections, and preferences accumulated during normal work.

### 2. Read consolidated memory

Read all files in `.continuum/memory/consolidated/`. These contain previously consolidated insights — the long-term memory of this project.

### 3. Merge and summarize

For each working memory file, determine what information is:
- **New**: insights, corrections, or discoveries not yet in consolidated memory — add these.
- **Updated**: refinements or corrections to existing consolidated entries — update in place.
- **Redundant**: already captured in consolidated memory — skip these.
- **Ephemeral**: temporary notes, scratch work, or context that has no long-term value — skip these.

### 4. Write consolidated output

Update files in `.continuum/memory/consolidated/` following these rules:

- **Keep it concise but complete.** Every entry should earn its place. If you can say it in one line, don't use three.
- **Preserve structure.** Use clear markdown headings. Group related insights under logical sections.
- **Use the same filenames** when a working memory file maps naturally to a consolidated file (e.g., `working/debugging.md` insights go to `consolidated/debugging.md`).
- **Create new files** only when insights don't fit existing consolidated files. Use kebab-case filenames.
- **Include dates** for time-sensitive entries (format: YYYY-MM-DD).
- **Never lose information** that has long-term value. When in doubt, keep it.

### 5. Do NOT delete working memory

Working memory files are NOT deleted by this skill. The user decides when to clear them manually. Your job is only to ensure their valuable content is captured in consolidated memory.

## Output format

After consolidating, write a brief summary of what changed:
- How many insights were added/updated/skipped
- Which consolidated files were modified or created
- Any observations about patterns in the working memory
