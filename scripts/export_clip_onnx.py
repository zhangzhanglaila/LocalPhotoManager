"""Export CLIP model to ONNX format for faster CPU inference."""

import torch
from pathlib import Path
from transformers import CLIPModel, CLIPProcessor


def export_clip_to_onnx(model_dir: Path, output_dir: Path):
    """Export CLIP model to ONNX format.

    Args:
        model_dir: Directory containing the PyTorch model.
        output_dir: Directory to save ONNX models.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading CLIP model from {model_dir}...")
    model = CLIPModel.from_pretrained(str(model_dir))
    model.eval()

    # Export image encoder
    print("Exporting image encoder...")
    image_encoder = model.vision_model
    dummy_pixel_values = torch.randn(1, 3, 224, 224)

    torch.onnx.export(
        image_encoder,
        dummy_pixel_values,
        str(output_dir / "image_encoder.onnx"),
        input_names=["pixel_values"],
        output_names=["image_embeds"],
        dynamic_axes={
            "pixel_values": {0: "batch_size"},
            "image_embeds": {0: "batch_size"},
        },
        opset_version=14,
    )
    print(f"  Saved to {output_dir / 'image_encoder.onnx'}")

    # Export text encoder
    print("Exporting text encoder...")
    text_encoder = model.text_model
    dummy_input_ids = torch.randint(0, 100, (1, 77))
    dummy_attention_mask = torch.ones(1, 77, dtype=torch.long)

    torch.onnx.export(
        text_encoder,
        (dummy_input_ids, dummy_attention_mask),
        str(output_dir / "text_encoder.onnx"),
        input_names=["input_ids", "attention_mask"],
        output_names=["text_embeds"],
        dynamic_axes={
            "input_ids": {0: "batch_size"},
            "attention_mask": {0: "batch_size"},
            "text_embeds": {0: "batch_size"},
        },
        opset_version=14,
    )
    print(f"  Saved to {output_dir / 'text_encoder.onnx'}")

    # Copy config and tokenizer files
    import shutil
    for file_name in [
        "config.json", "preprocessor_config.json",
        "tokenizer.json", "tokenizer_config.json",
        "vocab.json", "merges.txt", "special_tokens_map.json",
    ]:
        src = model_dir / file_name
        if src.exists():
            shutil.copy2(src, output_dir / file_name)
            print(f"  Copied {file_name}")

    print(f"\nExport complete! ONNX models saved to {output_dir}")
    print("You can now use CLIPFastEmbeddingService for faster CPU inference.")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python export_clip_onnx.py <model_dir> [output_dir]")
        print("  model_dir: Directory containing the PyTorch CLIP model")
        print("  output_dir: Directory to save ONNX models (default: model_dir)")
        sys.exit(1)

    model_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else model_dir

    export_clip_to_onnx(model_dir, output_dir)
