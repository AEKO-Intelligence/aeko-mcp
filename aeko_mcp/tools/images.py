import os
from pathlib import Path

from mcp.server.fastmcp import Image

from ..server import mcp
from ._annotations import LOCAL_READ_ONLY, LOCAL_WRITE

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
ALLOWED_SAVE_EXTENSIONS = {".md", ".html", ".json", ".txt"}


def _get_image_dir() -> Path:
    raw = os.environ.get("AEKO_IMAGE_DIR", "")
    if not raw:
        raise RuntimeError(
            "AEKO_IMAGE_DIR environment variable is not set. "
            "Set it to the directory containing your product images."
        )
    p = Path(raw).resolve()
    if not p.is_dir():
        raise RuntimeError(f"AEKO_IMAGE_DIR path does not exist or is not a directory: {p}")
    return p


def _get_output_dir() -> Path:
    raw = os.environ.get("AEKO_OUTPUT_DIR", "")
    if raw:
        p = Path(raw).resolve()
    else:
        p = Path.cwd() / "aeko_output"
    p.mkdir(parents=True, exist_ok=True)
    return p


@mcp.tool(annotations=LOCAL_READ_ONLY)
def aeko_list_product_images(directory: str | None = None) -> str:
    """List product images in a local directory.

    Scans for jpg, jpeg, png, webp, gif files recursively.
    Defaults to AEKO_IMAGE_DIR env var if directory not provided.

    Args:
        directory: Optional path to scan. Defaults to AEKO_IMAGE_DIR.

    Returns:
        List of image files with sizes.
    """
    if directory:
        base = Path(directory).resolve()
        if not base.is_dir():
            return f"Error: directory not found: {directory}"
    else:
        base = _get_image_dir()

    files = []
    for ext in ALLOWED_EXTENSIONS:
        files.extend(base.rglob(f"*{ext}"))

    if not files:
        return f"No image files found in {base}"

    lines = [f"# Product Images in {base}", f"Found {len(files)} image(s).", ""]

    for f in sorted(files):
        size_kb = f.stat().st_size / 1024
        rel = f.relative_to(base)
        dim_str = ""
        try:
            from PIL import Image as PILImage
            with PILImage.open(f) as img:
                dim_str = f" ({img.width}x{img.height})"
        except Exception:
            pass
        lines.append(f"- `{rel}`{dim_str} — {size_kb:.1f} KB")

    return "\n".join(lines)


@mcp.tool(annotations=LOCAL_READ_ONLY)
def aeko_read_product_image(file_path: str) -> Image:
    """Read a product image from the local filesystem.

    Returns the image so Claude can see it and use it for content creation.
    The path must be within the configured AEKO_IMAGE_DIR (no directory traversal).

    Args:
        file_path: Path to the image file (absolute or relative to AEKO_IMAGE_DIR).
    """
    base = _get_image_dir()
    p = Path(file_path)

    if not p.is_absolute():
        p = base / p

    p = p.resolve()

    # Security: prevent directory traversal outside image dir
    if not str(p).startswith(str(base)):
        raise ValueError(f"Path must be within AEKO_IMAGE_DIR ({base}). Got: {p}")

    if not p.is_file():
        raise FileNotFoundError(f"Image file not found: {p}")

    if p.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported image format: {p.suffix}. Allowed: {ALLOWED_EXTENSIONS}")

    return Image(path=str(p))


@mcp.tool(annotations=LOCAL_WRITE)
def aeko_save_content(file_path: str, content: str) -> str:
    """Save generated content to a local file.

    Supports: .md, .html, .json, .txt extensions.
    Files are saved to AEKO_OUTPUT_DIR (or ./aeko_output/ by default).

    Args:
        file_path: Filename or relative path (e.g. "blog-post.md").
        content: The content to write.

    Returns:
        Confirmation with the saved file path.
    """
    out_dir = _get_output_dir()
    p = Path(file_path)

    # Only use the filename part to prevent traversal
    safe_name = p.name
    if not safe_name:
        raise ValueError("Invalid file path")

    ext = Path(safe_name).suffix.lower()
    if ext not in ALLOWED_SAVE_EXTENSIONS:
        raise ValueError(f"Unsupported file extension: {ext}. Allowed: {ALLOWED_SAVE_EXTENSIONS}")

    # Support subdirectories within the output dir
    if len(p.parts) > 1:
        sub_dir = out_dir / p.parent
        sub_dir.mkdir(parents=True, exist_ok=True)
        target = sub_dir / safe_name
    else:
        target = out_dir / safe_name

    target = target.resolve()
    if not str(target).startswith(str(out_dir)):
        raise ValueError("Path traversal not allowed")

    target.write_text(content, encoding="utf-8")
    return f"Saved to: {target} ({len(content)} chars)"
