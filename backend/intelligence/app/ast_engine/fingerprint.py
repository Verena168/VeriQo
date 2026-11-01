"""Fingerprints for one source file (Module C).

* Lexical: k-gram hashing + winnowing over normalised tokens (Schleimer et al., 2003, the
  algorithm behind MOSS). Any shared run of >= K + W - 1 tokens is guaranteed to share at
  least one fingerprint, and each fingerprint keeps its line number for evidence.
* Structural: k-grams of AST node types from a tree-sitter parse, which survive changes that
  alter tokens but not program structure.
"""

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from hashlib import blake2b

from app.ast_engine.languages import language_for
from app.ast_engine.tokenizer import Token, normalize

log = logging.getLogger(__name__)

K = 10  # tokens per k-gram (noise threshold: shorter shared runs are ignored)
W = 6  # winnowing window -> every shared run of K + W - 1 = 15 tokens is detected
AST_K = 4
MAX_AST_GRAMS = 5000
MAX_AST_NODES = 200_000


def stable_hash(s: str) -> int:
    # 63-bit so it fits MongoDB's signed int64.
    return int.from_bytes(blake2b(s.encode(), digest_size=8).digest(), "big") >> 1


@dataclass(slots=True)
class FileFingerprint:
    path: str
    family: str
    n_tokens: int
    n_lines: int
    fps: list[tuple[int, int]]  # (hash, line)
    ast: set[int] = field(default_factory=set)

    def to_dict(self) -> dict:
        return {
            "path": self.path, "family": self.family, "n_tokens": self.n_tokens, "n_lines": self.n_lines,
            "fps": [list(f) for f in self.fps], "ast": sorted(self.ast),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FileFingerprint":
        return cls(d["path"], d["family"], d["n_tokens"], d["n_lines"], [tuple(f) for f in d["fps"]], set(d.get("ast", ())))


def winnow(kinds: list[str], lines: list[int], k: int = K, w: int = W) -> list[tuple[int, int]]:
    if len(kinds) < k:
        return [(stable_hash(" ".join(kinds)), lines[0])] if len(kinds) >= 3 else []
    grams = [(stable_hash(" ".join(kinds[i:i + k])), lines[i]) for i in range(len(kinds) - k + 1)]
    if len(grams) <= w:
        return [min(grams)]
    out, last_pos = [], -1
    for start in range(len(grams) - w + 1):
        window = grams[start:start + w]
        # rightmost minimum, as in the paper, so runs of equal hashes are not re-recorded
        pos = max(range(w), key=lambda i: (-window[i][0], i)) + start
        if pos != last_pos:
            out.append(grams[pos])
            last_pos = pos
    return out


@lru_cache(maxsize=None)
def _parser(grammar: str):
    try:
        from tree_sitter_language_pack import get_parser

        return get_parser(grammar)
    except Exception as exc:
        log.warning("tree-sitter grammar %s unavailable: %s", grammar, exc)
        return None


_STRINGY = ("string", "char", "escape", "heredoc", "template")
_NUMERIC = ("integer", "float", "number", "decimal", "hex", "octal", "numeric")


def _leaf_kind(node) -> str | None:
    """Normalised token for a tree-sitter leaf, mirroring tokenizer.normalize (ID / STR / NUM / literal)."""
    t = node.type
    if not node.is_named:
        return t  # anonymous leaves are keywords and punctuation; their type is their text
    if "comment" in t:
        return None
    if "identifier" in t or t in ("name", "constant", "variable_name"):
        return "ID"
    if any(x in t for x in _STRINGY):
        return "STR"
    if any(x in t for x in _NUMERIC):
        return "NUM"
    return node.text.decode(errors="replace") if node.text else t


def parse_tokens_and_ast(code: str, grammar: str) -> tuple[list[Token], set[int]] | None:
    """One tree-sitter pass: normalised leaf tokens (lexical) + node-type k-grams (structural)."""
    parser = _parser(grammar)
    if parser is None:
        return None
    tree = parser.parse(code.encode("utf-8", errors="replace"))
    types: list[str] = []
    tokens: list[Token] = []
    stack = [tree.root_node]
    while stack and len(types) < MAX_AST_NODES:  # iterative pre-order: deep trees can't overflow
        node = stack.pop()
        if node.is_named:
            types.append(node.type)
        if node.child_count == 0:
            kind = _leaf_kind(node)
            # adjacent string pieces (quote, content, escape) form one literal
            if kind and not (kind == "STR" and tokens and tokens[-1].kind == "STR"):
                tokens.append(Token(kind, node.start_point[0] + 1))
        else:
            stack.extend(reversed(node.children))
    grams = {stable_hash("/".join(types[i:i + AST_K])) for i in range(max(len(types) - AST_K + 1, 0))}
    if len(grams) > MAX_AST_GRAMS:
        grams = set(sorted(grams)[:MAX_AST_GRAMS])
    return tokens, grams


def fingerprint_source(path: str, code: str) -> FileFingerprint | None:
    lang = language_for(path)
    if lang is None:
        return None
    family, lexer, grammar = lang
    parsed = parse_tokens_and_ast(code, grammar) if grammar else None
    tokens, ast = parsed if parsed else (normalize(code, lexer), set())  # Pygments fallback (e.g. Dart)
    if len(tokens) < 3:
        return None
    fps = winnow([t.kind for t in tokens], [t.line for t in tokens])
    return FileFingerprint(path, family, len(tokens), code.count("\n") + 1, fps, ast)
