import os

from dotenv import load_dotenv
from gradio_client import Client


load_dotenv()

token = os.getenv("HF_TOKEN")
space = os.getenv(
    "HF_LTX_SPACE",
    "Lightricks/LTX-2.5",
)

if not token:
    raise RuntimeError(
        "HF_TOKEN is missing from the root .env file."
    )

print()
print("Triven Cinema - Hugging Face LTX Test")
print("-------------------------------------")
print(f"Space: {space}")
print("Connecting...")

client = Client(
    space,
    token=token,
)

print()
print("Connected successfully.")
print()
print("Available API endpoints:")
print("------------------------")

client.view_api(all_endpoints=True)
