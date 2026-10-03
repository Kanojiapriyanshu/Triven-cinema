import os
import shutil
from pathlib import Path

from dotenv import load_dotenv
from gradio_client import Client


load_dotenv()

token = os.getenv("HF_TOKEN")
space = os.getenv(
    "HF_LTX_SPACE",
    "ChopperBlu/ltx-2-5-demo",
)

if not token:
    raise RuntimeError("HF_TOKEN missing from .env")


prompt = """
Cinematic close-up of a futuristic silver sports car slowly
driving through a rain-soaked city street at night.
Wet pavement reflects neon lights. Smooth tracking camera.
Natural realistic movement, cinematic lighting, shallow depth of field.
""".strip()


print(f"Connecting to {space}...")

client = Client(
    space,
    token=token,
)

print("Preparing prompt...")

prepared_prompt = client.predict(
    prompt,
    None,
    False,
    api_name="/prepare_prompt",
)

print()
print("Prompt prepared.")
print("Starting ZeroGPU generation...")
print("This may wait in the shared GPU queue.")
print()


result = client.predict(
    prepared_prompt,  # prompt
    None,             # no input image
    512,              # width
    512,              # height
    1.0,              # duration seconds
    False,            # automatic duration
    42,               # seed
    False,            # randomize seed
    "conv",            # fastest decoder
    api_name="/generate_video",
)

print("Generation result:")
print(result)

video_path = result[0]

output_dir = Path("storage/generated")
output_dir.mkdir(parents=True, exist_ok=True)

destination = output_dir / "first-ltx-test.mp4"

shutil.copy2(
    video_path,
    destination,
)

print()
print("--------------------------------")
print("TRIVEN CINEMA FIRST LTX VIDEO")
print("--------------------------------")
print(f"Saved to: {destination.resolve()}")
print(f"Seed: {result[1]}")
print(f"Details: {result[2]}")
