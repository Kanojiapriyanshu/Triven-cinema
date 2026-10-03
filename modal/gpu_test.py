import modal

app = modal.App("triven-cinema-gpu-test")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .uv_pip_install("torch")
)

@app.function(
    image=image,
    gpu="H100",
    timeout=600,
)
def check_gpu():
    import torch

    result = {
        "torch_version": torch.__version__,
        "cuda_available": torch.cuda.is_available(),
        "cuda_version": torch.version.cuda,
    }

    if torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)

        result["gpu"] = torch.cuda.get_device_name(0)
        result["vram_gb"] = round(
            props.total_memory / 1024**3,
            2,
        )

    return result


@app.local_entrypoint()
def main():
    result = check_gpu.remote()

    print()
    print("Triven Cinema GPU Test")
    print("----------------------")

    for key, value in result.items():
        print(f"{key}: {value}")
