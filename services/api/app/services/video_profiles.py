def source_render_dimensions(aspect_ratio: str) -> tuple[int, int]:
    """Fast/source LTX dimensions, all divisible by 64."""
    if aspect_ratio == "16:9":
        return 1024, 576
    if aspect_ratio == "9:16":
        return 576, 1024
    return 512, 512
