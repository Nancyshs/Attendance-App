"""Bilingual (Arabic / English) user-facing messages.

Messages are authored in Arabic in the code and stored in that form (e.g. in the scan log).
They are translated to English at the edge, based on the `X-Lang` request header
(falls back to `Accept-Language`, then Arabic).
"""
from __future__ import annotations

import re

from fastapi import Request

SUPPORTED = ("ar", "en")


def request_lang(request: Request | None) -> str:
    if request is None:
        return "ar"
    raw = (request.headers.get("x-lang") or request.headers.get("accept-language") or "ar").lower()
    return "en" if raw.startswith("en") else "ar"


# exact Arabic message -> English
EN: dict[str, str] = {
    # generic / auth
    "حدث خطأ من جانبنا. من فضلك حاول مرة أخرى.": "Something went wrong on our side. Please try again.",
    "طلب غير صالح": "Invalid request",
    "غير موجود": "Not found",
    "يجب تسجيل الدخول أولاً": "Not authenticated",
    "انتهت الجلسة، سجّل الدخول مرة أخرى": "Session expired, please sign in again",
    "رمز الدخول غير صالح": "Invalid token",
    "هذا الحساب موقوف": "Account disabled",
    "ليس لديك صلاحية لتنفيذ هذا الإجراء": "You do not have permission for this action",
    "هذا الباج موقوف": "Badge disabled",
    "محاولات كثيرة. انتظر دقيقة ثم حاول مرة أخرى.": "Too many attempts. Please wait a minute and try again.",
    "محاولات دخول فاشلة كثيرة. حاول بعد دقائق.": "Too many failed attempts. Try again in a few minutes.",
    "اسم المستخدم أو كلمة المرور غير صحيحة": "Invalid username or password",
    "كلمة المرور الحالية غير صحيحة": "Current password is incorrect",
    "اسم المستخدم موجود بالفعل": "Username already exists",
    "حساب المحاضر يجب ربطه ببيانات محاضر": "Trainer accounts must be linked to a trainer",
    "المستخدم غير موجود": "User not found",
    "لا يمكنك تقليل صلاحياتك أو إيقاف حسابك": "You cannot demote or disable your own account",
    "محاولات غير صحيحة كثيرة. حاول بعد دقيقة.": "Too many invalid attempts. Try again in a minute.",
    "هذا الباج غير صالح. من فضلك اسأل المنظمين.": "This badge is not valid. Please ask the organisers.",
    "الوقت يجب أن يكون بصيغة HH:MM": "Time must be HH:MM",
    "حجم الصورة كبير (الحد الأقصى 6 ميجا)": "Photo is too large (max 6 MB)",
    "الملف ليس صورة صالحة": "File is not a valid image",
    # reports / settings
    "تاريخ النهاية يجب ألا يسبق تاريخ البداية": "End date must not be before start date",
    "المدة طويلة جداً (الحد الأقصى 400 يوم)": "Range too large (max 400 days)",
    "حسابك غير مرتبط ببيانات محاضر": "Your account is not linked to a trainer profile",
    "أيام العمل يجب أن تكون قائمة أرقام من 0 إلى 6": "Working weekdays must be a list of 0-6",
    "حد التقييم المنخفض يجب أن يكون رقماً": "Low-rating threshold must be a number",
    "اسم البرنامج مطلوب": "Programme name is required",
    "خيار اشتراط الحضور للاستبيان يجب أن يكون نعم/لا": "Require-attendance option must be yes/no",
    # surveys
    "القالب غير موجود": "Template not found",
    "أسئلة الاختيار تحتاج خيارين على الأقل": "Choice questions need at least two options",
    "اختر قالباً آخر كافتراضي بدلاً من إلغاء هذا": "Set another template as default instead of unsetting this one",
    "لا يمكن حذف القالب الافتراضي": "The default template cannot be deleted",
    "هذا القالب مستخدم في محاضرات": "This template is used by sessions",
    "هذا القالب عليه إجابات بالفعل. قم بإيقافه بدلاً من حذفه.": "This template already has responses. Deactivate it instead.",
    "المحاضرة غير موجودة": "Session not found",
    "لا يوجد استبيان مُعدّ": "No survey configured",
    "التقييم يجب أن يكون من 1 إلى 5": "Rating must be 1 to 5",
    "الدرجة يجب أن تكون من 0 إلى 10": "Score must be 0 to 10",
    "اختيار غير صالح": "Invalid choice",
    "إجابة نصية غير صالحة": "Invalid text answer",
    "رابط الاستبيان غير صحيح": "This survey link is not valid",
    "تم إلغاء هذه المحاضرة": "This session was cancelled",
    "استبيان هذه المحاضرة لم يُفتح بعد": "The survey for this session has not opened yet",
    "استبيان هذه المحاضرة مغلق": "The survey for this session is closed",
    "يمكن فقط للمتدربين الذين حضروا هذا اليوم تقييم محاضراته": "Only trainees who attended that day can rate its sessions",
    "لا يوجد قالب استبيان مُعدّ": "No survey template configured",
    "من فضلك أجب عن سؤال واحد على الأقل": "Please answer at least one question",
    "لقد أرسلت هذا الاستبيان من قبل": "You have already submitted this survey",
    # attendance
    "المتدرب غير موجود": "Trainee not found",
    "لا يوجد يوم تدريب في هذا التاريخ. أنشئ اليوم أولاً.": "No training day exists for this date. Create the day first.",
    "الانصراف يحتاج وقت حضور": "A check-out needs a check-in",
    "وقت الانصراف يجب أن يكون بعد الحضور": "Check-out must be after check-in",
    "لا يوجد سجل لهذا اليوم": "No record for this day",
    "الباج غير معروف": "Badge not recognised",
    "هذا المتدرب موقوف": "This trainee is deactivated",
    "لا يوجد تدريب مجدول اليوم": "No training scheduled for today",
    "لا يوجد حضور مسجل اليوم، لا يمكن تسجيل الانصراف": "No check-in recorded today, cannot check out",
    # schedule
    "المحاضر غير موجود": "Trainer not found",
    "يوجد يوم تدريب بالفعل في هذا التاريخ": "A training day already exists for this date",
    "نطاق التاريخ غير صالح (الحد الأقصى سنة)": "Invalid date range (max one year)",
    "يوم التدريب غير موجود": "Training day not found",
    "هذا اليوم عليه سجلات حضور ولا يمكن حذفه": "This day already has attendance records and cannot be deleted",
    "وقت النهاية يجب أن يكون بعد وقت البداية": "End time must be after start time",
    "هذه المحاضرة عليها إجابات استبيان. اجعلها «ملغاة» بدلاً من حذفها.": "This session already has survey responses. Mark it as cancelled instead.",
    "الملف كبير جداً": "File too large",
    "تعذّرت قراءة الملف. استخدم قالب .xlsx أو ملف .csv بترميز UTF-8": "Could not read the file. Use the .xlsx template or a UTF-8 .csv",
    "التاريخ والبداية والنهاية والعنوان مطلوبة": "Date, start, end and title are required",
    "النهاية يجب أن تكون بعد البداية": "End must be after start",
    # trainees
    "تعذّر إنشاء رمز باج فريد، حاول مرة أخرى": "Could not allocate a unique badge token, try again",
    "أرقام غير صالحة": "Invalid ids",
    "هذا المتدرب له سجلات حضور. قم بإيقافه بدلاً من حذفه.": "This trainee has attendance records. Deactivate instead of deleting.",
    "الاسم مطلوب": "Name is required",
    "اكتملت أرقام كود هذه المحافظة": "This governorate has used all 99 codes",
    "رقم البطاقة يجب أن يكون 14 رقماً": "National ID must be 14 digits",
    "رقم التليفون يجب أن يكون 11 رقماً": "Phone number must be 11 digits",
    "رقم البطاقة مستخدم بالفعل": "This national ID is already used",
    "الكود غير موجود": "This code was not found",
    "هذا الكود غير مفعّل": "This code is deactivated",
    "الاسم لا يطابق هذا الكود": "The name does not match this code",
}

# dynamic messages: (regex on the Arabic text, English template)
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^تم تسجيل الحضور الساعة (\S+)( \(متأخر\))?$"), r"Checked in at \1\2"),
    (re.compile(r"^تم تسجيل الانصراف الساعة (\S+)( \(مبكر\))?$"), r"Checked out at \1\2"),
    (re.compile(r"^تم تسجيل الحضور من قبل الساعة (\S+)$"), r"Already checked in at \1"),
    (re.compile(r"^تم تسجيل الانصراف من قبل الساعة (\S+)$"), r"Already checked out at \1"),
    (re.compile(r"^رقم الباج (\S+) مستخدم بالفعل$"), r"Badge ID \1 is already used"),
    (re.compile(r"^محافظة غير معروفة: (.*)$"), r"Unknown governorate: \1"),
    (re.compile(r"^سؤال غير معروف (\S+)$"), r"Unknown question \1"),
    (re.compile(r"^السؤال مطلوب: (.*)$"), r"Question is required: \1"),
    (re.compile(r"^«(.*)» موجود بالفعل، تم التخطي$"), r"'\1' already exists, skipped"),
    (re.compile(r"^(\w+): الوقت يجب أن يكون بصيغة HH:MM$"), r"\1 must be HH:MM"),
    (re.compile(r"^(\w+): يجب أن يكون رقماً صحيحاً غير سالب$"), r"\1 must be a non-negative integer"),
]
_SUFFIXES = {" (متأخر)": " (late)", " (مبكر)": " (early)"}


def translate(message: str | None, lang: str) -> str | None:
    """Arabic message -> `lang`. Unknown messages are returned unchanged."""
    if not message or lang != "en":
        return message
    if message in EN:
        return EN[message]
    for pattern, template in _PATTERNS:
        m = pattern.match(message)
        if m:
            out = m.expand(template)
            for ar, en in _SUFFIXES.items():
                out = out.replace(ar, en)
            return out
    # "a; b; c" joined validation errors
    if "; " in message:
        return "; ".join(translate(p, lang) or p for p in message.split("; "))
    return message
