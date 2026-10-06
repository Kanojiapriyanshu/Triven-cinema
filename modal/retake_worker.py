from pathlib import Path


def retake_audio_only(
    *,
    input_path: Path,
    output_path: Path,
    prompt: str,
    start_time: float,
    end_time: float,
    seed: int,
) -> None:
    """Use LTX RetakePipeline to regenerate audio while freezing video.

    This helper is intentionally tied to the pinned LTX v1.3.0 API used by the
    Modal image. Keep the repo pin and this helper in sync when upgrading LTX.
    """
    import torch
    from ltx_core.model.video_vae import AUTO_TILING, get_video_chunks_number
    from ltx_pipelines.retake import RetakePipeline
    from ltx_pipelines.utils.media_io import (
        encode_video,
        get_videostream_metadata,
        resolve_hdr_color_space,
        vae_dtype_for_hdr,
    )
    from ltx_pipelines.utils.model_paths import ModelPaths

    from models import AUDIO_VAE, TEXT_ENCODER, TRANSFORMER, VIDEO_VAE_DIFFUSION

    model_paths = ModelPaths.from_split(
        transformer_path=str(TRANSFORMER),
        text_encoder_path=str(TEXT_ENCODER),
        video_vae_path=str(VIDEO_VAE_DIFFUSION),
        audio_vae_path=str(AUDIO_VAE),
    )
    source = get_videostream_metadata(str(input_path))
    hdr = resolve_hdr_color_space(video_paths=[str(input_path)], hdr=None)
    vae_dtype = vae_dtype_for_hdr(hdr, torch.bfloat16)
    pipeline = RetakePipeline(
        model_paths=model_paths,
        loras=[],
        distilled=True,
    )
    with torch.inference_mode():
        result = pipeline(
            video_path=str(input_path),
            prompt=prompt,
            start_time=max(0.0, float(start_time)),
            end_time=min(float(end_time), max(0.01, (source.frames - 1) / source.fps)),
            seed=int(seed),
            regenerate_video=False,
            regenerate_audio=True,
            vae_dtype=vae_dtype,
            color_space=hdr,
            tiling_config=AUTO_TILING,
            max_batch_size=1,
        )
        encode_video(
            video=result.video,
            fps=int(source.fps),
            audio=result.audio,
            output_path=str(output_path),
            video_chunks_number=get_video_chunks_number(result.num_frames, result.tiling_config),
            color_space=hdr,
        )
