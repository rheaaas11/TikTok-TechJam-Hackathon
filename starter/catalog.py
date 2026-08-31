from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
PRICE_RE = re.compile(r"-?\d+(?:\.\d+)?")

MATERIALS = (
    "cotton", "polyester", "nylon", "leather", "wool", "spandex", "silk",
    "rayon", "linen", "denim", "suede", "rubber", "fabric", "canvas",
    "textile", "fleece", "cashmere", "velvet", "satin", "lace", "mesh",
    "synthetic", "faux leather", "stainless steel", "sterling silver", "metal",
)
_MATERIAL_WORD_SEPARATOR = r"[\s\-\u2010-\u2015]+"
_MATERIAL_PATTERNS = {
    value: re.compile(
        r"(?<!\w)" + _MATERIAL_WORD_SEPARATOR.join(re.escape(word) for word in value.split()) + r"(?!\w)"
    )
    for value in MATERIALS
}
_MATERIAL_FIRST_WORDS = {value: value.partition(" ")[0] for value in MATERIALS}
_NEGATED_MATERIAL_PREFIX = re.compile(
    r"\b(?:no|without|not|non|free\s+(?:of|from))"
    r"(?:[\s\-\u2010-\u2015]+(?:any|added|real|genuine|natural|organic|faux|made|of|with|from)){0,3}"
    r"[\s\-\u2010-\u2015]+$"
)
_NEGATED_MATERIAL_SUFFIX = re.compile(
    r"^[\s\-\u2010-\u2015]+free\b(?!\s+(?:shipping|delivery|returns?|size)\b)"
)
_NEGATION_WORDS = frozenset({"no", "without", "not", "non", "free"})
COLORS = (
    "black", "white", "blue", "red", "pink", "green", "brown", "gray",
    "grey", "purple", "yellow", "orange", "beige", "gold", "silver", "navy",
    "ivory", "cream", "tan", "khaki", "teal", "turquoise", "maroon", "multicolor",
)
SIZES = (
    "xxs", "xs", "small", "medium", "large", "xl", "xxl", "wide", "narrow",
)
STYLES = (
    "casual", "formal", "classic", "modern", "vintage", "athletic", "sport",
    "slim", "regular", "relaxed", "loose", "fitted", "oversized",
)

SEARCH_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
        "i", "in", "is", "it", "me", "my", "of", "on", "or", "please", "some",
        "that", "the", "this", "to", "want", "with", "would", "you", "looking",
        "still", "exploring", "need", "matters", "requirement", "key", "what",
    }
)
_RAW_FIELD_INDEX = {
    "title": 0,
    "categories": 1,
    "features": 2,
    "details": 3,
    "store": 4,
    "description": 5,
}


def flatten_text(value: object) -> str:
    """Flatten catalog lists/dicts without treating missing values as text."""
    if value in (None, ""):
        return ""
    if isinstance(value, dict):
        return " ".join(
            f"{key} {flatten_text(item)}".strip()
            for key, item in value.items()
            if item not in (None, "", [])
        )
    if isinstance(value, (list, tuple, set)):
        return " ".join(flatten_text(item) for item in value if item not in (None, ""))
    return str(value)


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", flatten_text(value)).casefold()
    return " ".join(TOKEN_RE.findall(text))


# Finite grammatical aliases, not stemming or a category ontology. In
# particular, "dress" must not match "address" or "dressing". Catalog-facing
# plural labels retain their usual spelling while both forms compare equally.
_CATEGORY_WORD_FORMS = (
    ("dresses", "dress"), ("shirts", "shirt"), ("jackets", "jacket"),
    ("coats", "coat"), ("hoodies", "hoodie"), ("sweaters", "sweater"),
    ("blazers", "blazer"), ("handbags", "handbag"), ("purses", "purse"),
    ("shoes", "shoe"), ("boots", "boot"), ("sneakers", "sneaker"),
    ("sandals", "sandal"), ("heels", "heel"), ("skirts", "skirt"),
    ("shorts", "short"), ("leggings", "legging"), ("pants", "pant"),
    ("trousers", "trouser"), ("jeans", "jean"), ("bottoms", "bottom"),
)
_CATEGORY_CANONICAL_WORD = {
    form: forms[0] for forms in _CATEGORY_WORD_FORMS for form in forms
}
_CATEGORY_SINGULAR_WORD = {
    form: forms[-1] for forms in _CATEGORY_WORD_FORMS for form in forms
}


def canonical_category(value: object) -> str:
    """Normalize only explicitly listed singular/plural category tokens."""
    return " ".join(_CATEGORY_CANONICAL_WORD.get(word, word)
                    for word in normalize_text(value).split())


def category_terms_match(text: object, value: object) -> bool:
    """Whole-token category comparison; empty metadata never proves a match."""
    requested = canonical_category(value).split()
    known = frozenset(canonical_category(text).split())
    return bool(requested and known and all(word in known for word in requested))


def category_query_variants(value: object) -> tuple[str, ...]:
    """Supply both exact grammatical forms to lexical retrieval, without OR syntax."""
    normalized = normalize_text(value)
    canonical = canonical_category(normalized)
    singular = " ".join(_CATEGORY_SINGULAR_WORD.get(word, word)
                        for word in normalized.split())
    return tuple(dict.fromkeys(item for item in (canonical, normalized, singular) if item))


def tokens(value: object) -> list[str]:
    return normalize_text(value).split()


def _lookup_token(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def _finite_float(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _nonnegative_int(value: object) -> int:
    try:
        return max(0, int(float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def parse_price(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else None
    match = PRICE_RE.search(str(value).replace(",", ""))
    if not match:
        return None
    number = float(match.group())
    return number if math.isfinite(number) and number >= 0 else None


def _present_terms(
    text: str,
    vocabulary: Iterable[str],
    token_set: frozenset[str] | None = None,
    *,
    prefer_specific: bool = False,
) -> frozenset[str]:
    present_tokens = token_set if token_set is not None else frozenset(text.split())
    padded = f" {text} "
    present = {
        value
        for value in vocabulary
        if (value in present_tokens if " " not in value else f" {value} " in padded)
    }
    if not prefer_specific:
        return frozenset(present)
    # Query clauses should prefer the most specific controlled value (for
    # example, ``faux leather`` rather than also requesting generic leather).
    return frozenset(
        value
        for value in present
        if not any(
            value != other and f" {value} " in f" {other} "
            for other in present
        )
    )


def extract_known_terms(value: object, vocabulary: Iterable[str]) -> frozenset[str]:
    normalized = normalize_text(value)
    return _present_terms(
        normalized,
        vocabulary,
        frozenset(normalized.split()),
        prefer_specific=True,
    )


def _catalog_material_terms(
    raw_fields: Iterable[str],
    present: frozenset[str],
    *,
    possible_negation: bool,
) -> tuple[frozenset[str], frozenset[str]]:
    """Keep affirmative material mentions, without turning negation into fact.

    This deliberately handles only local explicit negation. Mixed affirmative
    and negated mentions are ambiguous at parent-product level, so neither is
    promoted to a verified material claim. Searchable catalog text is unchanged.
    """
    raw_fields = tuple(raw_fields)
    if not present or not possible_negation:
        return present, frozenset()
    affirmative: set[str] = set()
    negated: set[str] = set()
    for raw_field in raw_fields:
        text = unicodedata.normalize("NFKC", raw_field).casefold()
        for material in present:
            # Most catalog-level material terms occur in only one or two fields.
            # A regex match requires this literal first word, including for
            # hyphenated multiword materials. Avoid rescanning unrelated fields.
            if _MATERIAL_FIRST_WORDS[material] not in text:
                continue
            for match in _MATERIAL_PATTERNS[material].finditer(text):
                prefix = text[max(0, match.start() - 80):match.start()]
                suffix = text[match.end():match.end() + 50]
                if _NEGATED_MATERIAL_PREFIX.search(prefix) or _NEGATED_MATERIAL_SUFFIX.search(suffix):
                    negated.add(material)
                else:
                    affirmative.add(material)
    return frozenset(affirmative - negated), frozenset(affirmative & negated)


@dataclass(frozen=True)
class Product:
    parent_asin: str
    title: str
    categories: str
    features: str
    details: str
    store: str
    description: str
    price: float | None
    average_rating: float | None
    rating_number: int
    materials: frozenset[str]
    colors: frozenset[str]
    sizes: frozenset[str]
    styles: frozenset[str]
    category_path: tuple[str, ...]
    raw_fields: tuple[str, ...]
    uncertain_materials: frozenset[str] = frozenset()

    @property
    def searchable_text(self) -> str:
        return " ".join(
            (self.title, self.categories, self.features, self.details, self.store, self.description)
        )

    def attribute_values(self, attribute: str) -> tuple[str, ...]:
        if attribute == "material":
            return tuple(sorted(self.materials))
        if attribute == "color":
            return tuple(sorted(self.colors))
        if attribute == "size":
            return tuple(sorted(self.sizes))
        if attribute == "style":
            return tuple(sorted(self.styles))
        if attribute == "brand":
            return (self.store,) if self.store else ()
        if attribute == "category":
            return self.category_path[-1:] if self.category_path else ()
        if attribute == "budget":
            return (_budget_bucket(self.price),) if self.price is not None else ()
        return ()

    def raw_field(self, name: str) -> str:
        index = _RAW_FIELD_INDEX.get(name)
        return self.raw_fields[index] if index is not None else ""


def _budget_bucket(price: float) -> str:
    if price < 25:
        return "under 25"
    if price < 50:
        return "25 to 50"
    if price < 100:
        return "50 to 100"
    if price < 200:
        return "100 to 200"
    return "200 and above"


class CatalogIndex:
    """Read-only product lookup plus an in-memory SQLite FTS5 index."""

    FTS_WEIGHTS = (0.0, 6.0, 4.0, 2.5, 2.5, 1.5, 1.0)
    SEARCH_FIELDS = ("title", "categories", "features", "details", "store", "description")
    FIELD_WEIGHTS = dict(zip(SEARCH_FIELDS, FTS_WEIGHTS[1:]))

    def __init__(
        self,
        catalog_path: str | Path,
        *,
        force_python_search: bool = False,
    ) -> None:
        self.catalog_path = Path(catalog_path)
        self.products: dict[str, Product] = {}
        self.valid_ids: set[str] = set()
        self.structured_ids: dict[str, dict[str, list[str]]] = {
            attribute: defaultdict(list)
            for attribute in ("material", "color", "size", "style", "brand")
        }
        self._fallback_ids: list[str] = []
        self._fallback_position: dict[str, int] = {}
        self._lexical_postings: dict[str, dict[str, set[str]]] = {
            field: defaultdict(set) for field in self.SEARCH_FIELDS
        }
        self._lock = threading.RLock()
        self.connection = sqlite3.connect(":memory:", check_same_thread=False)
        self.connection.execute("PRAGMA temp_store=MEMORY")
        self.connection.execute("PRAGMA cache_size=-64000")
        self.fts_available = not force_python_search
        self._load()

    def _load(self) -> None:
        cursor = self.connection.cursor()
        if self.fts_available:
            try:
                cursor.execute(
                    "CREATE VIRTUAL TABLE products USING fts5("
                    "parent_asin UNINDEXED, title, categories, features, details, store, description, "
                    "tokenize='unicode61 remove_diacritics 2')"
                )
            except sqlite3.OperationalError:
                self.fts_available = False
        batch: list[tuple[str, str, str, str, str, str, str]] = []
        with self.catalog_path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                raw = json.loads(line)
                parent_asin = str(raw.get("parent_asin") or "").strip()
                if not parent_asin:
                    raise ValueError(f"catalog row {line_number} has no parent_asin")
                if parent_asin in self.products:
                    raise ValueError(f"duplicate parent_asin: {parent_asin}")

                raw_title = flatten_text(raw.get("title"))
                raw_categories = flatten_text(raw.get("categories"))
                raw_features = flatten_text(raw.get("features"))
                raw_details = flatten_text(raw.get("details"))
                raw_store = flatten_text(raw.get("store"))
                raw_description = flatten_text(raw.get("description"))
                title = normalize_text(raw_title)
                raw_category_values = raw.get("categories") or []
                if not isinstance(raw_category_values, (list, tuple, set)):
                    raw_category_values = [raw_category_values]
                category_values = [normalize_text(item) for item in raw_category_values]
                categories = " | ".join(item for item in category_values if item)
                features = normalize_text(raw_features)
                details = normalize_text(raw_details)
                store = normalize_text(raw_store)
                description = normalize_text(raw_description)
                combined = " ".join((title, categories, features, details, store, description))
                combined_tokens = frozenset(combined.split())
                raw_fields = (
                    raw_title, raw_categories, raw_features, raw_details, raw_store, raw_description,
                )
                materials, uncertain_materials = _catalog_material_terms(
                    raw_fields,
                    _present_terms(combined, MATERIALS, combined_tokens),
                    possible_negation=bool(combined_tokens & _NEGATION_WORDS),
                )
                rating = raw.get("average_rating")
                rating_number = raw.get("rating_number")
                product = Product(
                    parent_asin=parent_asin,
                    title=title,
                    categories=categories,
                    features=features,
                    details=details,
                    store=store,
                    description=description,
                    price=parse_price(raw.get("price")),
                    average_rating=_finite_float(rating),
                    rating_number=_nonnegative_int(rating_number),
                    materials=materials,
                    colors=frozenset(
                        "gray" if value == "grey" else value
                        for value in _present_terms(combined, COLORS, combined_tokens)
                    ),
                    sizes=_present_terms(combined, SIZES, combined_tokens),
                    styles=_present_terms(combined, STYLES, combined_tokens),
                    category_path=tuple(item for item in category_values if item),
                    # Keep source text so demo evidence can quote a local window
                    # around a match anywhere in a field, not an unrelated prefix.
                    raw_fields=raw_fields,
                    uncertain_materials=uncertain_materials,
                )
                self.products[parent_asin] = product
                self.valid_ids.add(parent_asin)
                for attribute, values in (
                    ("material", product.materials),
                    ("color", product.colors),
                    ("size", product.sizes),
                    ("style", product.styles),
                    ("brand", (product.store,) if product.store else ()),
                ):
                    for value in values:
                        self.structured_ids[attribute][value].append(parent_asin)
                if self.fts_available:
                    batch.append(
                        (parent_asin, title, categories, features, details, store, description)
                    )
                    if len(batch) >= 1000:
                        cursor.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)", batch)
                        batch.clear()
                else:
                    for field in self.SEARCH_FIELDS:
                        for token in set(getattr(product, field).split()):
                            self._lexical_postings[field][_lookup_token(token)].add(parent_asin)
        if self.fts_available and batch:
            cursor.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)", batch)
        self.connection.commit()
        self._fallback_ids = [
            product.parent_asin
            for product in sorted(
                self.products.values(),
                key=lambda product: (
                    -product.rating_number,
                    -(product.average_rating or 0.0),
                    product.parent_asin,
                ),
            )
        ]
        self._fallback_position = {
            parent_asin: position for position, parent_asin in enumerate(self._fallback_ids)
        }

    @staticmethod
    def _expression(
        query_terms: Iterable[str],
        column: str | None = None,
        *,
        keep_stopwords: bool = False,
    ) -> str:
        cleaned: list[str] = []
        seen: set[str] = set()
        for term in query_terms:
            normalized = normalize_text(term)
            for token in normalized.split():
                if (
                    len(token) < 2
                    or token in seen
                    or (not keep_stopwords and token in SEARCH_STOPWORDS)
                ):
                    continue
                seen.add(token)
                cleaned.append(token)
                if len(cleaned) >= 48:
                    break
            if len(cleaned) >= 48:
                break
        if not cleaned:
            return ""
        body = " OR ".join(f'"{term}"' for term in cleaned)
        return f"{column} : ({body})" if column else body

    def search(
        self,
        query_terms: Iterable[str],
        limit: int = 200,
        column: str | None = None,
    ) -> list[str]:
        query_terms = tuple(query_terms)
        expression = self._expression(query_terms, column)
        if not expression:
            return []
        if not self.fts_available:
            return self._python_search(query_terms, limit, column)
        weights = ", ".join(str(value) for value in self.FTS_WEIGHTS)
        with self._lock:
            rows = self.connection.execute(
                "SELECT parent_asin FROM products WHERE products MATCH ? "
                f"ORDER BY bm25(products, {weights}), parent_asin LIMIT ?",
                (expression, max(1, int(limit))),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def _query_tokens(self, query_terms: Iterable[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for term in query_terms:
            for token in normalize_text(term).split():
                if len(token) < 2 or token in SEARCH_STOPWORDS or token in seen:
                    continue
                seen.add(token)
                result.append(_lookup_token(token))
                if len(result) >= 48:
                    return result
        return result

    def _python_search(
        self,
        query_terms: Iterable[str],
        limit: int,
        column: str | None,
    ) -> list[str]:
        query_tokens = self._query_tokens(query_terms)
        fields = (column,) if column in self.SEARCH_FIELDS else self.SEARCH_FIELDS
        scores: Counter[str] = Counter()
        for field in fields:
            weight = self.FIELD_WEIGHTS[field]
            postings = self._lexical_postings[field]
            for token in query_tokens:
                for parent_asin in postings.get(token, ()):
                    scores[parent_asin] += weight
        return [
            parent_asin
            for parent_asin, _ in sorted(
                scores.items(),
                key=lambda item: (
                    -item[1],
                    self._fallback_position.get(item[0], len(self.products)),
                    item[0],
                ),
            )[: max(1, int(limit))]
        ]

    def search_phrases(
        self,
        phrases: Iterable[str],
        limit: int = 200,
        column: str | None = None,
    ) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for phrase in phrases:
            normalized = " ".join(normalize_text(phrase).split()[:24])
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            cleaned.append(normalized)
            if len(cleaned) >= 24:
                break
        if not cleaned:
            return []
        if not self.fts_available:
            fields = (column,) if column in self.SEARCH_FIELDS else self.SEARCH_FIELDS
            scores: Counter[str] = Counter()
            for phrase in cleaned:
                phrase_tokens = [_lookup_token(token) for token in phrase.split()]
                folded_phrase = " ".join(phrase_tokens)
                candidates: set[str] = set()
                for field in fields:
                    postings = self._lexical_postings[field]
                    if phrase_tokens:
                        candidates.update(postings.get(phrase_tokens[0], ()))
                for parent_asin in candidates:
                    product = self.products[parent_asin]
                    for field in fields:
                        folded_field = " ".join(
                            _lookup_token(token) for token in getattr(product, field).split()
                        )
                        if f" {folded_phrase} " in f" {folded_field} ":
                            scores[parent_asin] += self.FIELD_WEIGHTS[field] * len(phrase_tokens)
            return [
                parent_asin
                for parent_asin, _ in sorted(
                    scores.items(),
                    key=lambda item: (
                        -item[1],
                        self._fallback_position.get(item[0], len(self.products)),
                        item[0],
                    ),
                )[: max(1, int(limit))]
            ]
        body = " OR ".join(f'"{phrase}"' for phrase in cleaned)
        expression = f"{column} : ({body})" if column else body
        weights = ", ".join(str(value) for value in self.FTS_WEIGHTS)
        with self._lock:
            rows = self.connection.execute(
                "SELECT parent_asin FROM products WHERE products MATCH ? "
                f"ORDER BY bm25(products, {weights}), parent_asin LIMIT ?",
                (expression, max(1, int(limit))),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def search_category(self, category: str, limit: int = 200) -> list[str]:
        exact = self.search_phrases([category], limit, column="categories")
        if len(exact) >= min(50, max(1, int(limit))):
            return exact[: max(1, int(limit))]
        broad = self.search([category], limit, column="categories")
        return list(dict.fromkeys((*exact, *broad)))[: max(1, int(limit))]

    def structured_search(
        self,
        constraints: Iterable[tuple[str, str]],
        limit: int = 200,
    ) -> list[str]:
        matches: set[str] = set()
        vocabularies = {
            "material": MATERIALS,
            "color": COLORS,
            "size": SIZES,
            "style": STYLES,
        }
        for attribute, raw_value in constraints:
            value = normalize_text(raw_value)
            if not value:
                continue
            if attribute == "brand":
                exact = self.structured_ids["brand"].get(value)
                if exact:
                    matches.update(exact)
                else:
                    matches.update(self.search([value], limit, column="store"))
                continue
            vocabulary = vocabularies.get(attribute)
            if vocabulary is None:
                continue
            known_values = extract_known_terms(value, vocabulary)
            if attribute == "color":
                known_values = frozenset("gray" if item == "grey" else item for item in known_values)
            for known in known_values:
                matches.update(self.structured_ids[attribute].get(known, ()))
        return sorted(
            matches,
            key=lambda parent_asin: self._fallback_position.get(parent_asin, len(self.products)),
        )[: max(1, int(limit))]

    def fallback(self, limit: int = 200) -> list[str]:
        return self._fallback_ids[: max(0, int(limit))]

    def popularity_position(self, parent_asin: str) -> int:
        return self._fallback_position.get(parent_asin, len(self.products))

    def attribute_counts(self, product_ids: Iterable[str], attribute: str) -> Counter[str]:
        counts: Counter[str] = Counter()
        for parent_asin in product_ids:
            product = self.products.get(parent_asin)
            if product is not None:
                counts.update(product.attribute_values(attribute))
        return counts

    def close(self) -> None:
        with self._lock:
            self.connection.close()
