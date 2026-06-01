#!/usr/bin/env python3
"""Download CLIP model for semantic search."""

import os
import sys
import zipfile
import urllib.request
from pathlib import Path

# GitHub release URL
MODEL_URL = "https://github.com/zhangzhanglaila/LocalPhotoManager/releases/download/v1.0.0/clip-vit-base-patch32.zip"
MODEL_DIR = Path(__file__).resolve().parent.parent / "extension" / "models"
MODEL_NAME = "clip-vit-base-patch32"


def download_file(url: str, dest: Path) -> bool:
    """Download file with progress."""
    print(f"Downloading {url}")
    print(f"To {dest}")

    try:
        def reporthook(block_num, block_size, total_size):
            downloaded = block_num * block_size
            if total_size > 0:
                percent = min(100, downloaded * 100 / total_size)
                mb_downloaded = downloaded / (1024 * 1024)
                mb_total = total_size / (1024 * 1024)
                print(f"\r{percent:.1f}% ({mb_downloaded:.1f}/{mb_total:.1f} MB)", end="", flush=True)

        urllib.request.urlretrieve(url, str(dest), reporthook)
        print()  # New line after progress
        return True
    except Exception as e:
        print(f"\nDownload failed: {e}")
        return False


def extract_zip(zip_path: Path, dest_dir: Path) -> bool:
    """Extract zip file."""
    print(f"Extracting to {dest_dir}")
    try:
        with zipfile.ZipFile(str(zip_path), 'r') as zip_ref:
            zip_ref.extractall(str(dest_dir))
        print("Extraction complete")
        return True
    except Exception as e:
        print(f"Extraction failed: {e}")
        return False


def main():
    """Main function."""
    print("=" * 50)
    print("CLIP Model Download Script")
    print("=" * 50)
    print()

    # Check if model already exists
    model_path = MODEL_DIR / MODEL_NAME
    if model_path.exists() and (model_path / "pytorch_model.bin").exists():
        print(f"Model already exists at: {model_path}")
        print("Skipping download.")
        return 0

    # Create directory
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # Download
    zip_path = MODEL_DIR / "clip-vit-base-patch32.zip"
    if not zip_path.exists():
        if not download_file(MODEL_URL, zip_path):
            print("\nDownload failed!")
            print(f"Please download manually from: {MODEL_URL}")
            return 1
    else:
        print(f"Zip file already exists: {zip_path}")

    # Extract
    if not extract_zip(zip_path, MODEL_DIR):
        print("Extraction failed!")
        return 1

    # Cleanup zip
    try:
        zip_path.unlink()
        print("Cleaned up zip file")
    except Exception:
        pass

    # Verify
    if (model_path / "pytorch_model.bin").exists():
        print()
        print("=" * 50)
        print("SUCCESS! Model installed at:")
        print(f"  {model_path}")
        print()
        print("You can now use semantic search in the app.")
        print("=" * 50)
        return 0
    else:
        print("\nVerification failed: pytorch_model.bin not found")
        return 1


if __name__ == "__main__":
    sys.exit(main())
