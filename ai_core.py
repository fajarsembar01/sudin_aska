import hashlib
import json
import logging
import os
import re
import shutil
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from langchain.chains import create_history_aware_retriever
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter

# --- Embed Logger ---
_embed_log = logging.getLogger("aska.embed")
if not _embed_log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter("[%(asctime)s] [EMBED] %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    _embed_log.addHandler(_handler)
    _embed_log.setLevel(logging.DEBUG)
    _embed_log.propagate = False


def _embed_log_also_file(msg: str, level: str = "info") -> None:
    """Log ke stderr dan juga ke file .embed.log di root project."""
    log_path = Path(__file__).resolve().parent / ".embed.log"
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [{level.upper()}] {msg}\n")
    except OSError:
        pass
    getattr(_embed_log, level, _embed_log.info)(msg)

from knowledge_loader import load_kecerdasan

try:  # opsional, hanya dipakai bila backend lokal diaktifkan
    from langchain_huggingface import HuggingFaceEmbeddings
except Exception:  # pragma: no cover - optional dependency
    HuggingFaceEmbeddings = None  # type: ignore[misc,assignment]

load_dotenv()

def _is_truthy(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_falsey(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in {"0", "false", "no", "off"}


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)


def _env_float(name: str, default: float, *, minimum: float = 0.0, maximum: float = 1.0) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return min(maximum, max(minimum, value))


_QUERY_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_SCHOOL_NUMBER_RE = re.compile(
    r"\b(sman|sma|smkn|smpn|smp|sdn|sd)\s*(?:negeri\s*)?(\d{1,3})\b",
    re.IGNORECASE,
)
_SD_NAMED_RE = re.compile(
    r"\b(?:sdn|sd\s*n|sd\s+negeri|sd)\s+([a-z]+(?:\s+[a-z]+){0,6}?)\s+(\d{1,2})(?:\s+(?:jakarta|pagi|pg))?\b",
    re.IGNORECASE,
)
_SPMB_TERMS = ("spmb", "pmb", "penerimaan murid baru")
_SCHEDULE_TERMS = ("jadwal", "kapan", "pendaftaran", "pengajuan akun", "daftar ulang")
_PMB_LEVELS = ("spaud", "sd", "smp", "sma", "smk", "slb", "skb")
_SCHOOL_LEVEL_PATTERNS = {
    "sd": re.compile(r"\b(?:sdn|sd\s*n|sd\s+negeri|sd|sekolah dasar)\b", re.IGNORECASE),
    "smp": re.compile(r"\b(?:smpn|smp\s+negeri|smp|sekolah menengah pertama)\b", re.IGNORECASE),
    "sma": re.compile(r"\b(?:sman|sma\s+negeri|sma|sekolah menengah atas)\b", re.IGNORECASE),
    "smk": re.compile(r"\b(?:smkn|smk\s+negeri|smk|sekolah menengah kejuruan)\b", re.IGNORECASE),
}
_LOCATION_QUERY_PATTERNS = (
    re.compile(r"\b(?:rumah|tinggal|domisili|alamat)(?:\s+(?:saya|aku|kami|anak|cmb|calon murid)){0,3}\s+(?:ada\s+)?(?:di|dari)\s+([a-z]+(?:\s+[a-z]+){0,5})", re.IGNORECASE),
    re.compile(r"\b(?:kelurahan|kel\.?)\s+([a-z]+(?:\s+[a-z]+){0,5})", re.IGNORECASE),
)
_LOCATION_TRAILING_STOPWORDS = {
    "apa",
    "atau",
    "buat",
    "dan",
    "dekat",
    "dong",
    "jakarta",
    "kalau",
    "ke",
    "kec",
    "kecamatan",
    "kel",
    "kelurahan",
    "pilih",
    "saja",
    "sekolah",
    "sih",
    "smp",
    "sma",
    "sd",
    "smk",
    "untuk",
    "ya",
    "yang",
}
_ASKA_PROFILE_MARKERS = (
    "## apa itu aska",
    "## manfaat aska",
    "## tujuan pembuatan",
    "agent ai sekolah kita",
)


def _normalize_search_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _contains_phrase(text: str, phrase: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text) is not None


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _is_spmb_schedule_query(question_norm: str) -> bool:
    return _has_any(question_norm, _SPMB_TERMS) and _has_any(question_norm, _SCHEDULE_TERMS)


def _requested_pmb_levels(question_norm: str) -> tuple[str, ...]:
    return tuple(level for level in _PMB_LEVELS if re.search(rf"\b{level}\b", question_norm))


def _requested_school_levels(question_norm: str) -> tuple[str, ...]:
    return tuple(level for level, pattern in _SCHOOL_LEVEL_PATTERNS.items() if pattern.search(question_norm))


def _doc_matches_school_level(content_norm: str, level: str) -> bool:
    if level == "sd":
        return (
            "wilayah pmb prioritas" in content_norm
            and (
                re.search(r"####\s*\d+\.\s+sdn\b", content_norm)
                or re.search(r"####\s*\d+\.\s+sd\s*n\b", content_norm)
            )
        )
    if level == "smp":
        return "wilayah pmb prioritas" in content_norm and re.search(r"####\s*\d+\.\s+smp negeri\b", content_norm)
    if level == "sma":
        return "wilayah pmb prioritas" in content_norm and re.search(r"####\s*\d+\.\s+sma negeri\b", content_norm)
    if level == "smk":
        return "wilayah pmb prioritas" in content_norm and re.search(r"####\s*\d+\.\s+smk negeri\b", content_norm)
    return False


def _clean_location_phrase(value: str) -> str:
    tokens = _QUERY_TOKEN_RE.findall(_normalize_search_text(value))
    kept = []
    for token in tokens:
        if token in _LOCATION_TRAILING_STOPWORDS:
            break
        kept.append(token)
    return " ".join(kept[:4])


def _extract_residence_location(question_norm: str) -> str:
    for pattern in _LOCATION_QUERY_PATTERNS:
        match = pattern.search(question_norm)
        if not match:
            continue
        location = _clean_location_phrase(match.group(1))
        if len(location) >= 3:
            return location
    return ""


def _location_priority_score(content_norm: str, location: str) -> int:
    best = 0
    for match in re.finditer(rf"(?<![a-z0-9]){re.escape(location)}(?![a-z0-9])", content_norm):
        nearby_before = content_norm[max(0, match.start() - 260):match.start()]
        if "prioritas pertama" in nearby_before:
            best = max(best, 360)
        elif "prioritas kedua" in nearby_before:
            best = max(best, 220)
        elif "prioritas ketiga" in nearby_before:
            best = max(best, 90)
        else:
            best = max(best, 30)
    return best


def _school_block_key(block: str) -> str:
    match = re.search(r"^####\s+\d+\.\s+(.+)$", block, flags=re.MULTILINE)
    if match:
        return _normalize_search_text(match.group(1))
    return hashlib.sha1(block.encode("utf-8", errors="ignore")).hexdigest()


def _sd_named_variants(question_norm: str) -> tuple[str, ...]:
    match = _SD_NAMED_RE.search(question_norm)
    if not match:
        return ()
    school_name = re.sub(r"\s+", " ", match.group(1)).strip()
    school_no = (match.group(2).lstrip("0") or "0")
    school_no_padded = school_no.zfill(2)
    return (
        f"sdn {school_name} {school_no_padded}",
        f"sdn {school_name} {school_no}",
        f"sd n {school_name} {school_no_padded}",
        f"sd n {school_name} {school_no}",
        f"sd negeri {school_name} {school_no_padded}",
        f"sd negeri {school_name} {school_no}",
    )


def _looks_like_spmb_schedule_content(content_norm: str) -> bool:
    has_summary_schedule = (
        "ringkasan jadwal spmb" in content_norm
        or "ringkasan jadwal spmb/pmb" in content_norm
        or "ringkasan jadwal pendaftaran utama" in content_norm
    )
    has_schedule_rows = all(marker in content_norm for marker in ("kegiatan:", "tanggal:", "waktu:"))
    has_account_schedule = (
        "pengajuan akun dan verifikasi kartu keluarga" in content_norm
        or "jadwal pengajuan akun" in content_norm
        or "jadwal pengajuan akun/verifikasi kk" in content_norm
    )
    has_pmb_context = _has_any(content_norm, _SPMB_TERMS) or re.search(
        r"\bpmb\s+(sd|smp|sma|smk|slb|skb|spaud)\b",
        content_norm,
    )
    has_current_year = "2026" in content_norm or "2026/2027" in content_norm
    return bool(has_summary_schedule or ((has_schedule_rows or has_account_schedule) and (has_pmb_context or has_current_year)))


def _document_keyword_boost(question: str, page_content: str) -> int:
    question_norm = _normalize_search_text(question)
    content_norm = _normalize_search_text(page_content)
    if not question_norm or not content_norm:
        return 0

    boost = 0
    residence_location = _extract_residence_location(question_norm)
    requested_school_levels = _requested_school_levels(question_norm)
    if residence_location and _contains_phrase(content_norm, residence_location):
        priority_score = _location_priority_score(content_norm, residence_location)
        if priority_score:
            boost += priority_score
            if requested_school_levels and any(_doc_matches_school_level(content_norm, level) for level in requested_school_levels):
                boost += 180
            elif requested_school_levels:
                boost -= 80

    sd_named_variants = _sd_named_variants(question_norm)
    if sd_named_variants and any(_contains_phrase(content_norm, variant) for variant in sd_named_variants):
        boost += 160
        if "wilayah pmb prioritas" in content_norm:
            boost += 60

    school_match = _SCHOOL_NUMBER_RE.search(question_norm)
    if school_match:
        school_kind = school_match.group(1)
        school_no = school_match.group(2)
        if school_kind.startswith("sma"):
            school_variants = (
                f"sma negeri {school_no}",
                f"sman {school_no}",
                f"sma {school_no}",
                f"#### {school_no}. sma",
                f"{school_no}. sma negeri",
            )
        elif school_kind.startswith("smk"):
            school_variants = (
                f"smk negeri {school_no}",
                f"smkn {school_no}",
                f"smk {school_no}",
                f"#### {school_no}. smk",
                f"{school_no}. smk negeri",
            )
        elif school_kind.startswith("smp"):
            school_variants = (
                f"smp negeri {school_no}",
                f"smpn {school_no}",
                f"smp {school_no}",
                f"#### {school_no}. smp",
                f"{school_no}. smp negeri",
            )
        else:
            school_variants = (
                f"sdn {school_no}",
                f"sd negeri {school_no}",
                f"sd {school_no}",
                f"{school_no}. sdn",
            )
        if any(_contains_phrase(content_norm, variant) for variant in school_variants):
            boost += 120
        if school_kind[:2] in content_norm and re.search(rf"\b{re.escape(school_no)}\b", content_norm):
            boost += 40

    if "prioritas" in question_norm:
        if "wilayah pmb prioritas" in content_norm:
            boost += 25
        if all(keyword in content_norm for keyword in ("prioritas pertama", "prioritas kedua", "prioritas ketiga")):
            boost += 35

    if _is_spmb_schedule_query(question_norm):
        requested_levels = _requested_pmb_levels(question_norm)
        if _has_any(content_norm, _ASKA_PROFILE_MARKERS):
            boost -= 120
        if "ringkasan jadwal spmb" in content_norm or "ringkasan jadwal spmb/pmb" in content_norm:
            boost += 260
        if _looks_like_spmb_schedule_content(content_norm):
            boost += 140
        for level in requested_levels:
            if re.search(rf"\bpmb\s+{level}\b", content_norm):
                boost += 180
            if re.search(rf"#+\s*\d+\)?\s*pmb\s+{level}\b", content_norm):
                boost += 80
            if (
                "pengajuan akun dan verifikasi kartu keluarga" in content_norm
                and re.search(rf"\b{level}\s*:", content_norm)
            ):
                boost += 40
        if "bab iv. pendaftaran" in content_norm:
            boost += 50
        if "jadwal pendaftaran" in content_norm:
            boost += 70
        if "pengajuan akun dan verifikasi kartu keluarga" in content_norm:
            boost += 70
        if "spmb.jakarta.go.id" in content_norm:
            boost += 25
        if "2026/2027" in content_norm:
            boost += 35
        if "2026" in content_norm:
            boost += 20
        if "2025" in content_norm and "2026" not in content_norm:
            boost -= 70

    query_tokens = {
        token
        for token in _QUERY_TOKEN_RE.findall(question_norm)
        if len(token) > 2 and token not in {"untuk", "yang", "dan", "atau", "dari", "sampai", "tanya"}
    }
    boost += sum(1 for token in query_tokens if token in content_norm)
    return boost


def _rank_and_limit_documents(question: str, docs: list) -> list:
    if not docs:
        return []

    max_docs = _env_int("ASKA_CONTEXT_MAX_DOCS", 4, minimum=1)
    max_chars = _env_int("ASKA_CONTEXT_MAX_CHARS", 4500, minimum=500)
    ranked = sorted(
        enumerate(docs),
        key=lambda item: (
            -_document_keyword_boost(question, getattr(item[1], "page_content", "")),
            item[0],
        ),
    )

    selected = []
    used_chars = 0
    for _, doc in ranked:
        text = getattr(doc, "page_content", "")
        doc_len = len(text)
        if selected and (len(selected) >= max_docs or used_chars + doc_len > max_chars):
            continue
        selected.append(doc)
        used_chars += doc_len
        if len(selected) >= max_docs or used_chars >= max_chars:
            break
    return selected


def _iter_vectorstore_documents(vectorstore: FAISS):
    docstore_dict = getattr(getattr(vectorstore, "docstore", None), "_dict", {})
    if isinstance(docstore_dict, dict):
        yield from docstore_dict.values()


def _location_documents_from_vectorstore(vectorstore: FAISS, question: str, *, limit: int = 8) -> list:
    question_norm = _normalize_search_text(question)
    location = _extract_residence_location(question_norm)
    requested_levels = _requested_school_levels(question_norm)
    if not location or not requested_levels:
        return []

    matches = []
    seen_blocks = set()
    for doc in _iter_vectorstore_documents(vectorstore):
        content = getattr(doc, "page_content", "")
        content_norm = _normalize_search_text(content)
        if not _contains_phrase(content_norm, location):
            continue

        blocks = [
            block.strip()
            for block in re.split(r"(?=^####\s+\d+\.\s+)", content, flags=re.MULTILINE)
            if block.strip()
        ]
        for block in blocks or [content]:
            block_norm = _normalize_search_text(block)
            if not _contains_phrase(block_norm, location):
                continue
            if not any(_doc_matches_school_level(block_norm, level) for level in requested_levels):
                continue
            if not _location_priority_score(block_norm, location):
                continue
            block_key = _school_block_key(block)
            if block_key in seen_blocks:
                continue
            seen_blocks.add(block_key)
            matches.append(Document(page_content=block))

    matches.sort(key=lambda doc: -_document_keyword_boost(question, getattr(doc, "page_content", "")))
    return matches[:limit]


def _keyword_documents_from_vectorstore(vectorstore: FAISS, question: str, *, limit: int = 5) -> list:
    question_norm = _normalize_search_text(question)
    location_docs = _location_documents_from_vectorstore(vectorstore, question, limit=limit)
    if location_docs:
        return location_docs

    school_match = _SCHOOL_NUMBER_RE.search(question_norm)
    if not school_match:
        sd_named_variants = _sd_named_variants(question_norm)
        if sd_named_variants:
            matches = []
            for doc in _iter_vectorstore_documents(vectorstore):
                content = getattr(doc, "page_content", "")
                content_norm = _normalize_search_text(content)
                if any(_contains_phrase(content_norm, variant) for variant in sd_named_variants):
                    matches.append(doc)
            matches.sort(key=lambda doc: -_document_keyword_boost(question, getattr(doc, "page_content", "")))
            return matches[:limit]

        if not _is_spmb_schedule_query(question_norm):
            return []

        matches = []
        for doc in _iter_vectorstore_documents(vectorstore):
            content = getattr(doc, "page_content", "")
            content_norm = _normalize_search_text(content)
            if _looks_like_spmb_schedule_content(content_norm):
                matches.append(doc)
        matches.sort(key=lambda doc: -_document_keyword_boost(question, getattr(doc, "page_content", "")))
        return matches[:limit]

    school_kind = school_match.group(1)
    school_no = school_match.group(2)
    if school_kind.startswith("sma"):
        variants = (
            f"sma negeri {school_no}",
            f"sman {school_no}",
            f"#### {school_no}. sma",
            f"{school_no}. sma negeri",
        )
    elif school_kind.startswith("smk"):
        variants = (
            f"smk negeri {school_no}",
            f"smkn {school_no}",
            f"#### {school_no}. smk",
            f"{school_no}. smk negeri",
        )
    elif school_kind.startswith("smp"):
        variants = (
            f"smp negeri {school_no}",
            f"smpn {school_no}",
            f"#### {school_no}. smp",
            f"{school_no}. smp negeri",
        )
    else:
        variants = (
            f"sdn {school_no}",
            f"sd negeri {school_no}",
            f"{school_no}. sdn",
        )
    matches = []
    for doc in _iter_vectorstore_documents(vectorstore):
        content = getattr(doc, "page_content", "")
        content_norm = _normalize_search_text(content)
        if any(_contains_phrase(content_norm, variant) for variant in variants):
            matches.append(doc)
    matches.sort(key=lambda doc: -_document_keyword_boost(question, getattr(doc, "page_content", "")))
    return matches[:limit]


def _merge_documents(primary_docs: list, secondary_docs: list) -> list:
    merged = []
    seen = set()
    for doc in [*primary_docs, *secondary_docs]:
        content = getattr(doc, "page_content", "")
        fingerprint = hashlib.sha1(content.encode("utf-8", errors="ignore")).hexdigest()
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        merged.append(doc)
    return merged


def _history_text_for_keywords(inputs: dict, *, max_messages: int = 4) -> str:
    messages = inputs.get("chat_history") or []
    parts = []
    for message in list(messages)[-max_messages:]:
        content = getattr(message, "content", "")
        if content:
            parts.append(str(content))
    return " ".join(parts)


def _needs_history_for_keywords(question: str) -> bool:
    question_norm = _normalize_search_text(question)
    if _SCHOOL_NUMBER_RE.search(question_norm) or _sd_named_variants(question_norm):
        return False
    if _extract_residence_location(question_norm):
        return False
    if _is_spmb_schedule_query(question_norm):
        return False
    tokens = _QUERY_TOKEN_RE.findall(question_norm)
    if len(tokens) <= 4 and _has_any(question_norm, ("apa", "mana", "iya", "itu", "sekolah")):
        return True
    return False


def _keyword_query_from_inputs(inputs: dict) -> str:
    question = str(inputs.get("input") or "")
    if not _needs_history_for_keywords(question):
        return question
    history_text = _history_text_for_keywords(inputs)
    return f"{question} {history_text}".strip()


def _load_cached_vectorstore(
    *,
    cache_dir: Path,
    metadata_path: Path,
    doc_hash: str,
    chunk_size: int,
    chunk_overlap: int,
    embedding_signature: dict[str, str],
    embedding,
) -> Optional[FAISS]:
    if not cache_dir.exists() or not metadata_path.exists():
        return None
    try:
        metadata = json.loads(metadata_path.read_text())
    except Exception:
        return None
    if (
        metadata.get("doc_hash") != doc_hash
        or metadata.get("chunk_size") != chunk_size
        or metadata.get("chunk_overlap") != chunk_overlap
        or metadata.get("embedding_signature") != embedding_signature
    ):
        return None
    try:
        return FAISS.load_local(
            str(cache_dir),
            embeddings=embedding,
            allow_dangerous_deserialization=True,
        )
    except Exception as exc:  # pragma: no cover - cache corruption/environment issues
        print(f"[RAG] Gagal memuat cache FAISS: {exc}")
        return None


def _save_vectorstore_cache(
    *,
    vectorstore: FAISS,
    cache_dir: Path,
    metadata_path: Path,
    metadata: dict[str, object],
) -> None:
    cache_dir.parent.mkdir(parents=True, exist_ok=True)
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    vectorstore.save_local(str(cache_dir))
    metadata_path.write_text(json.dumps(metadata, indent=2))


def _load_cached_vectorstore_fallback(
    *,
    cache_dir: Path,
    embedding,
) -> Optional[FAISS]:
    """Muat FAISS yang sudah ada tanpa validasi hash — dipakai sebagai fallback
    agar bot tetap jalan dengan kecerdasan lama saat cache tidak cocok."""
    if not cache_dir.exists():
        return None
    try:
        vs = FAISS.load_local(
            str(cache_dir),
            embeddings=embedding,
            allow_dangerous_deserialization=True,
        )
        _embed_log_also_file(
            "[FALLBACK] Vectorstore lama berhasil dimuat — bot tetap jalan dengan kecerdasan sebelumnya.",
            "warning",
        )
        return vs
    except Exception as exc:
        _embed_log_also_file(f"[FALLBACK] Gagal memuat vectorstore lama: {exc}", "error")
        return None


def build_qa_chain():
    _embed_log_also_file("=== build_qa_chain() dipanggil ===")
    t_start = time.perf_counter()

    api_key = os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        msg = "GROQ_API_KEY (atau OPENAI_API_KEY sebagai fallback) harus di-set untuk menjalankan ASKA."
        _embed_log_also_file(msg, "error")
        raise RuntimeError(msg)

    api_base = (
        os.getenv("ASKA_OPENAI_API_BASE")
        or os.getenv("OPENAI_API_BASE")
        or os.getenv("ASKA_GROQ_API_BASE")
        or "https://api.groq.com/openai/v1"
    )
    _embed_log_also_file(f"LLM api_base: {api_base}")

    llm = ChatOpenAI(
        temperature=float(os.getenv("ASKA_QA_TEMPERATURE", "0")),
        model=os.getenv("ASKA_QA_MODEL", "llama-3.1-8b-instant"),
        max_tokens=int(os.getenv("ASKA_QA_MAX_TOKENS", "1000")),  # ⬅️ batas jawaban agar tidak ngalor ngidul
        openai_api_key=api_key,
        openai_api_base=api_base,
    )

    backend_pref = os.getenv("ASKA_EMBEDDING_BACKEND", "auto").lower()
    embedding_api_key = os.getenv("ASKA_EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY")
    embedding_signature: dict[str, str]
    _embed_log_also_file(f"ASKA_EMBEDDING_BACKEND={backend_pref!r}  api_key_ada={bool(embedding_api_key)}")

    if backend_pref not in {"auto", "openai", "local"}:
        _embed_log_also_file(f"Backend tidak dikenal '{backend_pref}', reset ke 'auto'", "warning")
        backend_pref = "auto"

    use_local = backend_pref == "local" or (backend_pref == "auto" and not embedding_api_key)
    if use_local:
        if HuggingFaceEmbeddings is None:
            msg = (
                "Embedding backend disetel ke 'local' tetapi dependensi langchain-huggingface/sentence-transformers belum terpasang."
            )
            _embed_log_also_file(msg, "error")
            raise RuntimeError(
                "Embedding backend disetel ke 'local' tetapi dependensi langchain-huggingface/sentence-transformers belum terpasang.\n"
                "Jalankan: pip install langchain-huggingface sentence-transformers torch>=1.11.0"
            )
        local_device = os.getenv("ASKA_EMBEDDING_DEVICE", "cpu")
        local_model = os.getenv(
            "ASKA_EMBEDDING_MODEL_LOCAL", "sentence-transformers/all-MiniLM-L6-v2"
        )
        _embed_log_also_file(f"Menggunakan embedding LOCAL: model={local_model!r} device={local_device!r}")
        try:
            embedding = HuggingFaceEmbeddings(
                model_name=local_model,
                model_kwargs={"device": local_device},
                encode_kwargs={"normalize_embeddings": True},
            )
            _embed_log_also_file(f"HuggingFaceEmbeddings berhasil dimuat: {local_model}")
        except Exception as exc:
            _embed_log_also_file(f"GAGAL memuat HuggingFaceEmbeddings: {exc}", "error")
            raise
        embedding_signature = {
            "provider": "huggingface",
            "model": local_model,
            "device": local_device,
        }
    else:
        if not embedding_api_key:
            msg = "Embedding backend disetel ke OpenAI, tetapi ASKA_EMBEDDING_API_KEY / OPENAI_API_KEY belum diisi."
            _embed_log_also_file(msg, "error")
            raise RuntimeError(msg)
        embedding_api_base = (
            os.getenv("ASKA_EMBEDDING_API_BASE")
            or os.getenv("OPENAI_EMBEDDING_API_BASE")
            or "https://api.openai.com/v1"
        )
        openai_embedding_model = os.getenv("ASKA_EMBEDDING_MODEL", "text-embedding-3-large")
        _embed_log_also_file(
            f"Menggunakan embedding OPENAI: model={openai_embedding_model!r} api_base={embedding_api_base!r}"
        )
        try:
            embedding = OpenAIEmbeddings(
                model=openai_embedding_model,
                openai_api_key=embedding_api_key,
                openai_api_base=embedding_api_base,
                chunk_size=_env_int("ASKA_EMBEDDING_BATCH_SIZE", 64, minimum=1),
            )
            _embed_log_also_file("OpenAIEmbeddings berhasil diinisialisasi")
        except Exception as exc:
            _embed_log_also_file(f"GAGAL inisialisasi OpenAIEmbeddings: {exc}", "error")
            raise
        embedding_signature = {
            "provider": "openai",
            "model": openai_embedding_model,
            "api_base": embedding_api_base,
        }

    content = load_kecerdasan()
    _embed_log_also_file(f"Konten kecerdasan dimuat: {len(content):,} karakter")

    chunk_size = int(os.getenv("ASKA_CHUNK_SIZE", "2000"))
    chunk_overlap = int(os.getenv("ASKA_CHUNK_OVERLAP", "200"))
    _embed_log_also_file(f"Chunking: chunk_size={chunk_size} chunk_overlap={chunk_overlap}")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n|", "\n## ", "\n\n", "\n", " ", ""],  # urutkan dari yang paling “kuat”
        keep_separator=True
    )

    doc_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    cache_root = Path(os.getenv("ASKA_VECTORSTORE_PATH", ".aska_vectorstore"))
    index_name = os.getenv("ASKA_VECTORSTORE_INDEX", "kecerdasan")
    cache_dir = cache_root / index_name
    metadata_path = cache_root / f"{index_name}.meta.json"
    _embed_log_also_file(f"doc_hash={doc_hash[:12]}...  cache_dir={cache_dir}")

    vectorstore = _load_cached_vectorstore(
        cache_dir=cache_dir,
        metadata_path=metadata_path,
        doc_hash=doc_hash,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        embedding_signature=embedding_signature,
        embedding=embedding,
    )
    if vectorstore is None:
        _embed_log_also_file("Cache FAISS tidak ditemukan / kadaluarsa.", "warning")

        allow_reindex = _is_truthy(os.getenv("ASKA_ALLOW_REMOTE_EMBEDDING_REINDEX"))
        is_remote = embedding_signature.get("provider") == "openai"

        allow_stale_fallback = not _is_falsey(os.getenv("ASKA_ALLOW_STALE_VECTORSTORE_FALLBACK", "true"))
        vectorstore = (
            _load_cached_vectorstore_fallback(
                cache_dir=cache_dir,
                embedding=embedding,
            )
            if allow_stale_fallback
            else None
        )
        if vectorstore is not None:
            # Fallback berhasil — tidak perlu rebuild, bot jalan dengan kecerdasan lama
            _embed_log_also_file(
                "Menggunakan vectorstore lama sebagai fallback. "
                "Jalankan build ulang via GitHub Actions untuk memperbarui kecerdasan.",
                "warning",
            )
        elif is_remote and not allow_reindex:
            # Tidak ada fallback & rebuild remote diblokir → raise agar tidak buang token
            msg_blocked = (
                "Cache tidak cocok, tidak ada fallback, dan re-index remote diblokir. "
                "Set ASKA_ALLOW_REMOTE_EMBEDDING_REINDEX=1 untuk rebuild, "
                "atau jalankan build via GitHub Actions lalu sync ke server."
            )
            _embed_log_also_file(msg_blocked, "error")
            raise RuntimeError(msg_blocked)
        else:
            # Tidak ada fallback, rebuild diizinkan (lokal atau ASKA_ALLOW_REMOTE_EMBEDDING_REINDEX=1)
            _embed_log_also_file("Membangun ulang vectorstore...", "warning")
            t_embed = time.perf_counter()
            docs = text_splitter.create_documents([content])
            _embed_log_also_file(f"Jumlah chunk: {len(docs)}")
            try:
                vectorstore = FAISS.from_documents(docs, embedding)
                dur_ms = int((time.perf_counter() - t_embed) * 1000)
                _embed_log_also_file(f"Embedding selesai dalam {dur_ms} ms — menyimpan cache...")
            except Exception as exc:
                _embed_log_also_file(
                    f"GAGAL saat FAISS.from_documents: {type(exc).__name__}: {exc}", "error"
                )
                raise
            _save_vectorstore_cache(
                vectorstore=vectorstore,
                cache_dir=cache_dir,
                metadata_path=metadata_path,
                metadata={
                    "doc_hash": doc_hash,
                    "chunk_size": chunk_size,
                    "chunk_overlap": chunk_overlap,
                    "embedding_signature": embedding_signature,
                },
            )
            _embed_log_also_file("Cache FAISS berhasil disimpan")
    else:
        _embed_log_also_file("Cache FAISS dimuat dari disk — embedding SKIP")

    retrieval_max_k = _env_int("ASKA_RETRIEVAL_MAX_K", 10, minimum=1)
    retrieval_min_score = _env_float("ASKA_RETRIEVAL_MIN_SCORE", 0.35)
    retriever = vectorstore.as_retriever(
        search_type="similarity_score_threshold",
        search_kwargs={"k": retrieval_max_k, "score_threshold": retrieval_min_score},
    )
    _embed_log_also_file(
        "Retrieval: search_type=similarity_score_threshold "
        f"k<={retrieval_max_k} score_threshold={retrieval_min_score}"
    )
    total_ms = int((time.perf_counter() - t_start) * 1000)
    _embed_log_also_file(f"=== build_qa_chain() selesai dalam {total_ms} ms ===")
    # TAHAP 1: BUAT RETRIEVER YANG SADAR HISTORY
    # Tujuan: Mengubah pertanyaan user (misal: "kalau untuk SMA?") menjadi pertanyaan mandiri
    # berdasarkan history (misal: "berapa besaran KJP untuk SMA?").
    contextualize_q_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "Diberikan riwayat chat dan pertanyaan terbaru, formulasikan ulang pertanyaan itu menjadi pertanyaan mandiri tanpa mengubah isinya."),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
        ]
    )
    history_aware_retriever = create_history_aware_retriever(
        llm, retriever, contextualize_q_prompt
    )

    # TAHAP 2: BUAT PROMPT UNTUK MENJAWAB PERTANYAAN
    # Prompt ini akan menerima dokumen (context) dari retriever di atas.
    qa_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "Nama aku ASKA. Jawab dengan Bahasa Indonesia santai ala Gen Z, ramah, sopan, dan ringkas. "
                     "Untuk setiap jawaban normal, WAJIB pakai 1-3 emoji yang relevan dan boleh pakai slang ringan seperlunya seperti 'sip', 'sat-set', 'biar nggak zonk', atau 'gas'. "
                     "Jangan terlalu kaku/formal; tetap jelas untuk informasi resmi sekolah. "
                     "Untuk pesan terima kasih/pujian singkat, balas singkat ala Gen Z dengan 1-2 emoji, tanpa perlu mengambil konteks. "
                     "Dalam konteks data ini, SPMB/PMB berarti Penerimaan Murid Baru, bukan mahasiswa baru. "
                     "Jika user menanyakan jadwal SPMB/PMB secara umum tanpa jenjang atau jalur, jelaskan bahwa jadwal berbeda per jenjang/jalur, "
                     "sebutkan ringkasan yang ada di konteks, lalu arahkan user menyebut jenjang/jalur jika ingin detail. "
                     "Untuk jadwal, pertahankan nama jalur/tahap persis dari konteks; jangan mengubah 'afirmasi prioritas kedua' menjadi 'tahap kedua'. "
                     "Jika user minta saran memilih sekolah berdasarkan domisili/kelurahan, sebutkan nama sekolah yang ada di konteks, "
                     "kelompokkan berdasarkan Prioritas Pertama/Kedua/Ketiga jika tersedia, dan minta RT/RW jika diperlukan untuk memastikan pilihan paling tepat. "
                     "Jika user bertanya lanjutan seperti 'SMP apa?' atau 'sekolah apa?', jawab nama sekolahnya dulu; jangan hanya meminta RT/RW. "
                     "Jika RT/RW belum diketahui, jangan merinci RT/RW secara berlebihan; cukup sebutkan kandidat sekolah dan minta RT/RW untuk verifikasi. "
                     "Selalu sebut nama **'ASKA'** secara alami. Jawab hanya berdasarkan konteks. "
                     "Jika konteks kosong atau tidak memuat jawaban yang relevan, jawab persis: "
                     "\"ASKA belum punya data resmi untuk pertanyaan itu.\" "
                     "Jangan mengarang, jangan menebak, dan jangan mengaku sudah mengubah data sistem.\n\n"
                     "Konteks:\n{context}"),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
        ]
    )

    # TAHAP 3: BUAT CHAIN UNTUK MENGGABUNGKAN DOKUMEN KE PROMPT
    question_answer_chain = create_stuff_documents_chain(llm, qa_prompt)

    def _retrieve_ranked_context(inputs: dict) -> list:
        docs = history_aware_retriever.invoke(inputs)
        question = str(inputs.get("input") or "")
        keyword_query = _keyword_query_from_inputs(inputs)
        keyword_docs = _keyword_documents_from_vectorstore(vectorstore, keyword_query)
        combined_docs = _merge_documents(keyword_docs, docs)
        limited_docs = _rank_and_limit_documents(keyword_query, combined_docs)
        _embed_log_also_file(
            f"Context limiter: semantic={len(docs)} keyword={len(keyword_docs)} "
            f"selected={len(limited_docs)} "
            f"chars={sum(len(getattr(doc, 'page_content', '')) for doc in limited_docs)}"
        )
        return limited_docs

    # TAHAP 4: GABUNGKAN SEMUANYA MENJADI SATU RAG CHAIN UTUH.
    # Retriever tetap mengambil kandidat sampai ASKA_RETRIEVAL_MAX_K, lalu konteks
    # direrank dan dibatasi agar model gratisan tidak kelebihan token.
    rag_chain = RunnablePassthrough.assign(
        context=RunnableLambda(_retrieve_ranked_context)
    ).assign(answer=question_answer_chain)

    return rag_chain
