# Triven Cinema Continuity & Cardinality Engine

This layer is designed for a common generative-video failure: a recurring subject is visually consistent enough, but the model creates **two physical copies** of a character that should appear once.

## Production continuity stack

For strict continuity Triven combines multiple independent safeguards instead of relying on one prompt sentence:

1. **Character Bible** — immutable recurring identity traits.
2. **Style Bible** — immutable visual/rendering language.
3. **Entity Locks** — canonical physical subject counts such as `LEO=1`, `FOX=1`.
4. **Per-shot Visible Counts** — expected counts for subjects actually visible in a scene.
5. **Continuation Prompt Semantics** — subjects already visible in a supplied first frame are treated as existing canonical instances, not entities to instantiate again.
6. **Lossless First-frame Conditioning** — strict mode passes the selected continuity frame to LTX at frame 0 with full conditioning strength by default and CRF 0.
7. **Stable Anchor Selection** — Triven samples several near-end frames instead of blindly using the literal final frame, which can be blurred or occluded.
8. **Long-shot Temporal Carry** — clips longer than 10 seconds use LTX temporal windows with carry frames so identity and motion context survive across the shot.
9. **Vision Cardinality QC** — representative frames are inspected for obvious clone/twin/extra-body errors.
10. **Bounded Auto-regeneration** — failed continuity QC can trigger a stronger recovery prompt and one bounded re-render by default.

## New shot vs continuation shot

A new shot may establish a subject from text. A continuation shot is different: when a first-frame reference is present, the subject in that image already exists. The generation prompt therefore says to continue that physical instance rather than re-introduce or recreate it.

This distinction addresses a failure mode where the reference image already contains the hero and the text prompt names the hero again, causing the model to interpret the text as a request for another copy.

## QC behavior

`continuity_qc_mode` supports:

- `off` — prompt/conditioning guards only.
- `auto` — run QC when available; retry a failed scene; if the external QC service is unavailable, continue with prompt/conditioning guards and return a warning.
- `strict` — a duplicate/cardinality failure or unavailable QC rejects the scene/job instead of silently shipping it.

The default maximum QC retry count is `1` to prevent uncontrolled GPU spend. This is configurable per request within the schema limit.

## Long-video behavior

Normal shots up to 10 seconds remain a single LTX window. Longer shots use LTX Distilled temporal chunk controls with a 97-frame pixel window and 25-frame carry. These are internal windows inside one LTX invocation, not separate story characters/scenes.

## FFmpeg compatibility

Continuity frame extraction does not use the removed/deprecated `-vsync` option. The same code path works with current FFmpeg versions, including FFmpeg 9.

## Known limitation

No generative model can guarantee zero duplication in every possible composition. Triven therefore treats continuity as a controlled generation + validation problem. For high-value final renders, use strict continuity + strict QC and reject/regenerate any scene that violates canonical subject count.

## Element identity layer

Previous-frame continuity and Element identity now solve different problems:

```text
canonical @Element reference -> WHO / WHAT must remain the same
previous approved frame      -> WHERE / POSE / MOTION state continues from
scene prompt                  -> WHAT happens next
```

A scene that uses `@Radha` stores the concrete Element version bound to the render. Editing `@Radha` later creates another immutable version and cannot silently mutate an existing job.

For multi-reference scenes, Triven composes a clean black-background reference sheet and invokes LTX-2.5 Ingredients IC-LoRA. The static guide now matches the generated clip length/frame rate and target canvas, with a minimum of 121 frames, instead of the earlier fixed five-second guide. An Element can contribute its canonical image plus up to two supporting views inside its panel. For exact-image animation, Triven uses first-frame image conditioning and explicitly directs motion to begin immediately after frame zero instead of holding the input for several seconds. Visual continuity QC receives the canonical Element references as well as generated frames so it can detect cumulative identity drift instead of only comparing scene N with scene N-1.

The current production defaults intentionally expose a model-safe active-Element cap. Raise `ELEMENT_MAX_ACTIVE_PER_SCENE` only after benchmarking the deployed B200/Ingredients profile; a UI that can browse many library assets does not imply every asset should be injected into one LTX conditioning sheet.
