import re
from collections.abc import Iterable

from app.schemas.generation import EntityLock


CONTINUITY_HEADER = "TRIVEN CONTINUITY LOCK"

# These are deliberately phrased as generation constraints, not as a separate
# "negative prompt" because the current LTX distilled CLI accepts one text prompt.
ANTI_DUPLICATION_CONSTRAINTS = (
    "Never create duplicate copies of a recurring subject. No clone, twin, mirrored duplicate, "
    "second copy, extra person, extra animal, extra face, extra head, extra torso, fused duplicate, "
    "ghost duplicate, reflection that looks like a second physical subject, or accidental crowding. "
    "A mirror/window reflection is allowed only when the story explicitly asks for one and it must "
    "read clearly as a reflection, never as another physical character."
)

COMMON_ENTITY_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("PERSON", ("person", "human", "man", "woman", "boy", "girl", "adventurer", "traveler", "traveller", "character")),
    ("FOX", ("fox",)),
    ("DOG", ("dog", "puppy")),
    ("CAT", ("cat", "kitten")),
    ("HORSE", ("horse",)),
    ("ROBOT", ("robot", "android")),
    ("CAR", ("car", "vehicle", "sports car")),
)


def compact_text(value: str | None, limit: int = 2800) -> str:
    if not value:
        return ""
    compacted = re.sub(r"\s+", " ", value).strip()
    return compacted[:limit]


def _safe_label(value: str) -> str:
    label = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip().upper()).strip("_")
    return label[:64] or "ENTITY"


def normalize_entity_locks(entity_locks: Iterable[EntityLock | dict] | None) -> list[EntityLock]:
    result: list[EntityLock] = []
    seen: set[str] = set()
    for raw in entity_locks or []:
        try:
            lock = raw if isinstance(raw, EntityLock) else EntityLock.model_validate(raw)
        except Exception:
            continue
        label = _safe_label(lock.label)
        if label in seen:
            continue
        seen.add(label)
        result.append(
            EntityLock(
                label=label,
                expected_count=max(1, min(8, int(lock.expected_count))),
                description=compact_text(lock.description, 1200),
            )
        )
    return result[:12]


def infer_local_entity_locks(prompt: str) -> list[EntityLock]:
    """Conservative fallback entity locks when the remote planner is unavailable.

    This deliberately recognizes only common concrete subjects. The universal
    anti-duplication rule still applies to unrecognized subjects, so a weak
    heuristic can never force an invented extra character into the story.
    """
    text = compact_text(prompt, 4000).lower()
    locks: list[EntityLock] = []
    used_terms: set[str] = set()

    number_words = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
    }

    for label, terms in COMMON_ENTITY_PATTERNS:
        matched_term = next((term for term in sorted(terms, key=len, reverse=True) if re.search(rf"\b{re.escape(term)}s?\b", text)), None)
        if not matched_term or matched_term in used_terms:
            continue
        used_terms.add(matched_term)
        count = 1
        count_match = re.search(
            rf"\b(one|two|three|four|five|[1-5])\s+(?:\w+\s+){{0,2}}{re.escape(matched_term)}s?\b",
            text,
        )
        if count_match:
            token = count_match.group(1)
            count = number_words.get(token, int(token) if token.isdigit() else 1)
        locks.append(
            EntityLock(
                label=label,
                expected_count=count,
                description=f"Recurring {matched_term} from the original user request; preserve its established identity exactly.",
            )
        )

    return locks[:8]


def _cardinality_block(
    entity_locks: Iterable[EntityLock | dict] | None,
    visible_entity_counts: dict[str, int] | None,
) -> str:
    locks = normalize_entity_locks(entity_locks)
    if not locks and not visible_entity_counts:
        return (
            "ENTITY COUNT LOCK: Keep one physical instance of each recurring subject unless the original "
            "story explicitly requests multiple instances. Never spawn another copy merely because the subject "
            "is described again in this prompt."
        )

    by_label = {lock.label: lock for lock in locks}
    lines = ["ENTITY COUNT LOCK (HARD CONSTRAINT):"]
    for lock in locks:
        detail = f" — {lock.description}" if lock.description else ""
        lines.append(
            f"- {lock.label}: canonical maximum {lock.expected_count} physical instance(s){detail}"
        )

    exact_counts: list[str] = []
    for raw_label, raw_count in (visible_entity_counts or {}).items():
        label = _safe_label(raw_label)
        try:
            count = max(0, min(8, int(raw_count)))
        except (TypeError, ValueError):
            continue
        # Ignore planner hallucinations that exceed the canonical maximum.
        if label in by_label:
            count = min(count, by_label[label].expected_count)
        exact_counts.append(f"{label}={count}")
    if exact_counts:
        lines.append("- THIS SHOT MUST SHOW EXACTLY: " + ", ".join(exact_counts) + ".")
    lines.append(
        "- Text descriptions of an already-present subject are identity checks, not instructions to instantiate another copy."
    )
    return "\n".join(lines)


def compose_continuity_prompt(
    *,
    scene_prompt: str,
    character_bible: str | None,
    style_bible: str | None,
    scene_index: int | None,
    scene_count: int | None,
    entity_locks: Iterable[EntityLock | dict] | None = None,
    visible_entity_counts: dict[str, int] | None = None,
    reference_frame_present: bool = False,
    retry_level: int = 0,
    qc_feedback: str | None = None,
) -> str:
    """Attach identity, entity-cardinality and continuation locks to a scene prompt.

    The critical distinction is NEW SHOT vs CONTINUATION SHOT. When a first-frame
    reference exists, subjects in that frame are canonical existing instances. The
    text must continue them rather than asking LTX to instantiate them again.
    """
    character = compact_text(character_bible)
    style = compact_text(style_bible)
    prompt = scene_prompt.strip()

    # Scene planner already locks its prompts. A later render pass still needs to
    # add continuation/reference semantics if a new anchor frame is supplied.
    already_locked = f"[{CONTINUITY_HEADER}]" in prompt
    if already_locked and not reference_frame_present and retry_level <= 0:
        return prompt

    if scene_index is not None and scene_count:
        scene_label = f"SCENE {scene_index + 1} OF {scene_count}"
    else:
        scene_label = "STORY SCENE"

    blocks: list[str] = []
    if not already_locked:
        blocks.extend(
            [
                f"[{CONTINUITY_HEADER}]",
                "The following identity, cardinality and visual-style rules are immutable for the entire story.",
            ]
        )
        if character:
            blocks.append(f"CHARACTER BIBLE (DO NOT REINTERPRET): {character}")
        if style:
            blocks.append(f"VISUAL STYLE BIBLE (KEEP IDENTICAL): {style}")
        blocks.append(_cardinality_block(entity_locks, visible_entity_counts))
        blocks.append(
            "CONTINUITY RULES: Preserve the exact same face identity, facial structure, apparent age, hairstyle, "
            "hair color, eye color, skin/fur markings, body proportions, wardrobe colors, wardrobe design, "
            "accessories and companion design across every scene. Do not redesign, recast, age, recolor or restyle "
            "any recurring subject. Only action, pose, expression, camera framing, camera movement and story "
            "progression may change unless the story explicitly requires an environmental or lighting change."
        )
        blocks.append(f"ANTI-DUPLICATION RULES: {ANTI_DUPLICATION_CONSTRAINTS}")
    else:
        # Preserve the original locked prompt verbatim and append only the additional
        # runtime guard. This avoids multiplying the character bible on retries.
        blocks.append(prompt)
        prompt = ""

    if reference_frame_present:
        blocks.append(
            "[CONTINUATION SHOT — EXISTING SUBJECTS] The supplied first frame is authoritative. Every recurring "
            "subject already visible in that frame is the one and only canonical physical instance of that subject. "
            "Continue the same body, face, wardrobe, fur/markings, pose trajectory, screen position and motion from "
            "that frame. DO NOT introduce, recreate, re-enter, spawn, mirror or clone a subject that is already "
            "present. If the scene text names that subject again, interpret the words only as instructions for what "
            "the existing subject does next."
        )

    if retry_level > 0:
        feedback = compact_text(qc_feedback, 700)
        blocks.append(
            "[CONTINUITY RECOVERY — MAXIMUM CARDINALITY STRICTNESS] A previous render was rejected for continuity. "
            "Prioritize correct subject count over decorative background detail. Keep the canonical subject(s) "
            "clearly separated, anatomically complete and unambiguous. Never place a second look-alike in the frame."
            + (f" QC feedback: {feedback}" if feedback else "")
        )

    if prompt:
        blocks.extend([f"[{scene_label}]", prompt])
    return "\n\n".join(blocks)


def safe_continuity_id(value: str | None) -> str:
    raw = compact_text(value, 96) if value else ""
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", raw).strip("-")
    return cleaned[:80] or "story"


def local_character_bible(prompt: str) -> str:
    """Deterministic fallback identity lock when Gemini planning is unavailable."""
    base = compact_text(prompt, 1800)
    return (
        "Use the recurring main character(s) and companion(s) exactly as first established in the story. "
        "Freeze face identity, facial geometry, apparent age, hairstyle, hair color, eye color, body build, "
        "body proportions, clothing design and colors, footwear, accessories, and all animal fur markings, "
        "size and proportions. The original story description is authoritative: "
        f"{base}"
    )[:2800]


def local_style_bible(prompt: str) -> str:
    base = compact_text(prompt, 1600).lower()
    if any(term in base for term in ("disney", "animated", "animation", "cartoon", "stylized")):
        style = (
            "Polished cinematic feature-animation treatment with expressive but stable character design, "
            "consistent materials, proportions and palette, smooth cinematic camera movement, coherent "
            "environment design, warm story-driven lighting and consistent rendering style from shot to shot."
        )
    elif any(term in base for term in ("photoreal", "realistic", "real human", "human like", "human-like")):
        style = (
            "Photorealistic cinematic treatment with stable human identity, natural skin texture, consistent "
            "hair, realistic fabric/material detail, physically plausible lighting, coherent lens language, "
            "natural depth of field and consistent color science across every shot."
        )
    else:
        style = (
            "Keep the exact same visual language, character rendering, materials, color palette, lighting logic, "
            "lens language and environment design across all scenes."
        )
    return style
