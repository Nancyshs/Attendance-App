"""Survey template management (admin)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from ..core.db import get_db
from ..core.errors import Conflict, NotFound, ServiceError
from ..deps import admin_only, audit, staff_or_admin
from ..models import LectureSession, SurveyAnswer, SurveyQuestion, SurveyTemplate, User
from ..schemas import TemplateIn, TemplateOut

router = APIRouter(prefix="/survey-templates", tags=["surveys"])


def _load(db: Session, template_id: int) -> SurveyTemplate:
    t = db.scalar(
        select(SurveyTemplate).options(selectinload(SurveyTemplate.questions)).where(SurveyTemplate.id == template_id)
    )
    if t is None:
        raise NotFound("القالب غير موجود")
    return t


def _question_has_answers(db: Session, question_id: int) -> bool:
    return bool(db.scalar(select(func.count()).select_from(SurveyAnswer).where(SurveyAnswer.question_id == question_id)))


def _apply(db: Session, tpl: SurveyTemplate, body: TemplateIn) -> None:
    for q in body.questions:
        if q.type == "choice" and (not q.options or len(q.options) < 2):
            raise ServiceError("أسئلة الاختيار تحتاج خيارين على الأقل", code="invalid_question")

    existing = {q.id: q for q in tpl.questions}
    keep: set[int] = set()
    for pos, qin in enumerate(body.questions):
        q = existing.get(qin.id) if qin.id else None
        if q is None:
            q = SurveyQuestion(template_id=tpl.id)
            tpl.questions.append(q)
        elif q.type != qin.type and _question_has_answers(db, q.id):
            raise ServiceError(
                f'Cannot change the type of "{q.text}" because it already has answers. Add a new question instead.',
                code="invalid_question",
            )
        q.position = pos
        q.text = qin.text
        q.type = qin.type
        q.options = qin.options if qin.type == "choice" else None
        q.required = qin.required
        q.is_active = True
        db.flush()
        keep.add(q.id)

    for qid, q in existing.items():
        if qid in keep:
            continue
        if _question_has_answers(db, qid):
            q.is_active = False  # preserve historic answers, hide from new surveys
        else:
            tpl.questions.remove(q)


@router.get("", response_model=list[TemplateOut])
def list_templates(_: User = Depends(staff_or_admin), db: Session = Depends(get_db)) -> list[TemplateOut]:
    stmt = select(SurveyTemplate).options(selectinload(SurveyTemplate.questions)).order_by(SurveyTemplate.id)
    return [_out(t) for t in db.scalars(stmt)]


def _out(t: SurveyTemplate) -> TemplateOut:
    """Serialise without retired (deactivated) questions; never mutates the ORM object."""
    out = TemplateOut.model_validate(t)
    out.questions = [q for q in out.questions if q.is_active]
    return out


@router.post("", response_model=TemplateOut, status_code=201)
def create_template(
    body: TemplateIn, request: Request, user: User = Depends(admin_only), db: Session = Depends(get_db)
) -> TemplateOut:
    tpl = SurveyTemplate(
        name=body.name, description=body.description, is_anonymous=body.is_anonymous, is_active=body.is_active
    )
    db.add(tpl)
    db.flush()
    _apply(db, tpl, body)
    if body.is_default or not db.scalar(select(SurveyTemplate.id).where(SurveyTemplate.is_default.is_(True))):
        db.execute(update(SurveyTemplate).values(is_default=False))
        tpl.is_default = True
    audit(db, user, "survey_template_created", "survey_template", tpl.id, {"name": tpl.name}, request)
    db.commit()
    return _out(_load(db, tpl.id))


@router.put("/{template_id}", response_model=TemplateOut)
def update_template(
    template_id: int, body: TemplateIn, request: Request, user: User = Depends(admin_only), db: Session = Depends(get_db)
) -> TemplateOut:
    tpl = _load(db, template_id)
    tpl.name = body.name
    tpl.description = body.description
    tpl.is_anonymous = body.is_anonymous
    tpl.is_active = body.is_active
    _apply(db, tpl, body)
    if body.is_default and not tpl.is_default:
        db.execute(update(SurveyTemplate).values(is_default=False))
        tpl.is_default = True
    elif not body.is_default and tpl.is_default:
        raise Conflict("اختر قالباً آخر كافتراضي بدلاً من إلغاء هذا", "default_required")
    audit(db, user, "survey_template_updated", "survey_template", tpl.id, {"name": tpl.name}, request)
    db.commit()
    return _out(_load(db, tpl.id))


@router.delete("/{template_id}", status_code=204)
def delete_template(
    template_id: int, request: Request, user: User = Depends(admin_only), db: Session = Depends(get_db)
) -> None:
    tpl = _load(db, template_id)
    if tpl.is_default:
        raise Conflict("لا يمكن حذف القالب الافتراضي", "default_required")
    in_use = db.scalar(select(func.count()).select_from(LectureSession).where(LectureSession.template_id == tpl.id))
    if in_use:
        raise Conflict("هذا القالب مستخدم في محاضرات", "in_use")
    if any(_question_has_answers(db, q.id) for q in tpl.questions):
        raise Conflict("هذا القالب عليه إجابات بالفعل. قم بإيقافه بدلاً من حذفه.", "has_records")
    audit(db, user, "survey_template_deleted", "survey_template", tpl.id, {"name": tpl.name}, request)
    db.delete(tpl)
    db.commit()
