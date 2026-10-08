"""Neutralise prompt wording that LTX-2.5 renders as a blown, hazy glow.

Observed on a real render: the scene line "Soft key light from the front left,
shallow depth of field, natural film look" produced a bright veiling bloom over
the upper-left of the frame (the subject's hair and face). LTX has no negative
prompt, so the reliable fix is to not ask for the glow in the first place -
rewrite the handful of cinematography phrases that the model over-renders into
haze/flare/blown highlights, and replace them with controlled-exposure wording.

This is deliberately surgical: it touches only a known high-risk vocabulary and
keeps everything else (including the lighting *direction*, e.g. "from the front
left") intact, so the creator's framing survives. It is non-creative - it never
adds story, dialogue or wardrobe.
"""
import re

# Ordered (longer / more specific first). Each rule maps a bloom/haze/flare
# trigger to a neutral, evenly-exposed equivalent. Case-insensitive, word-bounded.
_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bshallow depth[\s\-]of[\s\-]field\b", re.I), "clear focus on the subject"),
    (re.compile(r"\bshallow dof\b", re.I), "clear focus on the subject"),
    (re.compile(r"\bsoft key light\b", re.I), "even key light"),
    (re.compile(r"\bsoft,?\s+(?:diffused|diffuse)\s+light(?:ing)?\b", re.I), "even, controlled lighting"),
    (re.compile(r"\bsoft light(?:ing)?\b", re.I), "even, controlled lighting"),
    (re.compile(r"\bnatural film look\b", re.I), "clean, natural color"),
    (re.compile(r"\bfilm(?:ic)? look\b", re.I), "clean, natural color"),
    (re.compile(r"\bfilm grain\b", re.I), "clean image"),
    (re.compile(r"\bhalation\b", re.I), "even exposure"),
    (re.compile(r"\blens[\s\-]?flare\b", re.I), "even exposure"),
    (re.compile(r"\bsun[\s\-]?flare\b", re.I), "even exposure"),
    (re.compile(r"\bback[\s\-]?lit\b", re.I), "evenly lit"),
    (re.compile(r"\bback[\s\-]?light(?:ing)?\b", re.I), "even front lighting"),
    (re.compile(r"\brim light(?:ing)?\b", re.I), "even lighting"),
    (re.compile(r"\bgolden hour\b", re.I), "neutral daylight"),
    (re.compile(r"\b(?:god rays|light rays|volumetric light(?:ing)?)\b", re.I), "even ambient light"),
    (re.compile(r"\bhigh[\s\-]key\b", re.I), "balanced"),
    (re.compile(r"\b(?:over[\s\-]?exposed|blown[\s\-]?out)\b", re.I), "evenly exposed"),
    (re.compile(r"\b(?:hazy|haze|misty|foggy glow|veiling glare)\b", re.I), "clear air"),
    (re.compile(r"\b(?:dreamy|ethereal)\b", re.I), "clean"),
    (re.compile(r"\b(?:soft |warm |hazy )?glow(?:ing)?\b", re.I), "even light"),
    (re.compile(r"\bbokeh\b", re.I), "clean background"),
    (re.compile(r"\bsun(?:lit|light)\b", re.I), "soft daylight"),
]

# POSITIVE PHRASING ONLY. LTX-2.5 has no negative prompt; its text encoder renders
# whatever nouns it reads. Naming the artefact ("no bloom / no haze / no lens flare")
# actively summons it, so this note must never contain bloom/haze/glare/flare/glow/
# wash/blown-out and must only describe the clean result we want.
EXPOSURE_INTEGRITY_NOTE = (
    "EXPOSURE INTEGRITY: light the scene evenly and hold one clean, consistent brightness from the first frame to "
    "the last. The face stays sharply and naturally exposed, the skin at a true natural tone, hair edges crisp "
    "against a flat even studio background, with clear air around the subject and full detail retained everywhere."
)

# Also positive-only. The identity reference is shot on its own backdrop; without
# this the reference's backdrop and its edge/rim light override the backdrop the
# creator actually asked for, and a subject lit against a dark backdrop reads as a
# glowing halo. This keeps the prompt's backdrop authoritative.
BACKGROUND_AUTHORITY_NOTE = (
    "BACKGROUND AUTHORITY: the backdrop described in this shot fills the whole frame edge to edge and keeps that "
    "exact color at an even, flat brightness behind the subject for the entire shot. The character reference "
    "supplies only the person's face, hair, body and clothing; the backdrop, setting and its lighting come from "
    "this prompt."
)


def normalize_lighting(prompt: str) -> tuple[str, list[str]]:
    """Return (cleaned prompt, list of 'before -> after' changes made)."""
    if not prompt:
        return prompt, []
    changes: list[str] = []
    cleaned = prompt
    for pattern, replacement in _RULES:
        def _sub(match: re.Match[str]) -> str:
            original = match.group(0)
            if original.lower() != replacement.lower():
                changes.append(f"{original} -> {replacement}")
            return replacement
        cleaned = pattern.sub(_sub, cleaned)
    # Collapse whitespace the substitutions may have doubled up.
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned, changes
