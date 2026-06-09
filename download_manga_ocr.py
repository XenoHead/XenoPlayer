import os
try:
    from manga_ocr import MangaOcr
except ImportError:
    print("manga_ocr not installed")
    exit(1)

model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "manga_ocr_model")
print(f"Loading MangaOcr and saving model to {model_path}...")
mocr = MangaOcr()
os.makedirs(model_path, exist_ok=True)
mocr.processor.save_pretrained(model_path)
mocr.tokenizer.save_pretrained(model_path)
mocr.model.save_pretrained(model_path)
print("Saved successfully!")
