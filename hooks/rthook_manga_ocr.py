# Runtime hook: pre-import transformers submodules that manga_ocr needs.
# In a frozen PyInstaller exe, transformers' lazy __getattr__ import system
# fails because importlib.import_module() can't resolve relative paths the
# same way it does in a normal Python environment.
# Pre-importing these modules at startup bypasses the lazy loader entirely.

import sys

def _preload_transformers_for_manga_ocr():
    try:
        # Core encoder-decoder infrastructure
        import transformers.models.encoder_decoder.modeling_encoder_decoder
        import transformers.models.encoder_decoder.configuration_encoder_decoder

        # ViT image processor (what manga_ocr uses)
        # torchvision may not be installed; pre-import both the default and the
        # PIL fallback so the lazy loader doesn't fail on either path.
        import transformers.models.vit.image_processing_vit
        try:
            import transformers.models.vit.image_processing_vit_fast
        except Exception:
            pass
        import transformers.models.vit.modeling_vit
        import transformers.models.vit.configuration_vit

        # Auto tokenizer chain (triggered by AutoTokenizer.from_pretrained)
        import transformers.models.auto.tokenization_auto
        import transformers.models.auto.configuration_auto
        import transformers.models.auto.modeling_auto

        # VisionEncoderDecoder model (the actual manga-ocr model class)
        import transformers.models.vision_encoder_decoder.modeling_vision_encoder_decoder
        import transformers.models.vision_encoder_decoder.configuration_vision_encoder_decoder

        # Generation utilities
        import transformers.generation.utils
        import transformers.generation.configuration_utils

        # BERT tokenizer (used as the decoder tokenizer in manga-ocr)
        import transformers.models.bert.tokenization_bert
        import transformers.models.bert.tokenization_bert_fast

    except Exception:
        # Do not crash startup if pre-loading fails — let the error surface
        # naturally when the user actually tries to use manga OCR.
        pass

_preload_transformers_for_manga_ocr()
