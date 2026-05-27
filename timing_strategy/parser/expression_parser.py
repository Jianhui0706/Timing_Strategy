from __future__ import annotations

import re
from dataclasses import dataclass

from timing_strategy.parser.ast import ASTNode


class ExpressionParseError(ValueError):
    """表达式解析失败。"""


@dataclass(frozen=True)
class Token:
    kind: str
    value: str


TOKEN_RE = re.compile(
    r"""
    (?P<SPACE>\s+)
    |(?P<NUMBER>-?\d+(?:\.\d+)?)
    |(?P<IDENT>[A-Za-z_][A-Za-z0-9_]*)
    |(?P<LPAREN>\()
    |(?P<RPAREN>\))
    |(?P<COMMA>,)
    """,
    re.VERBOSE,
)


def tokenize(expression: str) -> list[Token]:
    tokens: list[Token] = []
    pos = 0
    while pos < len(expression):
        match = TOKEN_RE.match(expression, pos)
        if not match:
            raise ExpressionParseError(f"无法识别的字符：{expression[pos:pos + 20]}")
        kind = match.lastgroup or ""
        value = match.group()
        if kind != "SPACE":
            tokens.append(Token(kind, value))
        pos = match.end()
    return tokens


class ExpressionParser:
    """解析函数式表达式，例如 SUB(TS_MEAN(close, 20), TS_MEAN(close, 60))。"""

    def __init__(self, expression: str):
        self.expression = expression
        self.tokens = tokenize(expression)
        self.index = 0

    def parse(self) -> ASTNode:
        if not self.tokens:
            raise ExpressionParseError("表达式为空")
        node = self._parse_expr()
        if self.index != len(self.tokens):
            token = self.tokens[self.index]
            raise ExpressionParseError(f"表达式末尾存在无法解析的内容：{token.value}")
        return node

    def _parse_expr(self) -> ASTNode:
        token = self._peek()
        if token.kind == "NUMBER":
            self._advance()
            return ASTNode("number", float(token.value))
        if token.kind != "IDENT":
            raise ExpressionParseError(f"此处需要字段、数字或函数名，实际为：{token.value}")

        ident = token.value
        self._advance()
        if self._match("LPAREN"):
            args: list[ASTNode] = []
            if not self._match("RPAREN"):
                while True:
                    args.append(self._parse_expr())
                    if self._match("RPAREN"):
                        break
                    self._expect("COMMA")
            return ASTNode("call", ident.upper(), tuple(args))
        return ASTNode("field", ident.lower())

    def _peek(self) -> Token:
        if self.index >= len(self.tokens):
            raise ExpressionParseError("表达式意外结束")
        return self.tokens[self.index]

    def _advance(self) -> Token:
        token = self._peek()
        self.index += 1
        return token

    def _match(self, kind: str) -> bool:
        if self.index < len(self.tokens) and self.tokens[self.index].kind == kind:
            self.index += 1
            return True
        return False

    def _expect(self, kind: str) -> Token:
        if self.index >= len(self.tokens):
            raise ExpressionParseError(f"需要 {kind}，但表达式已结束")
        token = self.tokens[self.index]
        if token.kind != kind:
            raise ExpressionParseError(f"需要 {kind}，实际为 {token.value}")
        self.index += 1
        return token


def parse_expression(expression: str) -> ASTNode:
    return ExpressionParser(expression).parse()

