"""Lexical normalisation of source code (Module C).

Every identifier becomes ID, every string STR and every number NUM; comments, docstrings and
whitespace are dropped. Renaming variables, rewording comments or reformatting code therefore
produces the same token stream, which is what makes copied-and-renamed logic detectable.
"""

from dataclasses import dataclass
from functools import lru_cache

from pygments.lexers import get_lexer_by_name
from pygments.token import Comment, Error, Name, Number, String, Text, Whitespace


@dataclass(frozen=True, slots=True)
class Token:
    kind: str
    line: int


@lru_cache(maxsize=None)
def _lexer(name: str):
    return get_lexer_by_name(name, stripnl=False, ensurenl=False)


def normalize(code: str, lexer_name: str) -> list[Token]:
    out: list[Token] = []
    line = 1
    for ttype, value in _lexer(lexer_name).get_tokens(code):
        start_line = line
        line += value.count("\n")
        if ttype in Comment or ttype in String.Doc or ttype in Whitespace or ttype in Error:
            continue
        if ttype in Text and not value.strip():
            continue
        if ttype in Name:
            kind = "ID"
        elif ttype in String:
            kind = "STR"
            # Pygments splits one string literal into quote / content / escape tokens.
            if out and out[-1].kind == "STR":
                continue
        elif ttype in Number:
            kind = "NUM"
        else:
            kind = value.strip()
        out.append(Token(kind, start_line))
    return out
