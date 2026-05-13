from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {"xlsx", "xls", "pdf", "png", "jpg", "jpeg", "docx"}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def upload_to_box(file: FileStorage, upload_root: str, company_name: str, inquiry_id: int) -> dict:
    """Local-safe Box substitute. Replace this body with Box SDK calls in production."""
    now = datetime.now()
    folder = Path(upload_root) / now.strftime("%Y%m") / f"{company_name}_{inquiry_id}"
    folder.mkdir(parents=True, exist_ok=True)

    safe_name = secure_filename(file.filename or "attachment")
    stored_name = f"{uuid4().hex}_{safe_name}"
    destination = folder / stored_name
    file.save(destination)

    return {
        "file_id": destination.stem,
        "file_url": str(destination),
        "file_name": file.filename or safe_name,
    }

