"""Independent GPT-2-era comparator. Only the offline research CLI imports this module."""

from .registry import sha256

REPO = "openai-community/roberta-large-openai-detector"
REVISION = "38f3e0ccf205e9c4e0b38ae9d75ec948141bf832"
FILES = {
    "config.json": "5d93caa966b81d8f39177184f528035e1d1404daec601086a31fd66646b68367",
    "merges.txt": "1ce1664773c50f3e0cc8842619a93edc4624525b728b188a9e0be33b7726adc5",
    "model.safetensors": "c3dde6261c9491bf5bc34a1a3cba92aa3e9b369b40ce17ccfcf66de508fe0c53",
    "tokenizer.json": "847bbeab6174d66a88898f729d52fa8d355fafe1bea101cf960dd404581df70e",
    "tokenizer_config.json": "994f46754c5bf4014f1aa92d34b1374319c3a6b3f702105cd5b742beaecd18ce",
    "vocab.json": "9e7f63c2d15d666b52e21d250d2e513b87c9b713cfa6987a82ed89e5e6e50655",
}


class RobertaBaseline:
    def __init__(self, directory):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        for name, digest in FILES.items():
            if sha256(directory / name) != digest:
                raise ValueError(f"Incorrect baseline revision for {name}")
        self.device = (
            "cuda"
            if torch.cuda.is_available()
            else "mps"
            if torch.backends.mps.is_available()
            else "cpu"
        )
        self.backend = "torch-" + self.device
        self.digest = FILES["model.safetensors"]
        self.tokenizer = AutoTokenizer.from_pretrained(directory, local_files_only=True)
        self.model = (
            AutoModelForSequenceClassification.from_pretrained(
                directory, local_files_only=True, use_safetensors=True
            )
            .eval()
            .to(self.device)
        )

    def score(self, text):
        import torch

        inputs = self.tokenizer(text, max_length=512, truncation=True, return_tensors="pt")
        with torch.inference_mode():
            logits = self.model(**inputs.to(self.device)).logits
            # The publisher's detector/server.py orders the classes as fake, real.
            return logits.softmax(dim=-1)[0, 0].item()
