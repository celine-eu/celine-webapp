"""CLI utilities for celine-webapp."""

import asyncio
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import typer
from sqlalchemy import select

from celine.webapp.db import FeedbackEntry, get_db_context

app = typer.Typer(help="CELINE webapp operational utilities.")


def _normalize_extension(mime_type: str | None) -> str:
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
    }.get(mime_type or "", ".bin")


async def _export_feedback(output: Path) -> int:
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    async with get_db_context() as db:
        result = await db.execute(
            select(FeedbackEntry).order_by(FeedbackEntry.created_at.asc())
        )
        rows = list(result.scalars())

    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        manifest: list[dict[str, object]] = []

        for row in rows:
            folder = f"{row.created_at.strftime('%Y%m%dT%H%M%SZ')}_{row.id}"
            archive.writestr(
                f"{folder}/comment.txt",
                (row.comment or "").strip() + "\n",
            )

            metadata = {
                "id": str(row.id),
                "user_id": row.user_id,
                "rating": row.rating,
                "comment": row.comment,
                "page_url": row.page_url,
                "page_title": row.page_title,
                "page_path": row.page_path,
                "locale": row.locale,
                "timezone": row.timezone,
                "user_agent": row.user_agent,
                "viewport_width": row.viewport_width,
                "viewport_height": row.viewport_height,
                "screen_width": row.screen_width,
                "screen_height": row.screen_height,
                "color_scheme": row.color_scheme,
                "client_timestamp": row.client_timestamp.isoformat() if row.client_timestamp else None,
                "client_ip": row.client_ip,
                "created_at": row.created_at.isoformat(),
                "extra_context": row.extra_context or {},
                "has_screenshot": bool(row.screenshot_bytes),
                "screenshot_mime_type": row.screenshot_mime_type,
            }
            archive.writestr(
                f"{folder}/metadata.json",
                json.dumps(metadata, indent=2, ensure_ascii=True),
            )

            screenshot_name = None
            if row.screenshot_bytes:
                screenshot_name = f"screenshot{_normalize_extension(row.screenshot_mime_type)}"
                archive.writestr(f"{folder}/{screenshot_name}", row.screenshot_bytes)

            manifest.append(
                {
                    "id": str(row.id),
                    "folder": folder,
                    "rating": row.rating,
                    "created_at": row.created_at.isoformat(),
                    "page_url": row.page_url,
                    "screenshot": screenshot_name,
                }
            )

        archive.writestr(
            "manifest.json",
            json.dumps({"count": len(manifest), "items": manifest}, indent=2, ensure_ascii=True),
        )

    typer.echo(f"Exported {len(rows)} feedback item(s) to {output}")
    return len(rows)


@app.command("export-feedback")
def export_feedback(
    output: Path = typer.Argument(..., help="Target .zip file path."),
) -> None:
    """Export all stored feedback into a zip archive."""

    asyncio.run(_export_feedback(output))


if __name__ == "__main__":
    app()


def main() -> None:
    """Entry point for direct feedback export usage."""

    typer.run(export_feedback)
