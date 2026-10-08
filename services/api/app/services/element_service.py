import hashlib
import json
import re
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Iterable

from PIL import Image, ImageFilter, ImageOps

from app.core.config import settings
from app.schemas.elements import ElementBinding, ResolvedElementBinding
from app.services.identity_service import sign_element_asset_access, verify_element_asset_access


PROJECT_ROOT = Path(__file__).resolve().parents[4]
ELEMENT_STORAGE_DIR = (PROJECT_ROOT / "storage" / "elements").resolve()
ASSET_DIR = (ELEMENT_STORAGE_DIR / "assets").resolve()
DB_PATH = ELEMENT_STORAGE_DIR / "elements.sqlite3"
_DB_LOCK = Lock()

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
HANDLE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")
MENTION_RE = re.compile(r"(?<![A-Za-z0-9_])@([A-Za-z][A-Za-z0-9_-]{0,31})")
VALID_ASSET_ROLES = {"primary", "face", "full_body", "profile", "costume", "object", "location", "style", "support"}


def _auto_asset_role(element_type: str, index: int) -> str:
    if element_type == "character":
        return ("face", "full_body", "profile", "costume")[index] if index < 4 else "support"
    if element_type == "prop":
        return "object"
    if element_type == "location":
        return "location"
    if element_type == "style":
        return "style"
    return "support"


class ElementError(RuntimeError):
    pass


@dataclass(frozen=True)
class UploadedElementAsset:
    original_filename: str
    content_type: str
    data: bytes
    role: str = "support"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    ELEMENT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def initialize_element_store() -> None:
    with _DB_LOCK, closing(_connect()) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS elements (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                name TEXT NOT NULL,
                handle TEXT NOT NULL,
                handle_key TEXT NOT NULL,
                type TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                current_version_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(workspace_id, handle_key)
            );

            CREATE TABLE IF NOT EXISTS element_assets (
                id TEXT PRIMARY KEY,
                element_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                width INTEGER,
                height INTEGER,
                sha256 TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'support',
                created_at TEXT NOT NULL,
                FOREIGN KEY(element_id) REFERENCES elements(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS element_versions (
                id TEXT PRIMARY KEY,
                element_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                manifest_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(element_id, version),
                FOREIGN KEY(element_id) REFERENCES elements(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_elements_workspace ON elements(workspace_id, status, updated_at);
            CREATE INDEX IF NOT EXISTS idx_assets_element ON element_assets(element_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_versions_element ON element_versions(element_id, version DESC);
            """
        )


def normalize_handle(value: str) -> str:
    handle = value.strip().lstrip("@").strip()
    if not HANDLE_RE.fullmatch(handle):
        raise ElementError(
            "Element handle must start with a letter and contain only letters, numbers, '_' or '-' (max 32 chars)."
        )
    return handle


def _element_dir(workspace_id: str, element_id: str) -> Path:
    path = (ASSET_DIR / workspace_id / element_id).resolve()
    expected = (ASSET_DIR / workspace_id).resolve()
    if path.parent != expected:
        raise ElementError("Invalid element storage path.")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _inspect_image(data: bytes, content_type: str, original_filename: str) -> tuple[str, int, int]:
    if not data:
        raise ElementError("Reference image is empty.")
    max_bytes = max(1, int(settings.element_max_upload_mb)) * 1024 * 1024
    if len(data) > max_bytes:
        raise ElementError(f"Reference image exceeds the {settings.element_max_upload_mb} MB upload limit.")

    suffix = Path(original_filename or "").suffix.lower()
    if content_type not in ALLOWED_IMAGE_TYPES and suffix not in ALLOWED_SUFFIXES:
        raise ElementError("Element references must be PNG, JPEG, or WEBP images.")

    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
        with Image.open(BytesIO(data)) as image:
            width, height = image.size
            fmt = (image.format or "").upper()
    except Exception as exc:
        raise ElementError("Uploaded element reference is not a valid image.") from exc

    if width < 128 or height < 128:
        raise ElementError("Reference images must be at least 128x128 pixels.")
    if width * height > 80_000_000:
        raise ElementError("Reference image dimensions are too large.")

    detected = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}.get(fmt)
    if not detected:
        raise ElementError("Unsupported image encoding. Use PNG, JPEG, or WEBP.")
    return detected, int(width), int(height)


def _asset_row_to_dict(row: sqlite3.Row) -> dict:
    access = sign_element_asset_access(row["workspace_id"], row["id"])
    return {
        "id": row["id"],
        "filename": row["filename"],
        "original_filename": row["original_filename"],
        "mime_type": row["mime_type"],
        "size_bytes": row["size_bytes"],
        "width": row["width"],
        "height": row["height"],
        "role": row["role"],
        "asset_url": f"/api/v1/elements/assets/{row['id']}?access={access}",
        "created_at": row["created_at"],
    }


def _get_assets(conn: sqlite3.Connection, workspace_id: str, element_id: str) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT * FROM element_assets WHERE workspace_id=? AND element_id=? ORDER BY created_at, rowid",
            (workspace_id, element_id),
        ).fetchall()
    )


def _latest_version_row(conn: sqlite3.Connection, workspace_id: str, element_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM element_versions WHERE workspace_id=? AND element_id=? ORDER BY version DESC LIMIT 1",
        (workspace_id, element_id),
    ).fetchone()


def _create_version(conn: sqlite3.Connection, workspace_id: str, element_id: str, primary_asset_id: str | None = None) -> sqlite3.Row:
    element = conn.execute(
        "SELECT * FROM elements WHERE workspace_id=? AND id=?",
        (workspace_id, element_id),
    ).fetchone()
    if element is None:
        raise ElementError("Element not found.")
    assets = _get_assets(conn, workspace_id, element_id)
    previous = _latest_version_row(conn, workspace_id, element_id)
    version_number = int(previous["version"]) + 1 if previous else 1
    if primary_asset_id is None:
        old_manifest = json.loads(previous["manifest_json"]) if previous else {}
        old_primary = old_manifest.get("primary_asset_id")
        asset_ids = {row["id"] for row in assets}
        primary_asset_id = old_primary if old_primary in asset_ids else (assets[0]["id"] if assets else None)
    manifest = {
        "name": element["name"],
        "handle": element["handle"],
        "type": element["type"],
        "description": element["description"],
        "status": element["status"],
        "primary_asset_id": primary_asset_id,
        "asset_ids": [row["id"] for row in assets],
    }
    version_id = f"ev_{uuid.uuid4().hex}"
    now = _utc_now()
    conn.execute(
        "INSERT INTO element_versions(id, element_id, workspace_id, version, manifest_json, created_at) VALUES(?,?,?,?,?,?)",
        (version_id, element_id, workspace_id, version_number, json.dumps(manifest, separators=(",", ":")), now),
    )
    conn.execute(
        "UPDATE elements SET current_version_id=?, updated_at=? WHERE workspace_id=? AND id=?",
        (version_id, now, workspace_id, element_id),
    )
    return conn.execute("SELECT * FROM element_versions WHERE id=?", (version_id,)).fetchone()


def _serialize_element(conn: sqlite3.Connection, row: sqlite3.Row, version_id: str | None = None) -> dict:
    version = None
    if version_id:
        version = conn.execute(
            "SELECT * FROM element_versions WHERE workspace_id=? AND element_id=? AND id=?",
            (row["workspace_id"], row["id"], version_id),
        ).fetchone()
    if version is None and row["current_version_id"]:
        version = conn.execute(
            "SELECT * FROM element_versions WHERE id=?",
            (row["current_version_id"],),
        ).fetchone()
    if version is None:
        raise ElementError("Element has no version manifest.")
    manifest = json.loads(version["manifest_json"])
    asset_rows = _get_assets(conn, row["workspace_id"], row["id"])
    asset_by_id = {asset["id"]: asset for asset in asset_rows}
    assets = [asset_by_id[asset_id] for asset_id in manifest.get("asset_ids", []) if asset_id in asset_by_id]
    return {
        "id": row["id"],
        "name": manifest.get("name") or row["name"],
        "handle": manifest.get("handle") or row["handle"],
        "type": manifest.get("type") or row["type"],
        "description": manifest.get("description") or "",
        "status": manifest.get("status") or row["status"],
        "current_version_id": version["id"],
        "current_version": int(version["version"]),
        "primary_asset_id": manifest.get("primary_asset_id"),
        "assets": [_asset_row_to_dict(asset) for asset in assets],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_elements(workspace_id: str, *, include_archived: bool = False) -> list[dict]:
    initialize_element_store()
    with closing(_connect()) as conn:
        sql = "SELECT * FROM elements WHERE workspace_id=?"
        params: list[object] = [workspace_id]
        if not include_archived:
            sql += " AND status='active'"
        sql += " ORDER BY updated_at DESC, name COLLATE NOCASE"
        return [_serialize_element(conn, row) for row in conn.execute(sql, params).fetchall()]


def get_element(workspace_id: str, element_id: str, *, version_id: str | None = None) -> dict:
    initialize_element_store()
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM elements WHERE workspace_id=? AND id=?", (workspace_id, element_id)).fetchone()
        if row is None:
            raise ElementError("Element not found.")
        return _serialize_element(conn, row, version_id=version_id)


def _workspace_element_count(conn: sqlite3.Connection, workspace_id: str) -> int:
    row = conn.execute("SELECT COUNT(*) AS count FROM elements WHERE workspace_id=? AND status='active'", (workspace_id,)).fetchone()
    return int(row["count"] if row else 0)


def _save_asset(conn: sqlite3.Connection, workspace_id: str, element_id: str, upload: UploadedElementAsset, *, role: str) -> str:
    mime, width, height = _inspect_image(upload.data, upload.content_type, upload.original_filename)
    suffix = ALLOWED_IMAGE_TYPES[mime]
    asset_id = f"ea_{uuid.uuid4().hex}"
    filename = f"{asset_id}{suffix}"
    directory = _element_dir(workspace_id, element_id)
    path = (directory / filename).resolve()
    if path.parent != directory:
        raise ElementError("Invalid element asset destination.")
    path.write_bytes(upload.data)
    now = _utc_now()
    conn.execute(
        """INSERT INTO element_assets(
            id, element_id, workspace_id, filename, original_filename, mime_type,
            size_bytes, width, height, sha256, role, created_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            asset_id, element_id, workspace_id, filename,
            (upload.original_filename or filename)[:255], mime, len(upload.data),
            width, height, hashlib.sha256(upload.data).hexdigest(), role, now,
        ),
    )
    return asset_id


def create_element(
    workspace_id: str,
    *,
    name: str,
    handle: str,
    element_type: str,
    description: str,
    uploads: Iterable[UploadedElementAsset],
) -> dict:
    initialize_element_store()
    clean_name = " ".join(name.split()).strip()
    if not clean_name or len(clean_name) > 80:
        raise ElementError("Element name must be 1-80 characters.")
    clean_handle = normalize_handle(handle or clean_name.replace(" ", ""))
    if element_type not in {"character", "prop", "location", "style"}:
        raise ElementError("Element type must be character, prop, location, or style.")
    clean_description = description.strip()[:1600]
    upload_list = list(uploads)
    if not upload_list:
        raise ElementError("Add at least one reference image before saving an Element.")
    if len(upload_list) > settings.element_max_assets_per_element:
        raise ElementError(f"An Element can contain at most {settings.element_max_assets_per_element} reference images.")

    element_id = f"el_{uuid.uuid4().hex}"
    now = _utc_now()
    with _DB_LOCK, closing(_connect()) as conn:
        if _workspace_element_count(conn, workspace_id) >= settings.element_max_stored_per_workspace:
            raise ElementError(f"This workspace can store at most {settings.element_max_stored_per_workspace} active Elements.")
        try:
            conn.execute(
                """INSERT INTO elements(id, workspace_id, name, handle, handle_key, type, description, status, created_at, updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (element_id, workspace_id, clean_name, clean_handle, clean_handle.lower(), element_type, clean_description, "active", now, now),
            )
        except sqlite3.IntegrityError as exc:
            raise ElementError(f"@{clean_handle} already exists in this workspace.") from exc

        asset_ids: list[str] = []
        try:
            for index, upload in enumerate(upload_list):
                requested_role = upload.role if upload.role in VALID_ASSET_ROLES else "support"
                # Older clients sent every upload as plain "support". Give those
                # references useful semantic roles automatically so the reference
                # sheet can separate face identity from wardrobe/body guidance.
                role = _auto_asset_role(element_type, index) if requested_role == "support" else requested_role
                asset_ids.append(_save_asset(conn, workspace_id, element_id, upload, role=role))
            _create_version(conn, workspace_id, element_id, primary_asset_id=asset_ids[0])
            conn.commit()
        except Exception:
            conn.rollback()
            directory = _element_dir(workspace_id, element_id)
            for child in directory.glob("*"):
                child.unlink(missing_ok=True)
            directory.rmdir()
            raise

        row = conn.execute("SELECT * FROM elements WHERE id=?", (element_id,)).fetchone()
        return _serialize_element(conn, row)


def add_element_assets(workspace_id: str, element_id: str, uploads: Iterable[UploadedElementAsset]) -> dict:
    upload_list = list(uploads)
    if not upload_list:
        raise ElementError("Choose at least one reference image.")
    with _DB_LOCK, closing(_connect()) as conn:
        element = conn.execute("SELECT * FROM elements WHERE workspace_id=? AND id=?", (workspace_id, element_id)).fetchone()
        if element is None:
            raise ElementError("Element not found.")
        existing = _get_assets(conn, workspace_id, element_id)
        if len(existing) + len(upload_list) > settings.element_max_assets_per_element:
            raise ElementError(f"An Element can contain at most {settings.element_max_assets_per_element} reference images.")
        for offset, upload in enumerate(upload_list):
            requested_role = upload.role if upload.role in VALID_ASSET_ROLES else "support"
            role = _auto_asset_role(str(element["type"]), len(existing) + offset) if requested_role == "support" else requested_role
            _save_asset(conn, workspace_id, element_id, upload, role=role)
        _create_version(conn, workspace_id, element_id)
        conn.commit()
        row = conn.execute("SELECT * FROM elements WHERE id=?", (element_id,)).fetchone()
        return _serialize_element(conn, row)


def update_element(workspace_id: str, element_id: str, values: dict) -> dict:
    allowed = {"name", "handle", "description", "status", "primary_asset_id"}
    changes = {key: value for key, value in values.items() if key in allowed and value is not None}
    if not changes:
        return get_element(workspace_id, element_id)

    with _DB_LOCK, closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM elements WHERE workspace_id=? AND id=?", (workspace_id, element_id)).fetchone()
        if row is None:
            raise ElementError("Element not found.")
        updates: list[str] = []
        params: list[object] = []
        if "name" in changes:
            name = " ".join(str(changes["name"]).split()).strip()
            if not name or len(name) > 80:
                raise ElementError("Element name must be 1-80 characters.")
            updates.append("name=?")
            params.append(name)
        if "handle" in changes:
            handle = normalize_handle(str(changes["handle"]))
            updates.extend(["handle=?", "handle_key=?"])
            params.extend([handle, handle.lower()])
        if "description" in changes:
            updates.append("description=?")
            params.append(str(changes["description"]).strip()[:1600])
        if "status" in changes:
            status = str(changes["status"])
            if status not in {"active", "archived"}:
                raise ElementError("Invalid Element status.")
            updates.append("status=?")
            params.append(status)
        now = _utc_now()
        updates.append("updated_at=?")
        params.append(now)
        params.extend([workspace_id, element_id])
        try:
            conn.execute(f"UPDATE elements SET {', '.join(updates)} WHERE workspace_id=? AND id=?", params)
        except sqlite3.IntegrityError as exc:
            raise ElementError("That @handle is already used by another Element.") from exc

        primary = changes.get("primary_asset_id")
        if primary:
            exists = conn.execute(
                "SELECT 1 FROM element_assets WHERE workspace_id=? AND element_id=? AND id=?",
                (workspace_id, element_id, primary),
            ).fetchone()
            if not exists:
                raise ElementError("Primary reference does not belong to this Element.")
        _create_version(conn, workspace_id, element_id, primary_asset_id=primary)
        conn.commit()
        updated = conn.execute("SELECT * FROM elements WHERE id=?", (element_id,)).fetchone()
        return _serialize_element(conn, updated)


def archive_element(workspace_id: str, element_id: str) -> dict:
    return update_element(workspace_id, element_id, {"status": "archived"})


def resolve_element_asset(workspace_id: str, asset_id: str) -> tuple[Path, str]:
    initialize_element_store()
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT * FROM element_assets WHERE workspace_id=? AND id=?",
            (workspace_id, asset_id),
        ).fetchone()
        if row is None:
            raise ElementError("Element asset not found.")
        path = (_element_dir(workspace_id, row["element_id"]) / row["filename"]).resolve()
        if not path.exists():
            raise ElementError("Element asset file is missing.")
        return path, row["mime_type"]


def resolve_element_asset_with_access(asset_id: str, access_token: str | None) -> tuple[Path, str]:
    """Resolve one preview image through an asset-scoped signed URL.

    This exists for browser <img> requests, which cannot attach Triven's custom
    workspace header during split-origin local development. The token grants
    access only to this asset and expires; it is not a reusable workspace token.
    """
    initialize_element_store()
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM element_assets WHERE id=?", (asset_id,)).fetchone()
        if row is None or not verify_element_asset_access(row["workspace_id"], asset_id, access_token):
            raise ElementError("Element asset not found.")
        path = (_element_dir(row["workspace_id"], row["element_id"]) / row["filename"]).resolve()
        if not path.exists():
            raise ElementError("Element asset file is missing.")
        return path, row["mime_type"]


def resolve_element_bindings(workspace_id: str, bindings: list[ElementBinding]) -> list[ResolvedElementBinding]:
    if len(bindings) > settings.element_max_active_per_scene:
        raise ElementError(f"At most {settings.element_max_active_per_scene} Elements can be active in one request.")
    resolved: list[ResolvedElementBinding] = []
    seen: set[str] = set()
    counts = {"character": 0, "prop": 0, "location": 0, "style": 0}
    for binding in bindings:
        if binding.element_id in seen:
            continue
        seen.add(binding.element_id)
        element = get_element(workspace_id, binding.element_id, version_id=binding.version_id)
        if element["status"] != "active":
            raise ElementError(f"@{element['handle']} is archived and cannot be used for generation.")
        counts[element["type"]] += 1
        limits = {
            "character": settings.element_max_characters_per_scene,
            "prop": settings.element_max_props_per_scene,
            "location": settings.element_max_locations_per_scene,
            "style": settings.element_max_styles_per_scene,
        }
        if counts[element["type"]] > limits[element["type"]]:
            raise ElementError(f"Too many {element['type']} Elements are active for one scene (max {limits[element['type']]}).")
        primary_id = element.get("primary_asset_id")
        primary = next((asset for asset in element["assets"] if asset["id"] == primary_id), None)
        if primary is None and element["assets"]:
            primary = element["assets"][0]
        if primary is None:
            raise ElementError(f"@{element['handle']} has no usable reference image.")
        ordered_assets = [primary] + [asset for asset in element["assets"] if asset["id"] != primary["id"]]
        reference_paths: list[str] = []
        reference_urls: list[str] = []
        reference_roles: list[str] = []
        for asset in ordered_assets:
            asset_path, _ = resolve_element_asset(workspace_id, asset["id"])
            reference_paths.append(str(asset_path))
            reference_urls.append(asset["asset_url"])
            reference_roles.append(str(asset.get("role") or "support"))
        resolved.append(
            ResolvedElementBinding(
                element_id=element["id"],
                version_id=element["current_version_id"],
                handle=element["handle"],
                name=element["name"],
                type=element["type"],
                description=element["description"],
                reference_mode=binding.reference_mode,
                wardrobe_policy=binding.wardrobe_policy,
                strength=binding.strength,
                apply_to_all_scenes=binding.apply_to_all_scenes,
                cast_role=binding.cast_role,
                primary_asset_path=reference_paths[0],
                primary_asset_url=reference_urls[0],
                reference_asset_paths=reference_paths,
                reference_asset_urls=reference_urls,
                reference_asset_roles=reference_roles,
            )
        )
    return resolved


def elements_for_scene(scene_prompt: str, bindings: list[ResolvedElementBinding]) -> list[ResolvedElementBinding]:
    mentions = {match.group(1).lower() for match in MENTION_RE.finditer(scene_prompt or "")}
    # A scene that opens on an exact image (for example a product shot) is defined by that image. Elements
    # that are merely carried across all scenes must not leak into it; only what the scene names stays.
    opens_on_image = any(
        binding.reference_mode == "start_frame" and binding.handle.lower() in mentions for binding in bindings
    )
    selected = [
        binding for binding in bindings
        if binding.handle.lower() in mentions or (binding.apply_to_all_scenes and not opens_on_image)
    ]
    start_frames = [binding for binding in selected if binding.reference_mode == "start_frame"]
    if len(start_frames) > 1:
        handles = ", ".join(f"@{item.handle}" for item in start_frames)
        raise ElementError(
            "Only one Element can be the exact start frame for a scene. "
            f"Change the others to Identity reference: {handles}"
        )
    # If the user's top-level prompt contains explicit bindings but a deterministic
    # split moved the @mention into a neighboring segment, preserve character/style
    # identity across the film when marked global; otherwise do not inject unused assets.
    return selected


_TAG_RUN_RE = re.compile(
    r"(?<![A-Za-z0-9_@])((?:@[A-Za-z][A-Za-z0-9_-]{0,31}[ \t,;]+)*@[A-Za-z][A-Za-z0-9_-]{0,31})\s*$"
)
_SENTENCE_END = ".!?…\"”’)]"


def split_trailing_tags(prompt: str) -> tuple[str, list[str]]:
    """Split a prompt into (story text, handles tagged in a trailing run).

    A trailing run such as ``... room tone. @ijustine @radha`` is a list of reference tags, not
    part of the story: it starts a new sentence/line and contains nothing but @handles. A single
    mention that ends a sentence (``she walks to @Mira``) is narrative and is left in the story.
    """
    text = (prompt or "").rstrip()
    match = _TAG_RUN_RE.search(text)
    if not match:
        return text, []
    before = text[: match.start()]
    stripped = before.rstrip()
    starts_clean = (
        not stripped
        or stripped[-1] in _SENTENCE_END
        or "\n" in before[len(stripped):]
    )
    if not starts_clean:
        return text, []
    handles = [item.lstrip("@") for item in re.findall(r"@[A-Za-z][A-Za-z0-9_-]{0,31}", match.group(1))]
    return before, handles


def park_tag_only_characters(
    prompt: str, bindings: list[ResolvedElementBinding]
) -> tuple[list[ResolvedElementBinding], list[ResolvedElementBinding]]:
    """Keep a character that is only a trailing tag out of the identity reference.

    Ingredients conditioning blends every Character panel it is given. When the shot text describes
    one person and extra Characters are merely tagged after the last sentence, those extra faces
    leak into the subject and identity drifts. Returns ``(kept, parked)``; nothing is parked unless
    another Character is mentioned inside the story text, and ``cast_role="cast"`` always stays.
    """
    story, tags = split_trailing_tags(prompt)
    if not tags:
        return list(bindings), []
    story_mentions = {match.group(1).lower() for match in MENTION_RE.finditer(story)}
    tag_set = {handle.lower() for handle in tags}
    narrative_character = any(
        item.type == "character" and item.handle.lower() in story_mentions for item in bindings
    )
    if not narrative_character:
        return list(bindings), []
    kept: list[ResolvedElementBinding] = []
    parked: list[ResolvedElementBinding] = []
    for item in bindings:
        handle = item.handle.lower()
        if (
            item.type == "character"
            and item.cast_role != "cast"
            and handle in tag_set
            and handle not in story_mentions
        ):
            parked.append(item)
        else:
            kept.append(item)
    return kept, parked


def parked_character_warning(parked: list[ResolvedElementBinding]) -> str:
    names = ", ".join(f"@{item.handle}" for item in parked)
    return (
        f"{names} {'is' if len(parked) == 1 else 'are'} only tagged after the last sentence and never described in the shot, "
        "so the identity reference was limited to the Character(s) the scene is about to avoid blending faces. "
        "Describe the Character in the scene text, or choose Keep in shot, to include them."
    )


WARDROBE_DESCRIPTION_TERMS = (
    "wear", "wearing", "wardrobe", "outfit", "costume", "sweater", "shirt", "t-shirt",
    "dress", "jacket", "coat", "top", "blouse", "hoodie", "trouser", "pants", "jeans",
    "skirt", "shorts", "vest", "suit", "tie", "shoe", "boots", "sleeve", "neckline",
)


def _identity_only_description(value: str) -> str:
    """Keep identity traits while removing reference-clothing text for prompt wardrobe mode."""
    sentences = [piece.strip() for piece in re.split(r"(?<=[.!?])\s+|[;\n]+", value or "") if piece.strip()]
    identity = [
        sentence for sentence in sentences
        if not any(term in sentence.lower() for term in WARDROBE_DESCRIPTION_TERMS)
    ]
    return " ".join(identity)[:420].strip()


def compile_element_prompt(scene_prompt: str, bindings: list[ResolvedElementBinding]) -> str:
    if not bindings:
        return scene_prompt

    action = scene_prompt
    for binding in bindings:
        action = re.sub(
            rf"(?<![A-Za-z0-9_])@{re.escape(binding.handle)}\b",
            binding.name,
            action,
            flags=re.IGNORECASE,
        )

    identity_bindings = [binding for binding in bindings if binding.reference_mode == "identity"]
    start_frame_bindings = [binding for binding in bindings if binding.reference_mode == "start_frame"]
    blocks: list[str] = []

    if identity_bindings or len(bindings) > 1:
        # Wording matters: describing a "reference sheet" with "Panel N: CHARACTER ..." made LTX draw
        # exactly that, a fake document page with garbled titles, for the first ~3 seconds of the clip
        # (observed in a real render). Identity text must read as plain subject description.
        subject_lines: list[str] = []
        for binding in bindings:
            if binding.type == "character" and binding.wardrobe_policy == "prompt":
                description = _identity_only_description(binding.description)
                wardrobe_note = (
                    " Keep this person's face, hairline, age, skin and body proportions. "
                    "The clothing is whatever the Generated video text describes."
                )
            else:
                description = " ".join(binding.description.split())[:420]
                wardrobe_note = (
                    " Keep this person's wardrobe exactly as supplied unless the scene changes it."
                    if binding.type == "character" else ""
                )
            subject_lines.append(f"{binding.name} ({binding.type}). {description}{wardrobe_note}".rstrip())
        blocks.append("Subjects: " + " ".join(subject_lines))
        blocks.append(
            "The video opens directly inside the live scene, with the subject already in natural motion "
            "from the very first frame."
        )
        prompt_wardrobe = [
            binding.name for binding in identity_bindings
            if binding.type == "character" and binding.wardrobe_policy == "prompt"
        ]
        if prompt_wardrobe:
            blocks.append(
                "IDENTITY / WARDROBE SEPARATION: For " + ", ".join(prompt_wardrobe) +
                ", take only facial identity, hairline, age and stable human proportions from the supplied identity. "
                "The Generated video wardrobe description is authoritative. Do not copy, blend, layer, recolor, "
                "or hybridize clothing from the supplied identity when the scene specifies different clothing. "
                "Keep one coherent garment construction with the exact requested colors, pattern and material."
            )

    if start_frame_bindings:
        blocks.append(
            "START FRAME BEHAVIOR: The supplied image is frame 0 and defines the existing composition. "
            "Animate forward from it immediately with natural micro-motion; do not keep the first image frozen "
            "for several seconds and do not recreate the subject as a new instance."
        )

    blocks.append("Generated video: " + action.strip())
    return "\n\n".join(blocks)


def _runs(active: list[bool], min_gap: int) -> list[tuple[int, int]]:
    """Contiguous runs of True values; runs separated by fewer than `min_gap` False values are merged."""
    runs: list[list[int]] = []
    for index, value in enumerate(active):
        if not value:
            continue
        if runs and index - runs[-1][1] <= min_gap:
            runs[-1][1] = index
        else:
            runs.append([index, index])
    return [(start, end) for start, end in runs]


def primary_subject_box(image: Image.Image) -> tuple[int, int, int, int] | None:
    """Bounding box of the main portrait when an upload is really a collage or turnaround sheet.

    A character sheet (one big close-up plus several full-body views on a plain background) fed to LTX as
    the identity reference is simply replayed as the video. When the picture splits into three or more
    separate subjects along the width, return the box of the biggest one; return None for a normal photo.
    """
    width, height = image.size
    if width < 256 or height < 128:
        return None
    scale = 320 / max(width, height)
    small = ImageOps.exif_transpose(image).convert("L").resize(
        (max(32, int(width * scale)), max(32, int(height * scale))), Image.Resampling.BILINEAR
    )
    sw, sh = small.size
    pixels = small.load()
    border = [pixels[x, y] for x in range(sw) for y in (0, 1, sh - 2, sh - 1)] + [
        pixels[x, y] for y in range(sh) for x in (0, 1, sw - 2, sw - 1)
    ]
    background = sorted(border)[len(border) // 2]
    # Textured or busy backgrounds are not "plain": a normal photo.
    # A collage may touch the left/right/top edge, so only a mostly non-plain border means a busy photo.
    if sum(1 for value in border if abs(value - background) > 24) / len(border) > 0.45:
        return None

    columns = [
        sum(1 for y in range(sh) if abs(pixels[x, y] - background) > 28) / sh for x in range(sw)
    ]
    active = [value > 0.03 for value in columns]
    runs = [run for run in _runs(active, 1) if run[1] - run[0] >= max(4, int(sw * 0.03))]
    if len(runs) < 3:
        return None

    mass = [sum(columns[start : end + 1]) for start, end in runs]
    start, end = runs[mass.index(max(mass))]
    pad = max(2, int(sw * 0.01))
    left, right = max(0, start - pad), min(sw - 1, end + pad)
    rows = [
        sum(1 for x in range(left, right + 1) if abs(pixels[x, y] - background) > 28) / (right - left + 1)
        for y in range(sh)
    ]
    ys = [y for y, value in enumerate(rows) if value > 0.03]
    top, bottom = (min(ys), max(ys)) if ys else (0, sh - 1)
    inverse = 1 / scale
    return (
        int(left * inverse),
        int(max(0, top - pad) * inverse),
        min(width, int((right + 1) * inverse)),
        min(height, int((bottom + 1 + pad) * inverse)),
    )


def _open_reference(image_path: str) -> Image.Image:
    """Open a reference photo, cropped to its main subject when the upload is a collage/turnaround sheet."""
    source = ImageOps.exif_transpose(Image.open(image_path)).convert("RGB")
    box = primary_subject_box(source)
    return source.crop(box) if box else source


def replace_handles(text: str, bindings: list[ResolvedElementBinding]) -> str:
    for binding in bindings:
        text = re.sub(
            rf"(?<![A-Za-z0-9_])@{re.escape(binding.handle)}\b", binding.name, text, flags=re.IGNORECASE
        )
    return text


def compile_hero_prompt(scene_prompt: str, bindings: list[ResolvedElementBinding], *, opening: bool) -> str:
    """Prompt for a render that starts from an approved start frame.

    The frame already shows the cast and products, so no reference sheet is built (a sheet next to a start
    frame was replayed as a split screen). Handles become plain names and, on the opening scene, the model is
    told the supplied image is frame 0 and must be animated, not redesigned.
    """
    action = replace_handles(scene_prompt, bindings).strip()
    if not opening or not bindings:
        return action
    names = ", ".join(binding.name for binding in bindings)
    return (
        f"OPENING FRAME: The supplied image is frame 0 and already shows {names} exactly as they must look, including "
        "face, hair, clothing and any product in hand. Start from it and animate forward with natural micro-motion. "
        "Keep every detail identical; do not recreate, redesign, replace or duplicate anyone or anything. "
        "Facial expressions stay natural and restrained, with small believable movements.\n\n"
        f"Generated video: {action}"
    )


def _paste_face_priority_crop(canvas: Image.Image, image_path: str, box: tuple[int, int, int, int]) -> None:
    """Place an upper-face/shoulder crop when a character reference also contains clothing.

    Ingredients strongly carries whatever appears in its reference sheet. For the default
    prompt-wardrobe mode we therefore avoid feeding a large full-body outfit when the user
    wants the face identity but a new garment described in the scene prompt.
    """
    left, top, right, bottom = box
    if right <= left or bottom <= top:
        return
    box_w, box_h = right - left, bottom - top
    with _open_reference(image_path) as source:
        sw, sh = source.size
        if sh >= sw * 0.8:
            # Head-and-shoulders window with the SAME aspect as the box, anchored at the top of the photo.
            # The window fills the whole box: black or padded bars around the portrait were reproduced by
            # LTX as dark hatched pillars with garbled text for the entire clip.
            crop_w = sw
            crop_h = min(sh, max(128, int(round(crop_w * box_h / box_w))))
            y0 = min(max(0, int(sh * 0.02)), sh - crop_h)
            source = source.crop((0, y0, sw, y0 + crop_h))
        fitted = ImageOps.fit(source, (box_w, box_h), method=Image.Resampling.LANCZOS, centering=(0.5, 0.0))
        canvas.paste(fitted, (left, top))


def _blurred_cover(source: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Soft out-of-focus fill for the area a contained image leaves empty (never a hard black bar)."""
    covered = ImageOps.fit(source, size, method=Image.Resampling.BILINEAR)
    return covered.filter(ImageFilter.GaussianBlur(radius=max(8, max(size) // 24)))


def _paste_contained(canvas: Image.Image, image_path: str, box: tuple[int, int, int, int]) -> None:
    left, top, right, bottom = box
    if right <= left or bottom <= top:
        return
    with _open_reference(image_path) as source:
        size = (right - left, bottom - top)
        canvas.paste(_blurred_cover(source, size), (left, top))
        fitted = ImageOps.contain(source, size, method=Image.Resampling.LANCZOS)
        x = left + (size[0] - fitted.width) // 2
        y = top + (size[1] - fitted.height) // 2
        canvas.paste(fitted, (x, y))


def _reference_assets_for_panel(binding: ResolvedElementBinding) -> list[tuple[str, str]]:
    paths = list(binding.reference_asset_paths or [binding.primary_asset_path])
    roles = list(binding.reference_asset_roles or [])
    pairs = [
        (path, roles[index] if index < len(roles) else "support")
        for index, path in enumerate(paths)
    ]
    if binding.type != "character":
        return pairs[:3]

    if binding.wardrobe_policy == "prompt":
        # Face/profile references are safe identity signals when the scene asks for
        # a different outfit. Full-body/costume panels can overpower the text prompt.
        identity = [item for item in pairs if item[1] in {"face", "profile"}]
        fallback = [item for item in pairs if item[1] not in {"full_body", "costume"}]
        selected = identity or fallback or pairs[:1]
        return selected[:2]

    priority = {"face": 0, "primary": 1, "full_body": 2, "profile": 3, "costume": 4, "support": 5}
    return sorted(pairs, key=lambda item: priority.get(item[1], 6))[:3]


def _paste_element_panel(canvas: Image.Image, binding: ResolvedElementBinding, box: tuple[int, int, int, int]) -> None:
    """Compose semantically selected views while keeping identity and wardrobe controls separate."""
    left, top, right, bottom = box
    assets = _reference_assets_for_panel(binding)
    if not assets:
        return

    def paste(path: str, role: str, target: tuple[int, int, int, int]) -> None:
        # In prompt-wardrobe mode every character reference is treated as an identity
        # source, even if an older Element mislabeled a full-body upload as `face`.
        # The upper-face crop prevents the reference outfit from overpowering text.
        if binding.type == "character" and binding.wardrobe_policy == "prompt":
            _paste_face_priority_crop(canvas, path, target)
        else:
            _paste_contained(canvas, path, target)

    if len(assets) == 1:
        paste(assets[0][0], assets[0][1], box)
        return

    width = right - left
    primary_right = left + max(1, int(width * 0.68))
    paste(assets[0][0], assets[0][1], (left, top, primary_right, bottom))
    side_left = min(right - 1, primary_right)
    if len(assets) == 2:
        paste(assets[1][0], assets[1][1], (side_left, top, right, bottom))
        return

    middle = top + max(1, (bottom - top) // 2)
    paste(assets[1][0], assets[1][1], (side_left, top, right, middle))
    paste(assets[2][0], assets[2][1], (side_left, middle, right, bottom))

def build_reference_sheet(bindings: list[ResolvedElementBinding], output_path: Path) -> Path:
    if not bindings:
        raise ElementError("Cannot build an Element reference sheet without active Elements.")
    width = max(256, int(settings.element_reference_sheet_width))
    height = max(256, int(settings.element_reference_sheet_height))
    canvas = Image.new("RGB", (width, height), "black")
    count = len(bindings)
    columns = 1 if count == 1 else 2 if count <= 4 else 3
    rows = (count + columns - 1) // columns
    cell_w = width // columns
    cell_h = height // rows

    for index, binding in enumerate(bindings):
        # An identity-only solo presenter needs ONE reference portrait, not a
        # side-by-side multi-view contact sheet. The latter can be reproduced as
        # a split-screen artifact when Ingredients conditioning is strong.
        if count == 1 and binding.type == "character" and binding.wardrobe_policy == "prompt":
            assets = _reference_assets_for_panel(binding)
            if assets:
                _paste_face_priority_crop(canvas, assets[0][0], (0, 0, width, height))
            break
        col = index % columns
        row = index // columns
        left = col * cell_w
        top = row * cell_h
        right = width if col == columns - 1 else left + cell_w
        bottom = height if row == rows - 1 else top + cell_h
        gutter = 4
        _paste_element_panel(
            canvas,
            binding,
            (left + gutter, top + gutter, max(left + gutter + 1, right - gutter), max(top + gutter + 1, bottom - gutter)),
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, format="PNG", optimize=True)
    return output_path


def canonical_reference_paths(bindings: list[ResolvedElementBinding]) -> list[tuple[str, Path]]:
    return [(f"@{binding.handle}", Path(binding.primary_asset_path)) for binding in bindings]
