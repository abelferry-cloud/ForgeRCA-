"""Download the five pinned parser model files, keeping all weights local."""

from app.ingestion import pdf


def main():
    from huggingface_hub import hf_hub_download

    for spec, filename, expected, path in pdf.model_files():
        if path.is_file() and pdf.file_sha256(path) == expected:
            print(f"Verified {spec['repo_id']}/{filename}")
            continue
        # Force replacement when an existing file failed the content check.
        hf_hub_download(
            repo_id=spec["repo_id"], revision=spec["revision"], filename=filename,
            local_dir=pdf.MODELS_DIR / spec["repo_id"].replace("/", "--"), force_download=True,
        )
        if pdf.file_sha256(path) != expected:
            raise ValueError(f"Parser model SHA-256 mismatch: {path}")
        print(f"Downloaded and verified {spec['repo_id']}/{filename}")
    pdf.verify_models()


if __name__ == "__main__":
    main()
