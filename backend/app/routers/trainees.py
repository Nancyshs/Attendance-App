from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.errors import Conflict, NotFound, ServiceError
from ..core.i18n import request_lang, translate
from ..core.security import new_qr_token
from ..deps import admin_only, audit, staff_or_admin
from ..models import AttendanceDay, Trainee, User
from ..schemas import ImportResult, TraineeIn, TraineeOut, TraineeUpdate
from ..services import badges, exports, media
from ..services import settings as settings_service
from ..services.governorates import canonical_governorate, letter_for, options as governorate_options
from ..services.names import require_triple_name

router = APIRouter(prefix="/trainees", tags=["trainees"])


def _out(t: Trainee) -> TraineeOut:
    out = TraineeOut.model_validate(t)
    out.photo_url = f"/media/{t.photo_path}" if t.photo_path else None
    return out


def next_badge_id(db: Session, governorate: str | None = None) -> str:
    """Next free code.

    With a governorate the code is that governorate's letter plus two digits
    (القاهرة → C01, C02, …). Without one, the legacy sequence A01, A02, … is used.
    """
    used = set(db.scalars(select(Trainee.badge_id)))
    letter = letter_for(governorate)
    if letter is None:
        n = 0
        while n < 26 * 99:
            candidate = f"{chr(65 + n // 99)}{n % 99 + 1:02d}"
            if candidate not in used:
                return candidate
            n += 1
        raise Conflict("تعذّر إنشاء رمز باج فريد، حاول مرة أخرى")
    for n in range(1, 100):
        candidate = f"{letter}{n:02d}"
        if candidate not in used:
            return candidate
    raise Conflict("اكتملت أرقام كود هذه المحافظة", "badge_full")


_INDIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def _exact_digits(value: str | None, length: int, label: str) -> str | None:
    """Empty becomes None. Anything else must be exactly `length` digits."""
    if value is None:
        return None
    raw = "".join(str(value).translate(_INDIC_DIGITS).split())
    if not raw:
        return None
    if len(raw) != length or not raw.isdigit():
        raise ServiceError(f"{label} يجب أن يكون {length} رقماً", code="invalid_contact")
    return raw


def _organization(value: str | None) -> str | None:
    return (value or "").strip() or None


def _governorate(value: str | None) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    name = canonical_governorate(raw)
    if name is None:
        raise ServiceError(f"محافظة غير معروفة: {raw}", code="unknown_governorate")
    return name


def _create(db: Session, data: TraineeIn) -> Trainee:
    explicit = (data.badge_id or "").strip().upper() or None
    governorate = _governorate(data.governorate)
    full_name = require_triple_name(data.full_name)
    badge_id = explicit or next_badge_id(db, governorate)
    for _ in range(5):  # retry on the (astronomically unlikely) token collision
        t = Trainee(
            badge_id=badge_id,
            qr_token=new_qr_token(),
            full_name=full_name,
            governorate=governorate,
            job_title=(data.job_title or "").strip() or None,
            organization=_organization(data.organization),
            national_id=_exact_digits(data.national_id, 14, "رقم البطاقة"),
            email=data.email,
            phone=_exact_digits(data.phone, 11, "رقم التليفون"),
            group_name=data.group_name,
            notes=data.notes,
        )
        try:
            with db.begin_nested():
                db.add(t)
                db.flush()
            return t
        except IntegrityError as exc:
            if "national_id" in str(exc.orig):
                raise Conflict("رقم البطاقة مستخدم بالفعل", "national_id_exists") from None
            if "badge_id" in str(exc.orig):
                if explicit:
                    raise Conflict(f"رقم الباج {badge_id} مستخدم بالفعل", "badge_exists") from None
                badge_id = next_badge_id(db, governorate)
                continue
    raise Conflict("تعذّر إنشاء رمز باج فريد، حاول مرة أخرى")


@router.get("/governorates")
def list_governorates(_: User = Depends(staff_or_admin)) -> list[dict[str, str]]:
    return governorate_options()


@router.get("", response_model=list[TraineeOut])
def list_trainees(
    q: str | None = None,
    active: bool | None = None,
    _: User = Depends(staff_or_admin),
    db: Session = Depends(get_db),
) -> list[TraineeOut]:
    stmt = select(Trainee).order_by(Trainee.badge_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Trainee.full_name.like(like),
                Trainee.badge_id.like(like),
                Trainee.governorate.like(like),
                Trainee.job_title.like(like),
                Trainee.organization.like(like),
                Trainee.national_id.like(like),
                Trainee.phone.like(like),
            )
        )
    if active is not None:
        stmt = stmt.where(Trainee.is_active.is_(active))
    return [_out(t) for t in db.scalars(stmt.limit(1000))]


@router.post("", response_model=TraineeOut, status_code=201)
def create_trainee(
    body: TraineeIn, request: Request, user: User = Depends(admin_only), db: Session = Depends(get_db)
) -> TraineeOut:
    t = _create(db, body)
    audit(db, user, "trainee_created", "trainee", t.id, {"badge_id": t.badge_id, "name": t.full_name}, request)
    db.commit()
    return _out(t)


@router.get("/import-template.xlsx")
def import_template(request: Request, _: User = Depends(admin_only)) -> Response:
    data = exports.template_workbook(
        ["الاسم", "المحافظة", "الوظيفة", "رقم البطاقة", "رقم التليفون", "الجهة"],
        [["أحمد حسن محمد", "القاهرة", "مسؤول إدارة بيئية", "29001011234567", "01001234567", "جهاز شؤون البيئة"]],
        "المتدربون",
    )
    return Response(
        data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="trainees_template.xlsx"'},
    )


@router.post("/import", response_model=ImportResult)
async def import_trainees(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(admin_only),
    db: Session = Depends(get_db),
) -> ImportResult:
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, "الملف كبير جداً")
    try:
        rows = exports.read_table(file.filename or "upload.xlsx", data)
    except Exception:
        raise HTTPException(400, "تعذّرت قراءة الملف. استخدم قالب .xlsx أو ملف .csv بترميز UTF-8") from None

    created = skipped = 0
    errors: list[dict] = []
    existing_names = {n.lower() for n in db.scalars(select(Trainee.full_name))}
    for row in rows:
        name = " ".join(str(row.get("full_name") or row.get("name") or "").split())
        if not name:
            errors.append({"row": row["_row"], "error": "الاسم مطلوب"})
            continue
        if name.lower() in existing_names:
            skipped += 1
            errors.append({"row": row["_row"], "error": f"«{name}» موجود بالفعل، تم التخطي"})
            continue
        try:
            payload = TraineeIn(
                full_name=name,
                governorate=str(row.get("governorate")).strip() or None if row.get("governorate") else None,
                job_title=str(row.get("job_title")).strip() or None if row.get("job_title") else None,
                organization=str(row.get("organization")).strip() or None if row.get("organization") else None,
                national_id=str(row.get("national_id")).strip() or None if row.get("national_id") else None,
                email=(str(row.get("email")).strip() or None) if row.get("email") else None,
                phone=str(row.get("phone")).strip() if row.get("phone") else None,
                group_name=str(row.get("group_name")).strip() if row.get("group_name") else None,
                badge_id=str(row.get("badge_id")).strip().upper() if row.get("badge_id") else None,
            )
            _create(db, payload)
            created += 1
            existing_names.add(name.lower())
        except Exception as exc:  # validation/conflict per-row must not abort the whole import
            msg = getattr(exc, "message", None) or str(exc).splitlines()[0]
            errors.append({"row": row["_row"], "error": msg})
    audit(db, user, "trainees_imported", "trainee", None, {"created": created, "skipped": skipped}, request)
    db.commit()
    lang = request_lang(request)
    for e in errors:
        e["error"] = translate(e["error"], lang)
    return ImportResult(created=created, skipped=skipped, errors=errors)


@router.get("/badges.pdf")
def badges_pdf(
    ids: str | None = Query(default=None, description="comma separated trainee ids; empty = all active"),
    _: User = Depends(staff_or_admin),
    db: Session = Depends(get_db),
) -> Response:
    stmt = select(Trainee).order_by(Trainee.badge_id)
    if ids:
        try:
            wanted = [int(i) for i in ids.split(",") if i.strip()]
        except ValueError:
            raise HTTPException(400, "أرقام غير صالحة") from None
        stmt = stmt.where(Trainee.id.in_(wanted))
    else:
        stmt = stmt.where(Trainee.is_active.is_(True))
    trainees = list(db.scalars(stmt))
    cfg = settings_service.get_all(db)
    pdf = badges.render_badges(trainees, cfg["program_name"])
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": 'inline; filename="badges.pdf"'})


@router.get("/{trainee_id}", response_model=TraineeOut)
def get_trainee(trainee_id: int, _: User = Depends(staff_or_admin), db: Session = Depends(get_db)) -> TraineeOut:
    t = db.get(Trainee, trainee_id)
    if t is None:
        raise NotFound("المتدرب غير موجود")
    return _out(t)


@router.get("/{trainee_id}/qr.svg")
def trainee_qr(trainee_id: int, _: User = Depends(staff_or_admin), db: Session = Depends(get_db)) -> Response:
    t = db.get(Trainee, trainee_id)
    if t is None:
        raise NotFound("المتدرب غير موجود")
    # The QR carries the same code printed next to it (e.g. C01), so a scan and the text match.
    return Response(badges.qr_svg(t.badge_id), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@router.patch("/{trainee_id}", response_model=TraineeOut)
def update_trainee(
    trainee_id: int,
    body: TraineeUpdate,
    request: Request,
    user: User = Depends(admin_only),
    db: Session = Depends(get_db),
) -> TraineeOut:
    t = db.get(Trainee, trainee_id)
    if t is None:
        raise NotFound("المتدرب غير موجود")
    data = body.model_dump(exclude_unset=True)
    if "phone" in data:
        data["phone"] = _exact_digits(data["phone"], 11, "رقم التليفون")
    if "national_id" in data:
        data["national_id"] = _exact_digits(data["national_id"], 14, "رقم البطاقة")
    if "organization" in data:
        data["organization"] = _organization(data["organization"])
    if data.get("full_name"):
        data["full_name"] = require_triple_name(data["full_name"])
    for k, v in data.items():
        setattr(t, k, v)
    audit(db, user, "trainee_updated", "trainee", t.id, data, request)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "national_id" in str(exc.orig):
            raise Conflict("رقم البطاقة مستخدم بالفعل", "national_id_exists") from None
        raise
    return _out(t)


@router.delete("/{trainee_id}", status_code=204)
def delete_trainee(
    trainee_id: int, request: Request, user: User = Depends(admin_only), db: Session = Depends(get_db)
) -> None:
    t = db.get(Trainee, trainee_id)
    if t is None:
        raise NotFound("المتدرب غير موجود")
    has_records = db.scalar(select(func.count()).select_from(AttendanceDay).where(AttendanceDay.trainee_id == t.id))
    if has_records:
        raise Conflict("هذا المتدرب له سجلات حضور. قم بإيقافه بدلاً من حذفه.", "has_records")
    media.delete_photo(t.photo_path)
    audit(db, user, "trainee_deleted", "trainee", t.id, {"badge_id": t.badge_id, "name": t.full_name}, request)
    db.delete(t)
    db.commit()


@router.post("/{trainee_id}/photo", response_model=TraineeOut)
async def upload_photo(
    trainee_id: int,
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(admin_only),
    db: Session = Depends(get_db),
) -> TraineeOut:
    t = db.get(Trainee, trainee_id)
    if t is None:
        raise NotFound("المتدرب غير موجود")
    new_path = media.save_photo(await file.read())
    old = t.photo_path
    t.photo_path = new_path
    audit(db, user, "trainee_photo_updated", "trainee", t.id, request=request)
    db.commit()
    media.delete_photo(old)
    return _out(t)


@router.post("/{trainee_id}/regenerate-token", response_model=TraineeOut)
def regenerate_token(
    trainee_id: int, request: Request, user: User = Depends(admin_only), db: Session = Depends(get_db)
) -> TraineeOut:
    """Invalidates a lost/shared badge. The old QR stops working immediately."""
    t = db.get(Trainee, trainee_id)
    if t is None:
        raise NotFound("المتدرب غير موجود")
    t.qr_token = new_qr_token()
    audit(db, user, "trainee_token_regenerated", "trainee", t.id, request=request)
    db.commit()
    return _out(t)
