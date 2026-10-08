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

## Creator-grade Character lock (v11)

For Character Elements, Triven now keeps Ingredients IC-LoRA/reference conditioning active in stage 2 (`--stage-2-ic-lora`) instead of letting the full-resolution stage fall back to the bare checkpoint. Long identity-conditioned shots use overlapping 121-frame temporal windows. This is the preferred path for a recurring presenter whose face must remain stable throughout a 15-30 second creator shot.

Character identity and wardrobe are intentionally separated. `wardrobe_policy=prompt` (Studio: **Follow scene prompt**) uses Character references for face/hair/age/proportions while the current scene controls clothing. The reference-sheet composer excludes full-body/costume panels in that mode and uses an upper-face crop even for older single-photo Elements that were tagged ambiguously. `wardrobe_policy=reference` intentionally preserves the reference outfit.

Strict visual QC samples the opening as well as early/mid/late frames and can reject identity drift, malformed anatomy, garment/pattern mutation, random straps/buttons/zippers, duplicated props and unstable set geometry. A prompt that explicitly requests one continuous shot up to the 30-second 1080p experimental profile is kept as one Factory scene instead of being silently split into independently generated clips.

## Cast resolution and "Continue scene" (v12)

**Who is in the shot.** Ingredients conditioning blends every Character panel in the reference sheet. A Character that is only tagged after the last sentence (`... room tone. @ijustine @radha`) and never described in the shot used to be added to the sheet next to the real subject, which pulled faces together. `park_tag_only_characters` now keeps such a Character out of the sheet whenever another Character is mentioned inside the story text, and reports it in `continuity_warnings`. A mention that ends a sentence (`she walks to @Mira`) is story text and is never parked. `cast_role: "cast"` on an `ElementBinding` (Studio: **Keep @name in shot**) overrides the rule. Props, locations and styles are never parked. Only Elements that are actually @mentioned take part in a shot; a hidden "keep active" flag no longer feeds a deleted mention's face into the sheet.

**Exact starting frame opens one scene.** An Element in `start_frame` mode is the first frame of the first scene it appears in. Later Factory scenes continue from the previous clip's last frame; before this change the still was re-applied at every scene boundary and snapped the film back to the opening composition.

**Continue scene.** Every Factory result now keeps its final frame (`continuity_frame_filename` / `continuity_frame_url`). Sending it back as `start_frame_filename` (Studio: **Continue this scene**) makes it frame 0 of the next job. The API requires Strict continuity, checks that the workspace owns the file, adds a continuation-anchor instruction to the prompt, and uses the image instead of an Element start frame for scene 1 (the Element still supplies identity). Direct mode does the same through `reference_frame_filename`.

## Start frame, Draft upscale and what the model copies (v13)

**LTX copies the layout of its conditioning image.** A portrait pasted on a black 16:9 canvas came back as dark hatched pillars with garbled text, a turnaround sheet uploaded as a photo played as the video, two Elements side by side produced a split-screen flash, and the words "reference sheet / Panel" in the prompt made the model draw a fake document. The reference image is therefore always a full-frame crop (collage uploads are cropped to the main portrait by `primary_subject_box`), non-face references sit on a blurred fill instead of black bars, and the prompt describes subjects in plain words.

**Start frame (hero frame).** `POST /api/v1/factory/hero-frame` composes the cast photos and the scene text into one still with a Gemini image model (`GEMINI_API_KEY`; the best image-capable model is picked automatically, `GEMINI_IMAGE_MODEL` overrides, and quota or availability errors fall back to the next model). `POST /api/v1/factory/hero-frame/upload` accepts a picture made elsewhere. The approved frame is sent as `hero_frame_filename`: it becomes the exact first frame of scene 1, no reference sheet is built, and later scenes continue from the previous clip's last frame. Image generation needs a Google project with billing enabled; the free tier has no image quota.

**Draft upscale.** Draft and Full HD are different generation engines, so re-rendering at 1080p can never reproduce a Draft. `POST /api/v1/factory/upscale` instead refines the approved Draft: it is Lanczos-scaled to the final canvas, passed through the Refine Details IC-LoRA (video-to-video) and re-muxed with the Draft's own audio. On a 15 s test the result differed from the Draft by about 4-5 grey levels on average (a different generation differs by about 30), took about 5 minutes and 256 GPU seconds, and kept the same face, expression and voice. It is cleaner, not a different performance. The worker function `upscale_video` must be deployed (`modal deploy modal/app.py`).

**Guards.** A rendered clip that is almost a frozen still is retried with looser references (`motion_qc`). Renders are refused before any GPU spend when ffmpeg/ffprobe are missing. Long single-shot prompts are compacted by priority so dialogue and actions are never cut, sentences are never split inside a quotation, and one paragraph per scene is honoured.
