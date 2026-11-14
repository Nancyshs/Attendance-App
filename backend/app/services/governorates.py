"""Egyptian governorates and the letter used in a trainee code (C01, G02, …).

There are 27 governorates and 26 English letters, so شمال سيناء and جنوب سيناء
share ``J`` and their numbers run in one sequence. Every other governorate has
its own letter.
"""
from __future__ import annotations

import re

# Display order. The letter is what the trainee code starts with.
GOVERNORATES: tuple[tuple[str, str], ...] = (
    ("القاهرة", "C"),
    ("الجيزة", "G"),
    ("الإسكندرية", "A"),
    ("الدقهلية", "D"),
    ("البحر الأحمر", "R"),
    ("البحيرة", "B"),
    ("الفيوم", "F"),
    ("الغربية", "H"),
    ("الإسماعيلية", "I"),
    ("المنوفية", "M"),
    ("المنيا", "Y"),
    ("القليوبية", "Q"),
    ("الوادي الجديد", "V"),
    ("السويس", "E"),
    ("أسوان", "U"),
    ("أسيوط", "O"),
    ("بني سويف", "W"),
    ("بورسعيد", "P"),
    ("دمياط", "T"),
    ("الشرقية", "Z"),
    ("جنوب سيناء", "J"),
    ("شمال سيناء", "J"),
    ("كفر الشيخ", "K"),
    ("مطروح", "X"),
    ("الأقصر", "L"),
    ("قنا", "N"),
    ("سوهاج", "S"),
)

_LETTER = dict(GOVERNORATES)

_AR_MAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})
_DIACRITICS = re.compile(r"[\u064B-\u0652\u0670]")

# English names accepted on import, folded the same way as Arabic.
_ENGLISH = {
    "cairo": "القاهرة",
    "giza": "الجيزة",
    "alexandria": "الإسكندرية",
    "dakahlia": "الدقهلية",
    "redsea": "البحر الأحمر",
    "beheira": "البحيرة",
    "fayoum": "الفيوم",
    "faiyum": "الفيوم",
    "gharbia": "الغربية",
    "ismailia": "الإسماعيلية",
    "monufia": "المنوفية",
    "menoufia": "المنوفية",
    "minya": "المنيا",
    "qalyubia": "القليوبية",
    "newvalley": "الوادي الجديد",
    "suez": "السويس",
    "aswan": "أسوان",
    "asyut": "أسيوط",
    "assiut": "أسيوط",
    "benisuef": "بني سويف",
    "portsaid": "بورسعيد",
    "damietta": "دمياط",
    "sharqia": "الشرقية",
    "sharkia": "الشرقية",
    "southsinai": "جنوب سيناء",
    "northsinai": "شمال سيناء",
    "kafrelsheikh": "كفر الشيخ",
    "matrouh": "مطروح",
    "marsamatrouh": "مطروح",
    "luxor": "الأقصر",
    "qena": "قنا",
    "sohag": "سوهاج",
}


def _fold(value: str) -> str:
    s = _DIACRITICS.sub("", value.strip())
    s = s.translate(_AR_MAP)
    s = re.sub(r"[\s_\-]+", "", s)
    s = s.casefold()
    if s.startswith("محافظه"):
        s = s[len("محافظه") :]
    return s


_BY_FOLD = {_fold(name): name for name, _letter in GOVERNORATES}
_BY_FOLD.update(_ENGLISH)


def canonical_governorate(value: str | None) -> str | None:
    """Official Arabic name, or None when the text is empty or not a governorate."""
    if value is None:
        return None
    folded = _fold(value)
    if not folded:
        return None
    return _BY_FOLD.get(folded)


def letter_for(governorate: str | None) -> str | None:
    name = canonical_governorate(governorate)
    if name is None:
        return None
    return _LETTER[name]


def options() -> list[dict[str, str]]:
    return [{"name": name, "letter": letter} for name, letter in GOVERNORATES]
