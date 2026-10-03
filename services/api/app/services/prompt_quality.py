import re


_STOP_WORDS = {
    "about", "above", "after", "again", "against", "along", "also",
    "another", "because", "before", "being", "below", "between", "both",
    "camera", "cinematic", "could", "detail", "during", "every", "from",
    "have", "into", "lighting", "make", "more", "most", "movement",
    "other", "over", "scene", "should", "smooth", "style",
    "than", "that", "their", "there", "these", "they", "this", "through",
    "very", "video", "while", "with", "would", "your",
}


def _terms(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]{2,}", text.lower())
    return {
        word
        for word in words
        if len(word) >= 4 and word not in _STOP_WORDS and not word.isdigit()
    }


def evaluate_plan_prompt_coverage(
    original_prompt: str,
    scene_prompts: list[str],
) -> dict:
    """Text-only planning diagnostic, not a visual adherence score."""
    source_terms = _terms(original_prompt)
    planned_terms = _terms(" ".join(scene_prompts))

    if not source_terms:
        return {
            "coverage_score": 1.0,
            "covered_terms": [],
            "missing_terms": [],
            "note": (
                "Text-only storyboard coverage diagnostic. This does not evaluate "
                "the generated video's visual prompt adherence."
            ),
        }

    covered = sorted(source_terms & planned_terms)
    missing = sorted(source_terms - planned_terms)
    score = round(len(covered) / len(source_terms), 3)

    return {
        "coverage_score": score,
        "covered_terms": covered,
        "missing_terms": missing,
        "note": (
            "Text-only storyboard coverage diagnostic. This does not evaluate "
            "the generated video's visual prompt adherence."
        ),
    }
