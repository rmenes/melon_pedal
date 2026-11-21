"""Small Turtle (.ttl) reader, enough for LV2 plugin bundles.

Keeps melon-pedald free of extra packages: it only needs the Python standard
library. Handles @prefix/@base, IRIs, prefixed names, 'a', strings (short and
long, with @lang / ^^type), numbers, booleans, blank nodes [ ... ],
collections ( ... ), and ; , . lists. Not a full RDF implementation.
"""
import re


class IRI(str):
    """An IRI (as opposed to a literal string)."""


class BNode(str):
    """A blank node id."""


RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"

_TOKEN = re.compile(
    r"""
    (?P<ws>\s+|\#[^\n]*)
  | (?P<iri><[^>]*>)
  | (?P<lstr>\"\"\"(?:[^"\\]|\\.|"(?!""))*\"\"\")
  | (?P<str>"(?:[^"\\\n]|\\.)*")
  | (?P<lang>@[A-Za-z]+(?:-[A-Za-z0-9]+)*)
  | (?P<dtype>\^\^)
  | (?P<num>[+-]?(?:\d+\.\d+(?:[eE][+-]?\d+)?|\d+\.[eE][+-]?\d+|\.\d+(?:[eE][+-]?\d+)?|\d+[eE][+-]?\d+|\d+)(?![\w:]))
  | (?P<pname>(?:[A-Za-z_][\w.-]*)?:(?:[\w%:-]|\.(?=[\w%:-]))*)
  | (?P<bnode>_:[\w.-]+)
  | (?P<word>[A-Za-z]+)
  | (?P<punct>[;,.\[\]()])
    """,
    re.VERBOSE,
)

_ESC = {"t": "\t", "n": "\n", "r": "\r", '"': '"', "'": "'", "\\": "\\", "b": "\b", "f": "\f"}


def _unescape(s):
    return re.sub(r"\\(u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8}|.)",
                  lambda m: chr(int(m.group(1)[1:], 16)) if m.group(1)[0] in "uU" and len(m.group(1)) > 1
                  else _ESC.get(m.group(1), m.group(1)), s)


def _tokenize(text):
    pos = 0
    out = []
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            raise ValueError(f"cannot parse near: {text[pos:pos + 40]!r}")
        kind = m.lastgroup
        if kind != "ws":
            if kind == "lang" and m.group().lower() in ("@prefix", "@base"):
                kind = "directive"
            out.append((kind, m.group(), pos))
        pos = m.end()
    return out


class Graph:
    """Triples plus where each subject first appeared (to keep file order)."""

    def __init__(self):
        self.triples = []
        self.by_subject = {}
        self.first_seen = {}
        self._order = 0

    def add(self, s, p, o):
        self.triples.append((s, p, o))
        self.by_subject.setdefault(s, []).append((p, o))

    def objects(self, s, p):
        return [o for (pp, o) in self.by_subject.get(s, ()) if pp == p]

    def value(self, s, p, default=None):
        objs = self.objects(s, p)
        return objs[0] if objs else default

    def subjects(self, p, o):
        return [s for (s, pp, oo) in self.triples if pp == p and oo == o]

    def parse(self, text, base=""):
        _Parser(self, text, base).run()
        return self


class _Parser:
    def __init__(self, graph, text, base):
        self.g = graph
        self.toks = _tokenize(text)
        self.i = 0
        self.base = base
        self.prefixes = {}
        self.bn = 0

    # --- helpers ---
    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else ("eof", "", -1)

    def next(self):
        t = self.peek()
        self.i += 1
        return t

    def expect(self, value):
        t = self.next()
        if t[1] != value:
            raise ValueError(f"expected {value!r}, got {t[1]!r}")

    def new_bnode(self):
        self.bn += 1
        return BNode(f"_:b{id(self.g)}_{self.bn}")

    def iri(self, raw):
        v = raw[1:-1]
        if self.base and not re.match(r"^[A-Za-z][\w+.-]*:", v):
            v = self.base.rsplit("/", 1)[0] + "/" + v if v else self.base
        return IRI(v)

    def pname(self, raw):
        pre, _, local = raw.partition(":")
        if pre not in self.prefixes:
            raise ValueError(f"unknown prefix {pre!r}")
        return IRI(self.prefixes[pre] + local)

    # --- grammar ---
    def run(self):
        while self.peek()[0] != "eof":
            t = self.peek()
            if t[0] == "directive" or (t[0] == "word" and t[1].upper() in ("PREFIX", "BASE")):
                self.directive()
            else:
                self.triples()
                self.expect(".")

    def directive(self):
        kind, word, _ = self.next()
        sparql = kind == "word"
        if word.lower().lstrip("@") == "prefix":
            name = self.next()[1]
            self.prefixes[name[:-1]] = self.iri(self.next()[1])
        else:
            self.base = self.iri(self.next()[1])
        if not sparql:
            self.expect(".")

    def triples(self):
        t = self.peek()
        if t[1] == "[":
            subj = self.blank_node_list()
            if self.peek()[1] == ".":
                return
        else:
            subj = self.term()
            if subj not in self.g.first_seen:
                self.g.first_seen[subj] = self.g._order
                self.g._order += 1
        self.predicate_objects(subj)

    def predicate_objects(self, subj):
        while True:
            t = self.next()
            pred = IRI(RDF + "type") if t[0] == "word" and t[1] == "a" else self.term(t)
            while True:
                self.g.add(subj, pred, self.object())
                if self.peek()[1] == ",":
                    self.next()
                    continue
                break
            if self.peek()[1] == ";":
                while self.peek()[1] == ";":
                    self.next()
                if self.peek()[1] in (".", "]"):
                    return
                continue
            return

    def blank_node_list(self):
        self.expect("[")
        node = self.new_bnode()
        if self.peek()[1] != "]":
            self.predicate_objects(node)
        self.expect("]")
        return node

    def collection(self):
        self.expect("(")
        items = []
        while self.peek()[1] != ")":
            items.append(self.object())
        self.expect(")")
        head = IRI(RDF + "nil")
        for item in reversed(items):
            node = self.new_bnode()
            self.g.add(node, IRI(RDF + "first"), item)
            self.g.add(node, IRI(RDF + "rest"), head)
            head = node
        return head

    def object(self):
        t = self.peek()
        if t[1] == "[":
            return self.blank_node_list()
        if t[1] == "(":
            return self.collection()
        return self.term()

    def term(self, t=None):
        kind, raw, _ = t or self.next()
        if kind == "iri":
            return self.iri(raw)
        if kind == "pname":
            return self.pname(raw)
        if kind == "bnode":
            return BNode(raw)
        if kind == "num":
            return float(raw) if any(c in raw for c in ".eE") else int(raw)
        if kind in ("str", "lstr"):
            val = _unescape(raw[3:-3] if kind == "lstr" else raw[1:-1])
            if self.peek()[0] == "lang":
                self.next()
            elif self.peek()[0] == "dtype":
                self.next()
                dt = self.term()
                if dt.endswith(("#float", "#double", "#decimal")):
                    return float(val)
                if dt.endswith(("#int", "#integer", "#long")):
                    return int(val)
                if dt.endswith("#boolean"):
                    return val == "true"
            return val
        if kind == "word" and raw in ("true", "false"):
            return raw == "true"
        raise ValueError(f"unexpected token {raw!r}")
