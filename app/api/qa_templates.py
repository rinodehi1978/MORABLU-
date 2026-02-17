from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.qa_template import QaTemplate

router = APIRouter(prefix="/qa-templates", tags=["qa-templates"])


class QaTemplateRead(BaseModel):
    id: int
    category_key: str
    category: str
    subcategory: str | None
    platform: str
    answer_template: str
    staff_notes: str | None

    model_config = {"from_attributes": True}


class QaTemplateCreate(BaseModel):
    category_key: str = "other"
    category: str
    subcategory: str | None = None
    platform: str = "common"
    answer_template: str
    staff_notes: str | None = None


class QaTemplateUpdate(BaseModel):
    category_key: str | None = None
    category: str | None = None
    subcategory: str | None = None
    platform: str | None = None
    answer_template: str | None = None
    staff_notes: str | None = None


@router.get("/", response_model=list[QaTemplateRead])
def list_templates(
    search: str | None = Query(None),
    category_key: str | None = Query(None),
    category: str | None = Query(None),
    platform: str | None = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(QaTemplate)
    if platform:
        query = query.filter(
            QaTemplate.platform.in_([platform, "common"])
        )
    if category_key:
        query = query.filter(QaTemplate.category_key == category_key)
    if category:
        query = query.filter(QaTemplate.category.ilike(f"%{category}%"))
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                QaTemplate.category.ilike(pattern),
                QaTemplate.subcategory.ilike(pattern),
                QaTemplate.answer_template.ilike(pattern),
            )
        )
    return query.all()


@router.post("/", response_model=QaTemplateRead, status_code=201)
def create_template(data: QaTemplateCreate, db: Session = Depends(get_db)):
    template = QaTemplate(
        category_key=data.category_key,
        category=data.category,
        subcategory=data.subcategory,
        platform=data.platform,
        answer_template=data.answer_template,
        staff_notes=data.staff_notes,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


@router.put("/{template_id}", response_model=QaTemplateRead)
def update_template(
    template_id: int, data: QaTemplateUpdate, db: Session = Depends(get_db)
):
    template = db.query(QaTemplate).filter(QaTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(template, field, value)

    db.commit()
    db.refresh(template)
    return template


@router.delete("/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db)):
    template = db.query(QaTemplate).filter(QaTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    db.delete(template)
    db.commit()
    return {"detail": "テンプレートを削除しました"}
