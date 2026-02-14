"""Path helpers."""

from pathlib import Path


def resolve_output_path(feeds_dir: str | Path, output: str) -> Path:
    """Resolve output path under feeds directory and prevent path traversal."""
    if not output or not output.strip():
        raise ValueError("output 不能为空")

    feeds_root = Path(feeds_dir).resolve()
    output_path = (feeds_root / output).resolve()

    if output_path != feeds_root and feeds_root not in output_path.parents:
        raise ValueError(f"非法输出路径: {output}")
    if not output_path.name:
        raise ValueError(f"非法输出文件名: {output}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path
