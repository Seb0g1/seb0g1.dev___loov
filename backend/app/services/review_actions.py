from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.entities import DraftPost, Project
from app.services.drafts import create_draft_from_product, pick_next_product_for_project
from app.services.publishing import publish_draft


async def process_draft_decision(db: Session, draft_id: int, action: str) -> dict:
    draft = db.get(DraftPost, draft_id)
    if not draft:
        return {"ok": False, "error": "Draft not found"}

    action = action.lower().strip()
    if action == "approve":
        published = await publish_draft(db, draft)
        return {"ok": True, "status": "published", "published_id": published.id}

    if action in {"reject", "cancel"}:
        draft.status = "rejected"
        db.commit()
        db.refresh(draft)
        return {"ok": True, "status": "rejected"}

    if action in {"redo", "next"}:
        draft.status = "rejected"
        db.commit()
        db.refresh(draft)
        project = db.get(Project, draft.project_id) if draft.project_id else None
        if not project:
            return {"ok": True, "status": "rejected", "message": "Project not found"}
        next_product = pick_next_product_for_project(db, project.id, exclude_product_id=draft.product_id)
        if not next_product:
            return {"ok": True, "status": "rejected", "message": "Next product not found"}
        new_draft = await create_draft_from_product(db, next_product, style=draft.style)
        return {"ok": True, "status": "replaced", "draft_id": new_draft.id}

    return {"ok": False, "error": "Unknown decision action"}
