# Triven Cinema v11 - Creator-grade realism and continuity

This release targets photoreal talking-head creator videos where the same presenter must stay recognizable, wardrobe must follow the scene prompt exactly, and long shots must not decay into face, hand, fabric, prop, or set artifacts.

## What changed

### 1. Character identity remains active through both Ingredients stages

LTX-2.5 Ingredients is a two-stage IC-LoRA pipeline. The upstream CLI normally applies the IC-LoRA/reference in stage 1 and lets stage 2 refine with the bare checkpoint. Triven now passes `--stage-2-ic-lora` whenever a reusable Element reference sheet is used, so the same Character reference remains active during the full-resolution reconstruction stage as well.

For long identity-conditioned shots, Triven also enables overlapping 121-frame temporal windows with carry frames. This keeps each window close to the Ingredients training bucket while preserving one continuous output. Large 4K-class identity renders additionally use spatial transformer tiling with the stage-2 lock retained.

### 2. Identity and wardrobe are separate controls

A real Character photo is excellent for face identity but can unintentionally overpower a different outfit requested in the scene. Character bindings therefore expose a wardrobe policy:

- `Follow scene prompt` (default): reference images are treated as identity sources. Clothing in the scene prompt is authoritative.
- `Lock reference outfit`: reference clothing is intentionally preserved unless the scene explicitly changes it.

In `Follow scene prompt` mode Triven removes clothing sentences from the Character description before building the Ingredients prompt and prioritizes upper-face/shoulder crops in the reference sheet. Full-body/costume panels are not injected into the identity sheet by default. This reduces hybrid garments, random straps, copied denim, malformed sweaters, and other reference/prompt clothing mixtures.

New Character uploads are tagged semantically in the recommended order: face, full body, profile, costume, then supporting views. The Studio shows those roles on thumbnails so creators can understand what each upload is doing.

### 3. Exact single-shot prompts retain hard constraints

Prompt-only Factory mode does not send the manuscript through Gemini when AI Director is off. For a single creator shot, Triven now gives extra priority to the user's exact wardrobe, skin, face, hair, camera, microphone/desk, lighting, audio, and quoted dialogue sentences when fitting the prompt into the LTX context budget.

The render-integrity guard is non-creative. It adds only anti-corruption constraints: no duplicate bodies, melted faces, extra teeth/fingers, garment morphing, random zippers/straps/buttons, duplicated props, unstable desk/microphone geometry, frozen opening frames, or progressive identity/wardrobe mutation.

### 4. Earlier and stricter visual QC

Strict final renders now sample five positions across a clip, including the opening seconds. QC separately records identity drift, artifacts, and wardrobe mismatch. A failure causes regeneration; Identity Max allows up to two QC retries from the Studio.

Canonical Character Element images outrank drift in previous generated frames. When scene wardrobe is authoritative, QC compares the generated clothing to the scene description rather than incorrectly requiring clothing from the Character reference photo.

### 5. Creator-grade Studio preset

The Scene inspector has a `Creator-grade talking head` preset. With a Character Element active it selects:

- 1080p final quality
- diffusion final decoder
- preserves the user-selected Factory runtime and scene length
- strict continuity/QC
- Identity Max
- Character identity mode at strength 1.0
- Character active across the Factory sequence
- prompt-authoritative wardrobe
- AI Director off so the user's detailed creator prompt is not creatively rewritten

The preset never overwrites duration. Users can choose short creator clips or longer Factory runtimes, while 1080p supports up to 30 seconds per individual scene. Without a Character Element it applies the same production settings but stays on Real Skin until a reusable Character is added. For a solo presenter, the preset refuses to activate Identity Max when multiple Character Elements are referenced at once; competing identity sheets are a common cause of face blending/drift.

## Recommended Character references

For the strongest identity signal, create a Character Element with clean, naturally lit references in this order:

1. face close-up
2. full-body neutral view
3. profile / three-quarter view
4. optional costume reference

For a scene that requests a different outfit than the source photograph, leave `Wardrobe source` on `Follow scene prompt`. Use `Lock reference outfit` only when the source clothes are intentionally part of the persistent identity.

## Real Skin and Refine Details

Final Real Skin / Identity Max renders can run the separately gated LTX-2.5 Refine Details IC-LoRA after the base render. Triven uses a generic photographic-detail prompt, tiled reconstruction, diffusion VAE, and preserves the original generated audio stream after the picture-only refinement pass.

The Refine Details Hugging Face repository is gated separately. Until access is granted and the checkpoint has been downloaded into the Modal volume, Standard renders remain available. Real Skin / Identity Max intentionally fail rather than silently claiming a refinement pass that did not run.

## Quality expectation

The pipeline is designed to materially improve identity stability and reduce creator-video artifacts, but it does not claim a mathematically guaranteed 99.95/100 face match. Generative video can still vary with occlusion, extreme pose, lighting, motion, reference quality, and model limits. Measure progress with a fixed reference set, fixed prompt, fixed seed, and side-by-side benchmark clips.
