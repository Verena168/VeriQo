"""File extension -> (language family, Pygments lexer, tree-sitter grammar)."""

from pathlib import PurePosixPath

# family groups languages that may legitimately be compared with each other (JS <-> TS).
LANGUAGES: dict[str, tuple[str, str, str | None]] = {
    ".py": ("python", "python", "python"),
    ".js": ("js", "javascript", "javascript"),
    ".mjs": ("js", "javascript", "javascript"),
    ".cjs": ("js", "javascript", "javascript"),
    ".jsx": ("js", "javascript", "javascript"),
    ".ts": ("js", "typescript", "typescript"),
    ".tsx": ("js", "typescript", "tsx"),
    ".java": ("java", "java", "java"),
    ".kt": ("kotlin", "kotlin", "kotlin"),
    ".c": ("c", "c", "c"),
    ".h": ("c", "c", "c"),
    ".cpp": ("c", "cpp", "cpp"),
    ".cc": ("c", "cpp", "cpp"),
    ".hpp": ("c", "cpp", "cpp"),
    ".cs": ("csharp", "csharp", "csharp"),
    ".go": ("go", "go", "go"),
    ".rs": ("rust", "rust", "rust"),
    ".rb": ("ruby", "ruby", "ruby"),
    ".php": ("php", "php", "php"),
    ".swift": ("swift", "swift", "swift"),
    ".dart": ("dart", "dart", None),
    ".sol": ("solidity", "solidity", None),
}


def language_for(path: str) -> tuple[str, str, str | None] | None:
    return LANGUAGES.get(PurePosixPath(path).suffix.lower())
