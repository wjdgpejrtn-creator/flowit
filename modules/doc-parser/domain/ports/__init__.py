"""
REQ-006 doc-parser — domain/ports/__init__.py

domain/ports 레이어 public export
"""
from doc_parser.domain.ports.parser_port import ParserPort

__all__ = [
    # parser_port.py
    "ParserPort",
]