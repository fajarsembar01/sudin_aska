"""Helpers for jenjang-specific classroom configuration and room naming."""

from __future__ import annotations

import re
from typing import Any

PAUD_GROUP_JENJANGS = {"SPS", "TPA", "KB"}
PAKET_JENJANGS = {"SKB", "PKBM"}
SLB_TYPE_OPTIONS = (
    {"code": "A", "label": "A", "description": "Tunanetra (hambatan penglihatan)."},
    {"code": "B", "label": "B", "description": "Tunarungu (hambatan pendengaran)."},
    {
        "code": "C",
        "label": "C",
        "description": "Tunagrahita Ringan (hambatan intelektual ringan).",
    },
    {
        "code": "C1",
        "label": "C1",
        "description": "Tunagrahita Sedang (hambatan intelektual sedang).",
    },
    {"code": "D", "label": "D", "description": "Tunadaksa (hambatan fisik/motorik)."},
    {
        "code": "E",
        "label": "E",
        "description": "Tunalaras (hambatan emosi dan perilaku).",
    },
    {
        "code": "G",
        "label": "G",
        "description": "Tunaganda (kombinasi dua atau lebih ketunaan).",
    },
)
SLB_TYPE_CODES = tuple(item["code"] for item in SLB_TYPE_OPTIONS)


def normalize_jenjang(jenjang: str | None) -> str:
    return (jenjang or "").strip().upper()


def is_kelompok_jenjang(jenjang: str | None) -> bool:
    return normalize_jenjang(jenjang) in PAUD_GROUP_JENJANGS


def is_template_only_classroom_jenjang(jenjang: str | None) -> bool:
    return False


def encode_slb_grade(level: int, type_code: str) -> int:
    normalized_type = type_code.upper()
    if normalized_type not in SLB_TYPE_CODES:
        raise ValueError(f"Unsupported SLB type: {type_code}")
    return 1000 + (level * 10) + SLB_TYPE_CODES.index(normalized_type) + 1


def decode_slb_grade(code: int) -> tuple[int, str] | None:
    if code < 1011:
        return None
    level = (code - 1000) // 10
    type_index = (code - 1000) % 10
    if level < 1 or level > 12 or type_index < 1 or type_index > len(SLB_TYPE_CODES):
        return None
    return level, SLB_TYPE_CODES[type_index - 1]


def get_slb_type_options() -> list[dict[str, str]]:
    return [dict(item) for item in SLB_TYPE_OPTIONS]


def _slb_encoded_levels() -> list[dict[str, Any]]:
    levels: list[dict[str, Any]] = []
    for level in range(1, 13):
        for type_config in SLB_TYPE_OPTIONS:
            type_code = str(type_config["code"])
            levels.append(
                {
                    "code": encode_slb_grade(level, type_code),
                    "label": f"{level}{type_code}",
                    "variant_style": "numeric",
                    "bucket": "slb",
                }
            )
    return levels


def get_classroom_levels(
    jenjang: str | None, for_profile: bool = False
) -> list[dict[str, Any]]:
    upper = normalize_jenjang(jenjang)

    if upper == "PAUD":
        return [
            {"code": -2, "label": "KB", "variant_style": "numeric", "bucket": "paud"},
            {
                "code": -1,
                "label": "Kelompok A",
                "variant_style": "numeric",
                "bucket": "paud",
            },
            {
                "code": 0,
                "label": "Kelompok B",
                "variant_style": "numeric",
                "bucket": "paud",
            },
        ]
    if upper == "TK":
        return [
            {"code": -1, "label": "TK A", "variant_style": "numeric", "bucket": "tk"},
            {"code": 0, "label": "TK B", "variant_style": "numeric", "bucket": "tk"},
        ]
    if upper in PAUD_GROUP_JENJANGS:
        return [
            {
                "code": -1,
                "label": "Kelompok A",
                "variant_style": "numeric",
                "bucket": "paud",
            },
            {
                "code": 0,
                "label": "Kelompok B",
                "variant_style": "numeric",
                "bucket": "paud",
            },
        ]
    if upper == "SD":
        return [
            {
                "code": grade,
                "label": f"Kelas {grade}",
                "variant_style": "alpha",
                "bucket": "sd",
            }
            for grade in range(1, 7)
        ]
    if upper == "SMP":
        return [
            {
                "code": grade,
                "label": f"Kelas {grade}",
                "variant_style": "alpha",
                "bucket": "smp",
            }
            for grade in range(7, 10)
        ]
    if upper in {"SMA", "SMK"}:
        return [
            {
                "code": grade,
                "label": f"Kelas {grade}",
                "variant_style": "alpha",
                "bucket": "sma",
            }
            for grade in range(10, 13)
        ]
    if upper in PAKET_JENJANGS:
        return [
            {
                "code": -21,
                "label": "Paket A",
                "variant_style": "numeric",
                "bucket": "paket",
            },
            {
                "code": -22,
                "label": "Paket B",
                "variant_style": "numeric",
                "bucket": "paket",
            },
            {
                "code": -23,
                "label": "Paket C",
                "variant_style": "numeric",
                "bucket": "paket",
            },
        ]
    if upper == "SLB":
        if for_profile:
            return []
        slb_types = get_slb_type_options()
        return [
            {
                "code": level,
                "label": f"Kelas {level}",
                "variant_style": "numeric",
                "bucket": "slb",
                "slb_types": slb_types,
            }
            for level in range(1, 13)
        ]
    return []


def expected_grade_levels(jenjang: str | None) -> list[int]:
    return [
        int(level["code"]) for level in get_classroom_levels(jenjang, for_profile=True)
    ]


def classroom_grade_levels(jenjang: str | None) -> list[int]:
    if normalize_jenjang(jenjang) == "SLB":
        return [int(level["code"]) for level in _slb_encoded_levels()]
    return [
        int(level["code"]) for level in get_classroom_levels(jenjang, for_profile=False)
    ]


def _level_config(
    jenjang: str | None, grade: int, for_profile: bool = False
) -> dict[str, Any] | None:
    for level in get_classroom_levels(jenjang, for_profile=for_profile):
        if int(level["code"]) == int(grade):
            return level
    return None


def grade_label(jenjang: str | None, grade: int) -> str:
    config = _level_config(jenjang, grade, for_profile=False) or _level_config(
        jenjang, grade, for_profile=True
    )
    if config:
        return str(config["label"])
    decoded = decode_slb_grade(int(grade))
    if decoded:
        return f"{decoded[0]}{decoded[1]}"
    return f"Kelas {grade}"


def grade_label_map(jenjang: str | None, for_profile: bool = False) -> dict[str, str]:
    if normalize_jenjang(jenjang) == "SLB" and not for_profile:
        return {
            str(level["code"]): str(level["label"]) for level in _slb_encoded_levels()
        }
    return {
        str(level["code"]): str(level["label"])
        for level in get_classroom_levels(jenjang, for_profile=for_profile)
    }


def variant_style(jenjang: str | None, grade: int) -> str:
    if normalize_jenjang(jenjang) == "SLB" and decode_slb_grade(int(grade)):
        return "numeric"
    config = _level_config(jenjang, grade, for_profile=False) or _level_config(
        jenjang, grade, for_profile=True
    )
    if config:
        return str(config.get("variant_style") or "alpha")
    return "alpha"


def normalize_variant(jenjang: str | None, grade: int, variant: Any) -> str:
    raw = str(variant or "").strip().upper()
    if not raw:
        return ""
    if variant_style(jenjang, grade) == "numeric":
        if raw.isdigit() and int(raw) > 0:
            return str(int(raw))
        return ""
    if len(raw) == 1 and raw.isalpha():
        return raw
    return ""


def build_classroom_name(jenjang: str | None, grade: int, variant: Any) -> str:
    upper = normalize_jenjang(jenjang)
    normalized = normalize_variant(jenjang, grade, variant)
    label = grade_label(jenjang, grade)

    if upper == "TK":
        return f"Kelas {label}{normalized}".strip()
    if (
        upper in PAUD_GROUP_JENJANGS
        or upper in PAKET_JENJANGS
        or (upper == "PAUD" and grade in (-2, -1, 0))
    ):
        return f"{label}{normalized}".strip()
    if upper == "SLB":
        return f"{label} - {normalized}".strip()
    return f"Kelas {grade}{normalized}".strip()


def build_room_name(jenjang: str | None, grade: int, variant: Any) -> str:
    upper = normalize_jenjang(jenjang)
    normalized = normalize_variant(jenjang, grade, variant)
    label = grade_label(jenjang, grade)

    if upper == "TK":
        return f"Ruang Kelas {label}{normalized}".strip()
    if upper in PAUD_GROUP_JENJANGS or upper in PAKET_JENJANGS:
        return f"Ruang {label}{normalized}".strip()
    if upper == "SLB":
        return f"Ruang Kelas {label} - {normalized}".strip()
    if upper == "PAUD" and grade in (-2, -1, 0):
        return f"Ruang {label}{normalized}".strip()
    return f"Ruang Kelas {grade}{normalized}".strip()


def get_template_room_name(jenjang: str | None) -> str | None:
    upper = normalize_jenjang(jenjang)
    if upper == "PAUD" or upper in PAUD_GROUP_JENJANGS:
        return "Ruang Kelas PAUD"
    if upper == "TK":
        return "Ruang Kelas -1"
    if upper in PAKET_JENJANGS:
        return "Ruang Kelas Paket"
    if upper == "SLB":
        return "Ruang Kelas SLB"
    return None


def _parse_room_for_jenjang(name: str, jenjang: str) -> dict[str, Any] | None:
    upper = normalize_jenjang(jenjang)

    if upper == "TK":
        match = re.match(
            r"^\s*(?:Ruang\s+)?Kelas\s+TK\s+A(\d+)\s*$", name, flags=re.IGNORECASE
        )
        if match:
            return {
                "grade_level": -1,
                "variant": match.group(1),
                "is_variant": True,
                "bucket": "tk",
            }
        match = re.match(
            r"^\s*(?:Ruang\s+)?Kelas\s+TK\s+B(\d+)\s*$", name, flags=re.IGNORECASE
        )
        if match:
            return {
                "grade_level": 0,
                "variant": match.group(1),
                "is_variant": True,
                "bucket": "tk",
            }
        if re.match(r"^\s*(?:Ruang\s+)?Kelas\s+TK\s*$", name, flags=re.IGNORECASE):
            return {
                "grade_level": -1,
                "variant": "",
                "is_variant": False,
                "bucket": "tk",
            }
        if re.match(r"^\s*(?:Ruang\s+)?Kelas\s+-1\s*$", name, flags=re.IGNORECASE):
            return {
                "grade_level": -1,
                "variant": "",
                "is_variant": False,
                "bucket": "tk",
            }

    if upper == "PAUD":
        match = re.match(r"^\s*(?:Ruang\s+)?KB(\d+)\s*$", name, flags=re.IGNORECASE)
        if match:
            return {
                "grade_level": -2,
                "variant": match.group(1),
                "is_variant": True,
                "bucket": "paud",
            }
        match = re.match(
            r"^\s*(?:Ruang\s+)?Kelompok\s+([AB])(\d+)\s*$", name, flags=re.IGNORECASE
        )
        if match:
            return {
                "grade_level": -1 if match.group(1).upper() == "A" else 0,
                "variant": match.group(2),
                "is_variant": True,
                "bucket": "paud",
            }
        if re.match(r"^\s*(?:Ruang\s+)?Kelas\s+PAUD\s*$", name, flags=re.IGNORECASE):
            return {
                "grade_level": -2,
                "variant": "",
                "is_variant": False,
                "bucket": "paud",
            }

    if upper in PAUD_GROUP_JENJANGS:
        match = re.match(
            r"^\s*(?:Ruang\s+)?Kelompok\s+([AB])(\d+)\s*$", name, flags=re.IGNORECASE
        )
        if match:
            return {
                "grade_level": -1 if match.group(1).upper() == "A" else 0,
                "variant": match.group(2),
                "is_variant": True,
                "bucket": "paud",
            }
        if re.match(r"^\s*Kelompok\s+([AB])(\d+)\s*$", name, flags=re.IGNORECASE):
            match = re.match(
                r"^\s*Kelompok\s+([AB])(\d+)\s*$", name, flags=re.IGNORECASE
            )
            return {
                "grade_level": -1 if match.group(1).upper() == "A" else 0,
                "variant": match.group(2),
                "is_variant": True,
                "bucket": "paud",
            }

    if upper in PAKET_JENJANGS:
        match = re.match(
            r"^\s*(?:Ruang\s+)?Paket\s+([ABC])(\d+)\s*$", name, flags=re.IGNORECASE
        )
        if match:
            grade_map = {"A": -21, "B": -22, "C": -23}
            return {
                "grade_level": grade_map[match.group(1).upper()],
                "variant": match.group(2),
                "is_variant": True,
                "bucket": "paket",
            }
        if re.match(r"^\s*Paket\s+([ABC])(\d+)\s*$", name, flags=re.IGNORECASE):
            match = re.match(r"^\s*Paket\s+([ABC])(\d+)\s*$", name, flags=re.IGNORECASE)
            grade_map = {"A": -21, "B": -22, "C": -23}
            return {
                "grade_level": grade_map[match.group(1).upper()],
                "variant": match.group(2),
                "is_variant": True,
                "bucket": "paket",
            }

    if upper == "SLB":
        match = re.match(
            r"^\s*(?:Ruang\s+Kelas\s+)?(\d+)([A-Z](?:1)?)\s*-\s*(\d+)\s*$",
            name,
            flags=re.IGNORECASE,
        )
        if match:
            type_code = match.group(2).upper()
            if type_code not in SLB_TYPE_CODES:
                return None
            return {
                "grade_level": encode_slb_grade(int(match.group(1)), type_code),
                "variant": match.group(3),
                "is_variant": True,
                "bucket": "slb",
            }
        if re.match(r"^\s*Ruang\s+Kelas\s+SLB\s*$", name, flags=re.IGNORECASE):
            return {
                "grade_level": 0,
                "variant": "",
                "is_variant": False,
                "bucket": "slb",
            }

    if upper in {"SD", "SMP", "SMA", "SMK", ""}:
        match = re.match(
            r"^\s*(?:Ruang\s+)?Kelas\s+(-?\d+)\s*([A-Za-z])\s*$",
            name,
            flags=re.IGNORECASE,
        )
        if match:
            bucket = (
                "sd"
                if 1 <= int(match.group(1)) <= 6
                else "smp" if 7 <= int(match.group(1)) <= 9 else "sma"
            )
            return {
                "grade_level": int(match.group(1)),
                "variant": match.group(2).upper(),
                "is_variant": True,
                "bucket": bucket,
            }
        match = re.search(r"\bKelas\s+(-?\d+)\b", name, flags=re.IGNORECASE)
        if match:
            grade = int(match.group(1))
            bucket = (
                "sd"
                if 1 <= grade <= 6
                else (
                    "smp" if 7 <= grade <= 9 else "sma" if 10 <= grade <= 12 else "umum"
                )
            )
            return {
                "grade_level": grade,
                "variant": "",
                "is_variant": False,
                "bucket": bucket,
            }

    return None


def parse_room_info(
    name: str | None, jenjang: str | None = None
) -> dict[str, Any] | None:
    value = re.sub(r"\s+", " ", (name or "").strip())
    if not value:
        return None

    upper = normalize_jenjang(jenjang)
    if upper:
        return _parse_room_for_jenjang(value, upper)

    for candidate in [
        "TK",
        "PAUD",
        *sorted(PAUD_GROUP_JENJANGS),
        *sorted(PAKET_JENJANGS),
        "SLB",
        "SD",
        "SMP",
        "SMA",
    ]:
        parsed = _parse_room_for_jenjang(value, candidate)
        if parsed:
            return parsed
    return None


def sanitize_submitted_classrooms(
    jenjang: str | None, classrooms: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    allowed_grades = set(classroom_grade_levels(jenjang))
    sanitized: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()

    for classroom in classrooms or []:
        try:
            grade = int(classroom.get("grade_level"))
        except (TypeError, ValueError):
            continue
        if grade not in allowed_grades:
            continue
        variant = normalize_variant(jenjang, grade, classroom.get("variant"))
        if not variant:
            continue
        key = (grade, variant)
        if key in seen:
            continue
        seen.add(key)
        sanitized.append(
            {
                "name": build_classroom_name(jenjang, grade, variant),
                "grade_level": grade,
                "variant": variant,
                "capacity": classroom.get("capacity"),
                "notes": classroom.get("notes"),
            }
        )

    sanitized.sort(key=lambda item: (int(item["grade_level"]), str(item["variant"])))
    return sanitized
