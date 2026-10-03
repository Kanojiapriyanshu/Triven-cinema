import re


CONTINUITY_HEADER = "TRIVEN CONTINUITY LOCK"


def compact_text(value: str | None, limit: int = 2800) -> str:
    if not value:
        return ""
    compacted = re.sub(r"\s+", " ", value).strip()
    return compacted[:limit]


def compose_continuity_prompt(
    *,
    scene_prompt: str,
    character_bible: str | None,
    style_bible: str | None,
    scene_index: int | None,
    scene_count: int | None,
) -> str:
    """Attach immutable identity/style locks to a scene prompt.

    The same lock text is prepended to every scene. This deliberately duplicates
    planner guidance at render time so user edits cannot accidentally remove the
    identity constraints that keep a multi-shot story coherent.
    """
    character = compact_text(character_bible)
    style = compact_text(style_bible)
    prompt = scene_prompt.strip()

    if f"[{CONTINUITY_HEADER}]" in prompt:
        return prompt

    if not character and not style:
        return prompt

    if scene_index is not None and scene_count:
        scene_label = f"SCENE {scene_index + 1} OF {scene_count}"
    else:
        scene_label = "STORY SCENE"

    blocks = [
        f"[{CONTINUITY_HEADER}]",
        "The following identity and visual-style rules are immutable for the entire story.",
    ]
    if character:
        blocks.append(f"CHARACTER BIBLE (DO NOT REINTERPRET): {character}")
    if style:
        blocks.append(f"VISUAL STYLE BIBLE (KEEP IDENTICAL): {style}")

    blocks.extend(
        [
            (
                "CONTINUITY RULES: Preserve the exact same face identity, facial structure, apparent age, "
                "hairstyle, hair color, eye color, skin/fur markings, body proportions, wardrobe colors, "
                "wardrobe design, accessories and companion design across every scene. Do not redesign, "
                "recast, age, recolor or restyle any recurring character. Only action, pose, expression, "
                "camera framing, camera movement, and story progression may change unless the story explicitly "
                "requires an environmental or lighting change."
            ),
            f"[{scene_label}]",
            prompt,
        ]
    )
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
