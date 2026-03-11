"""Extract preferences, corrections, tech stack and patterns from parsed sessions.

Pure Python heuristics — regex + frequency counting, no ML.
Supports both English and Portuguese patterns.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from continuum.scanner.parser import Message, Session


# ---------------------------------------------------------------------------
# Preference detection patterns
# ---------------------------------------------------------------------------

# Language preference: explicit statements about which natural language to use
_LANG_PREF_PATTERNS = [
    # English patterns
    (re.compile(r"\b(?:respond|answer|reply|speak|write|talk)\s+(?:in|to me in)\s+(\w+)", re.I), None),
    (re.compile(r"\buse\s+(\w+)\s+(?:language|please)", re.I), None),
    (re.compile(r"\bin\s+(portuguese|english|spanish|french|german|italian|chinese|japanese)\b", re.I), None),
    # Portuguese patterns
    (re.compile(r"\b(?:responda|fale|escreva)\s+em\s+(\w+)", re.I), None),
    (re.compile(r"\bem\s+portugu[eê]s\b", re.I), "portuguese"),
]

# Verbosity / style directives
_STYLE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Conciseness
    (re.compile(r"\b(?:be\s+)?(?:concise|brief|terse|short|succinct)\b", re.I), "concise"),
    (re.compile(r"\bno\s+(?:fluff|filler|preamble|bloat)\b", re.I), "concise"),
    (re.compile(r"\bkeep\s+it\s+(?:short|simple|brief)\b", re.I), "concise"),
    (re.compile(r"\bseja\s+(?:breve|conciso|direto)\b", re.I), "concise"),
    (re.compile(r"\bsem\s+(?:enrolação|firula)\b", re.I), "concise"),
    # Verbose / detailed
    (re.compile(r"\b(?:be\s+)?(?:detailed|verbose|thorough|comprehensive)\b", re.I), "detailed"),
    (re.compile(r"\bstep\s+by\s+step\b", re.I), "step-by-step"),
    (re.compile(r"\bpasso\s+a\s+passo\b", re.I), "step-by-step"),
    (re.compile(r"\bexplain\s+(?:everything|each|every|in\s+detail)\b", re.I), "detailed"),
    (re.compile(r"\bexplique\s+(?:tudo|cada|em\s+detalhe)\b", re.I), "detailed"),
    # Code-only
    (re.compile(r"\bjust\s+(?:show|give)\s+(?:me\s+)?(?:the\s+)?code\b", re.I), "code-only"),
    (re.compile(r"\bcode\s+only\b", re.I), "code-only"),
    (re.compile(r"\bno\s+(?:explanation|commentary|comments)\b", re.I), "code-only"),
    # Formality
    (re.compile(r"\bdon'?t\s+(?:be\s+)?formal\b", re.I), "informal"),
    (re.compile(r"\b(?:be\s+)?(?:casual|informal)\b", re.I), "informal"),
]

# ---------------------------------------------------------------------------
# Correction / negation patterns
# ---------------------------------------------------------------------------

_CORRECTION_PATTERNS = [
    re.compile(r"\b(?:no|nope),?\s+(?:not\s+)?that", re.I),
    re.compile(r"\binstead\s+(?:do|use|try|look)\b", re.I),
    re.compile(r"\bdon'?t\s+(?:do|use|add|include|mock|create)\b", re.I),
    re.compile(r"\bstop\s+(?:doing|using|adding)\b", re.I),
    re.compile(r"\bwrong\b", re.I),
    re.compile(r"\bthat'?s\s+not\s+(?:right|correct|what)\b", re.I),
    re.compile(r"\bactually,?\s+(?:I|we|you|let'?s)\b", re.I),
    re.compile(r"\bnot\s+like\s+that\b", re.I),
    re.compile(r"\bplease\s+(?:don'?t|stop|remove|undo)\b", re.I),
    # Portuguese
    re.compile(r"\bnão\b.*\b(?:isso|assim|esse|essa)\b", re.I),
    re.compile(r"\berrado\b", re.I),
    re.compile(r"\bna\s+verdade\b", re.I),
    re.compile(r"\bpare\s+de\b", re.I),
    re.compile(r"\bnão\s+(?:faça|use|coloque|adicione)\b", re.I),
]

# ---------------------------------------------------------------------------
# Technology detection
# ---------------------------------------------------------------------------

# Programming languages — match common mentions
_TECH_LANGUAGES = [
    "python", "javascript", "typescript", "rust", "go", "java", "kotlin",
    "swift", "ruby", "php", "c\\+\\+", "c#", "scala", "elixir", "clojure",
    "haskell", "lua", "perl", "dart", "zig", "nim", "ocaml", "r\\b",
]

# Frameworks and tools
_TECH_FRAMEWORKS = [
    "react", "nextjs", "next\\.js", "vue", "angular", "svelte", "django",
    "flask", "fastapi", "express", "nestjs", "spring", "rails",
    "laravel", "phoenix", "gin", "actix", "axum", "rocket",
    "tailwind", "bootstrap", "prisma", "drizzle", "sqlalchemy",
]

_TECH_TOOLS = [
    "docker", "kubernetes", "k8s", "terraform", "ansible", "nginx",
    "postgres(?:ql)?", "mysql", "redis", "mongodb", "sqlite",
    "git", "github", "gitlab", "npm", "yarn", "pnpm", "pip", "cargo",
    "pytest", "jest", "vitest", "playwright", "cypress",
    "webpack", "vite", "esbuild", "turbopack",
    "aws", "gcp", "azure", "vercel", "netlify", "fly\\.io",
    "claude", "openai", "langchain", "llamaindex",
]

# Compile combined tech pattern
_TECH_ALL = _TECH_LANGUAGES + _TECH_FRAMEWORKS + _TECH_TOOLS
_TECH_PATTERN = re.compile(
    r"\b(" + "|".join(_TECH_ALL) + r")\b", re.I
)

# Canonical name mapping for regex variants
_TECH_CANONICAL: dict[str, str] = {
    "next.js": "nextjs",
    "postgresql": "postgres",
    "k8s": "kubernetes",
    "fly.io": "fly.io",
    "c++": "c++",
    "c#": "c#",
}

# ---------------------------------------------------------------------------
# Project structure patterns
# ---------------------------------------------------------------------------

# Common directories and config files
_STRUCTURE_DIRS = re.compile(
    r"\b(?:src|lib|app|pages|components|utils|hooks|services|api|"
    r"tests?|spec|__tests__|fixtures|e2e|"
    r"config|scripts|bin|docs?|public|static|assets|dist|build|"
    r"migrations?|models?|views?|controllers?|routes?|middleware|"
    r"templates?|schemas?)\b",
    re.I,
)

_CONFIG_FILES = re.compile(
    r"\b(?:package\.json|tsconfig\.json|pyproject\.toml|setup\.py|setup\.cfg|"
    r"Cargo\.toml|go\.mod|Gemfile|Makefile|Dockerfile|docker-compose\.ya?ml|"
    r"\.env|\.gitignore|\.eslintrc|prettier|jest\.config|vite\.config|"
    r"next\.config|tailwind\.config|continuum\.toml|CLAUDE\.md)\b",
    re.I,
)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Preference:
    """A detected user preference."""

    category: str  # "language", "style", "other"
    value: str
    occurrences: int = 1
    confidence: float = 0.0  # 0.0 - 1.0


@dataclass
class Correction:
    """A detected user correction."""

    user_text: str  # The correcting message
    preceding_assistant_text: str  # What the assistant said before
    pattern_matched: str  # Which pattern triggered


@dataclass
class HeuristicsResult:
    """All extracted heuristics from a set of sessions."""

    preferences: list[Preference] = field(default_factory=list)
    corrections: list[Correction] = field(default_factory=list)
    tech_stack: dict[str, int] = field(default_factory=dict)  # tech -> count
    structure_patterns: dict[str, int] = field(default_factory=dict)  # pattern -> count
    topics: dict[str, int] = field(default_factory=dict)  # topic -> count


# ---------------------------------------------------------------------------
# Extraction functions
# ---------------------------------------------------------------------------

def extract_preferences(sessions: list[Session]) -> list[Preference]:
    """Extract explicit user preferences from human messages.

    Looks for language preferences, verbosity/style directives,
    and other explicit instructions in user messages.

    Returns list of Preference objects with confidence based on frequency.
    """
    style_counts: Counter[str] = Counter()
    lang_counts: Counter[str] = Counter()

    for session in sessions:
        for msg in session.human_messages:
            if not msg.text:
                continue

            # Check style patterns
            for pattern, style_name in _STYLE_PATTERNS:
                if pattern.search(msg.text):
                    style_counts[style_name] += 1

            # Check language preference patterns
            for pattern, fixed_lang in _LANG_PREF_PATTERNS:
                match = pattern.search(msg.text)
                if match:
                    if fixed_lang:
                        lang_counts[fixed_lang] += 1
                    else:
                        lang = match.group(1).lower()
                        lang_counts[lang] += 1

    # Build preference list with confidence scores
    preferences: list[Preference] = []

    total_human_msgs = sum(len(s.human_messages) for s in sessions)
    if total_human_msgs == 0:
        return preferences

    for lang, count in lang_counts.most_common():
        confidence = min(1.0, count / max(total_human_msgs * 0.01, 1))
        preferences.append(Preference(
            category="language",
            value=lang,
            occurrences=count,
            confidence=round(confidence, 2),
        ))

    for style, count in style_counts.most_common():
        confidence = min(1.0, count / max(total_human_msgs * 0.01, 1))
        preferences.append(Preference(
            category="style",
            value=style,
            occurrences=count,
            confidence=round(confidence, 2),
        ))

    return preferences


def extract_corrections(sessions: list[Session]) -> list[Correction]:
    """Extract user corrections — human messages following assistant output
    that contain negation/correction patterns.

    Returns list of Correction objects.
    """
    corrections: list[Correction] = []

    for session in sessions:
        messages = session.messages
        for i, msg in enumerate(messages):
            if msg.role != "human" or not msg.text:
                continue

            # Must follow an assistant message
            if i == 0:
                continue
            prev = messages[i - 1]
            if prev.role != "assistant":
                continue

            # Check correction patterns
            for pattern in _CORRECTION_PATTERNS:
                if pattern.search(msg.text):
                    # Truncate texts for storage
                    user_text = msg.text[:300]
                    prev_text = prev.text[:300] if prev.text else ""
                    corrections.append(Correction(
                        user_text=user_text,
                        preceding_assistant_text=prev_text,
                        pattern_matched=pattern.pattern,
                    ))
                    break  # One correction per message

    return corrections


def extract_tech_stack(sessions: list[Session]) -> dict[str, int]:
    """Extract technology mentions from all messages.

    Counts mentions of programming languages, frameworks, and tools
    across all human and assistant messages.

    Returns dict mapping tech name -> occurrence count, sorted descending.
    """
    counts: Counter[str] = Counter()

    for session in sessions:
        for msg in session.messages:
            if not msg.text:
                continue
            for match in _TECH_PATTERN.finditer(msg.text):
                tech = match.group(1).lower()
                # Normalize to canonical name
                tech = _TECH_CANONICAL.get(tech, tech)
                counts[tech] += 1

            # Also count tools from tool_calls
            for tc in msg.tool_calls:
                cmd = tc.args_summary.lower()
                for match in _TECH_PATTERN.finditer(cmd):
                    tech = match.group(1).lower()
                    tech = _TECH_CANONICAL.get(tech, tech)
                    counts[tech] += 1

    return dict(counts.most_common())


def extract_structure_patterns(sessions: list[Session]) -> dict[str, int]:
    """Extract project structure patterns — directory names and config files.

    Returns dict mapping pattern -> occurrence count, sorted descending.
    """
    counts: Counter[str] = Counter()

    for session in sessions:
        for msg in session.messages:
            if not msg.text:
                continue

            # Count directory patterns
            for match in _STRUCTURE_DIRS.finditer(msg.text):
                counts[match.group(0).lower()] += 1

            # Count config file patterns
            for match in _CONFIG_FILES.finditer(msg.text):
                counts[match.group(0)] += 1

            # Count from file paths mentioned
            for fpath in msg.files_mentioned:
                parts = fpath.split("/")
                for part in parts:
                    if _STRUCTURE_DIRS.fullmatch(part):
                        counts[part.lower()] += 1

    return dict(counts.most_common())


def extract_topics(sessions: list[Session], top_n: int = 20) -> dict[str, int]:
    """Extract recurring topics from human messages by word frequency.

    Filters out common stop words and short words.
    Returns dict mapping topic -> count for top N topics.
    """
    _STOP_WORDS = {
        # English
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "need", "must",
        "i", "you", "he", "she", "it", "we", "they", "me", "him", "her",
        "us", "them", "my", "your", "his", "its", "our", "their",
        "this", "that", "these", "those", "what", "which", "who", "whom",
        "and", "but", "or", "nor", "not", "so", "yet", "both", "either",
        "in", "on", "at", "to", "for", "of", "with", "by", "from",
        "up", "about", "into", "through", "during", "before", "after",
        "above", "below", "between", "out", "off", "over", "under",
        "if", "then", "else", "when", "where", "how", "why", "all",
        "each", "every", "any", "few", "more", "most", "other", "some",
        "no", "yes", "just", "also", "very", "too", "only", "own",
        "same", "than", "like", "now", "here", "there", "as",
        "want", "please", "make", "let", "get", "see", "know", "think",
        "look", "use", "file", "code", "run", "new", "add", "change",
        "sure", "ok", "okay", "thanks", "thank",
        # Portuguese
        "o", "a", "os", "as", "um", "uma", "uns", "umas", "de", "do",
        "da", "dos", "das", "em", "no", "na", "nos", "nas", "por",
        "para", "com", "sem", "que", "se", "não", "sim", "mais",
        "isso", "esse", "essa", "este", "esta", "ele", "ela",
        "eu", "tu", "nós", "eles", "elas", "você", "vocês",
        "mas", "ou", "como", "quando", "onde", "porque",
    }

    word_pattern = re.compile(r"[a-zA-ZÀ-ÿ]{4,}")
    counts: Counter[str] = Counter()

    for session in sessions:
        for msg in session.human_messages:
            if not msg.text:
                continue
            words = word_pattern.findall(msg.text.lower())
            for word in words:
                if word not in _STOP_WORDS and len(word) >= 4:
                    counts[word] += 1

    return dict(counts.most_common(top_n))


def run_heuristics(sessions: list[Session]) -> HeuristicsResult:
    """Run all heuristic extractors on a list of sessions.

    This is the main entry point. Returns a HeuristicsResult with
    all extracted data.
    """
    return HeuristicsResult(
        preferences=extract_preferences(sessions),
        corrections=extract_corrections(sessions),
        tech_stack=extract_tech_stack(sessions),
        structure_patterns=extract_structure_patterns(sessions),
        topics=extract_topics(sessions),
    )
