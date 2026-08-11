import hmac
import re
import secrets


NIP_PATTERN = re.compile(r"^\d{18}$")
TOKEN_PATTERN = re.compile(r"^\d{6}$")


def generate_access_token() -> str:
    """Return a zero-padded, cryptographically random six-digit PIN."""
    return f"{secrets.randbelow(1_000_000):06d}"


def validate_external_identity(name: str, nip: str) -> list[str]:
    errors = []
    if len((name or "").strip()) < 3:
        errors.append("Nama guru wajib diisi minimal 3 karakter.")
    elif len(name.strip()) > 150:
        errors.append("Nama guru maksimal 150 karakter.")
    errors.extend(validate_external_nip(nip))
    return errors


def validate_external_nip(nip: str) -> list[str]:
    if not NIP_PATTERN.fullmatch((nip or "").strip()):
        return ["NIP wajib terdiri dari tepat 18 digit."]
    return []


def access_token_matches(provided: str, expected: str) -> bool:
    provided = (provided or "").strip()
    expected = (expected or "").strip()
    return bool(
        TOKEN_PATTERN.fullmatch(provided)
        and TOKEN_PATTERN.fullmatch(expected)
        and hmac.compare_digest(provided, expected)
    )
