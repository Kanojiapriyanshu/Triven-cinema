"""LTX provider entrypoint.

The production implementation is selected through inference.providers.router.
This module remains as a stable import location for future direct/local LTX use.
"""

from inference.providers.huggingface_ltx import HuggingFaceLTXProvider
from inference.providers.modal_ltx import ModalLTXProvider

__all__ = ["HuggingFaceLTXProvider", "ModalLTXProvider"]
