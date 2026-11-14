"""Printable badge sheets: each card is only a QR code of the trainee code, such as C01."""
from __future__ import annotations

import io
import ipaddress
import os
import socket
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urlparse

from starlette.requests import Request

import segno
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from ..core.config import settings
from ..models import Trainee

MM = 2.8346456693

PAGE_W = 210 * MM
PAGE_H = 297 * MM

_FONT_CANDIDATES = [
    (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
]
_fonts: tuple[str, str] | None = None


def _register_fonts() -> tuple[str, str]:
    """Registers a Unicode (Arabic capable) font; falls back to Helvetica."""
    global _fonts
    if _fonts:
        return _fonts
    candidates = list(_FONT_CANDIDATES)
    if settings.badge_font_path:
        bold = settings.badge_font_path
        candidates.insert(0, (settings.badge_font_path, bold))
    for regular, bold in candidates:
        if Path(regular).exists():
            pdfmetrics.registerFont(TTFont("BadgeFont", regular))
            pdfmetrics.registerFont(TTFont("BadgeFont-Bold", bold if Path(bold).exists() else regular))
            _fonts = ("BadgeFont", "BadgeFont-Bold")
            return _fonts
    _fonts = ("Helvetica", "Helvetica-Bold")
    return _fonts


def _shape(text: str) -> str:
    """Arabic needs letter joining + right-to-left ordering before it is drawn."""
    if not any("\u0600" <= ch <= "\u06ff" for ch in text):
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display

        return get_display(arabic_reshaper.reshape(text))
    except Exception:  # pragma: no cover - library missing, draw as-is
        return text


def _wrap(c: canvas.Canvas, text: str, font: str, size: float, max_width: float) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for w in words:
        trial = f"{current} {w}".strip()
        if c.stringWidth(_shape(trial), font, size) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines[:3]


def _draw_qr(c: canvas.Canvas, data: str, x: float, y: float, size: float, label: str | None = None) -> None:
    # A label in the middle covers modules, so the code uses the strongest correction.
    qr = segno.make(data, error="h" if label else "m", boost_error=False)
    matrix = [list(row) for row in qr.matrix]
    n = len(matrix)
    module = size / n
    c.setFillColor(HexColor("#000000"))
    for r, row in enumerate(matrix):
        for col, dark in enumerate(row):
            if dark:
                # +0.2pt overlap hides hairline gaps between modules in some PDF viewers
                c.rect(x + col * module, y + size - (r + 1) * module, module + 0.2, module + 0.2, stroke=0, fill=1)
    if not label:
        return
    _, bold = _register_fonts()
    font_size = max(14, min(size * 0.11, 56))
    c.setFont(bold, font_size)
    text_w = c.stringWidth(label, bold, font_size)
    box_w = text_w + 8
    box_h = font_size + 6
    bx = x + (size - box_w) / 2
    by = y + (size - box_h) / 2
    c.setFillColor(HexColor("#ffffff"))
    c.roundRect(bx, by, box_w, box_h, 2, stroke=0, fill=1)
    c.setFillColor(HexColor("#000000"))
    c.drawCentredString(x + size / 2, by + 4, label)


def render_badges(trainees: Sequence[Trainee], program: str, org: str = "") -> bytes:
    """One A4 page per trainee: a large QR centered on the sheet, with the code in its middle."""
    del program, org
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H))
    c.setTitle("باجات المتدربين")
    qr_size = 170 * MM
    qx = (PAGE_W - qr_size) / 2
    qy = (PAGE_H - qr_size) / 2
    for i, t in enumerate(trainees):
        if i:
            c.showPage()
        _draw_qr(c, t.badge_id, qx, qy, qr_size, label=t.badge_id)
    if not trainees:
        c.setFont(_register_fonts()[0], 12)
        c.drawString(20 * MM, PAGE_H - 30 * MM, _shape("لم يتم اختيار متدربين."))
    c.save()
    return buf.getvalue()


def qr_svg(data: str) -> str:
    """SVG of a QR code whose payload is exactly ``data`` (the trainee code)."""
    out = io.BytesIO()
    segno.make(data, error="m").save(out, kind="svg", scale=6, border=2, xmldecl=False, svgns=True)
    return out.getvalue().decode("utf-8")


# ---------------------------------------------------------------------- survey QR
def _lan_ip() -> str | None:
    """IPv4 of the interface used for the default route (the Wi-Fi a phone can reach)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
    except OSError:
        return None
    if not ip or ip.startswith("127."):
        return None
    return ip


def _hostname(hostport: str) -> str:
    value = hostport.strip()
    if value.startswith("["):
        end = value.find("]")
        return value[1:end].lower() if end > 1 else ""
    return value.split(":")[0].strip().lower()


def _is_loopback(host: str) -> bool:
    name = _hostname(host)
    if name in {"localhost", "0.0.0.0", ""}:
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


def _explicit_public_base(raw: str) -> str | None:
    """A PUBLIC_URL written on purpose. localhost is ignored so nobody has to fill it in."""
    text = (raw or "").strip().rstrip("/")
    if not text:
        return None
    parsed = urlparse(text if "://" in text else f"http://{text}")
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    if _is_loopback(parsed.hostname):
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _usable_ip(ip: str) -> ipaddress.IPv4Address | None:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if not isinstance(addr, ipaddress.IPv4Address):
        return None
    if addr.is_loopback or addr.is_link_local or addr.is_unspecified or addr.is_multicast:
        return None
    return addr


def _own_ipv4s() -> list[str]:
    found: list[str] = []
    lan = _lan_ip()
    if lan:
        found.append(lan)
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in found:
                found.append(ip)
    except OSError:
        pass
    return found


def _best_host() -> str | None:
    """This machine's own address. A public address wins, otherwise the network address."""
    addrs = [addr for ip in _own_ipv4s() if (addr := _usable_ip(ip))]
    public = [addr for addr in addrs if not addr.is_private]
    if public:
        return str(public[0])
    fqdn = socket.getfqdn().strip().lower().rstrip(".")
    if fqdn and "." in fqdn and not fqdn.endswith(".local") and not _is_loopback(fqdn):
        try:
            ipaddress.ip_address(fqdn)
        except ValueError:
            return fqdn
    lan = _lan_ip()
    if lan and _usable_ip(lan):
        return lan
    return str(addrs[0]) if addrs else None


def _service_origin() -> str | None:
    """http(s)://<this machine>:<the port the package is listening on>."""
    host = _best_host()
    if not host:
        return None
    developing = settings.environment.lower() == "development" and not settings.survey_bind_port
    if developing:
        return f"http://{host}:8473"
    port = settings.survey_bind_port or 8000
    scheme = "https" if settings.survey_https else "http"
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def public_base_url(request: Request | None = None) -> str:
    """Base URL written into the survey QR.

    An address typed in PUBLIC_URL is used when it is not localhost. Otherwise
    the link is this computer's own address, so putting the package on a server
    fills the QR without anyone typing a host.
    """
    configured = _explicit_public_base(settings.public_url)
    if configured:
        return configured
    origin = _service_origin()
    if origin:
        return origin
    if request is not None:
        host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip()
        if host and not _is_loopback(host) and not any(ch in host for ch in " \r\n/\\"):
            proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "http").split(",")[0].strip()
            if proto not in {"http", "https"}:
                proto = "http"
            return f"{proto}://{host}".rstrip("/")
    return settings.public_url.rstrip("/") or "http://localhost:8000"


def survey_url(token: str, request: Request | None = None) -> str:
    return f"{public_base_url(request)}/s/{token}"


def exam_url(token: str, request: Request | None = None) -> str:
    return f"{public_base_url(request)}/x/{token}"


def survey_qr_svg(token: str, request: Request | None = None) -> str:
    return _qr_svg(survey_url(token, request))


def exam_qr_svg(token: str, request: Request | None = None) -> str:
    return _qr_svg(exam_url(token, request))


def _qr_svg(payload: str) -> str:
    out = io.BytesIO()
    segno.make(payload, error="m").save(out, kind="svg", scale=6, border=2, xmldecl=False, svgns=True)
    return out.getvalue().decode("utf-8")


_AR_WEEKDAYS = ("الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد")
_AR_MONTHS = ("يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر")
_EN_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_EN_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")


def poster_when(day, start, end, lang: str = "ar") -> str:
    """Date and time for the printed poster, in words rather than an ISO stamp."""
    if lang == "en":
        date_line = f"{_EN_WEEKDAYS[day.weekday()]}, {day.day} {_EN_MONTHS[day.month - 1]} {day.year}"
        time_line = f"{start:%H:%M} – {end:%H:%M}"
    else:
        date_line = f"{_AR_WEEKDAYS[day.weekday()]}، {day.day} {_AR_MONTHS[day.month - 1]} {day.year}"
        time_line = f"من {start:%H:%M} إلى {end:%H:%M}"
    return f"{date_line}\n{time_line}"


def render_survey_poster(program: str, title: str, token: str, trainer: str | None, when: str, axis: str | None, lang: str = "ar", request: Request | None = None, headline: str | None = None, caption: str | None = None, link: str | None = None) -> bytes:
    """Black-and-white A4 sheet. The trainer's name is the headline, then the session, then the QR."""
    regular, bold = _register_fonts()
    en = lang == "en"
    black = HexColor("#000000")
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H))
    c.setTitle(trainer or title)
    c.setFillColor(black)
    c.setStrokeColor(black)
    width = PAGE_W - 36 * MM

    y = PAGE_H - 16 * MM

    def lines_of(text: str, font: str, size: float, leading: float) -> None:
        nonlocal y
        c.setFont(font, size)
        for line in _wrap(c, text, font, size, width):
            c.drawCentredString(PAGE_W / 2, y, _shape(line))
            y -= leading

    def label(text: str) -> None:
        lines_of(text, regular, 10, 5 * MM)

    lines_of(program, regular, 14, 6.5 * MM)
    y -= 5 * MM
    lines_of(headline or ("Session feedback survey" if en else "استبيان تقييم جودة الجلسة التدريبية"), bold, 28, 12 * MM)
    y -= 1.2 * MM
    c.setLineWidth(1.35)
    c.line(24 * MM, y, PAGE_W - 24 * MM, y)
    c.setLineWidth(0.35)
    c.line(24 * MM, y - 1.15 * MM, PAGE_W - 24 * MM, y - 1.15 * MM)
    y -= 13 * MM

    if trainer:
        label("Trainer" if en else "المدرب")
        y -= 1.5 * MM
        lines_of(trainer, bold, 16, 7.5 * MM)
        y -= 4 * MM
    label("Session" if en else "عنوان الجلسة")
    y -= 1.5 * MM
    lines_of(title, bold, 16, 7.5 * MM)
    if axis:
        y -= 3.5 * MM
        label("Training axis" if en else "المحور التدريبي")
        y -= 1 * MM
        lines_of(axis, regular, 13, 6.2 * MM)
    if when.strip():
        y -= 3.5 * MM
        label("Date" if en else "التاريخ")
        y -= 1 * MM
        for part in when.splitlines():
            if part.strip():
                lines_of(part.strip(), regular, 13, 6.2 * MM)

    caption = caption or ("Please scan the code to rate this session" if en else "يرجى مسح الرمز لتقييم الجلسة")
    pad = 5 * MM
    bottom = 18 * MM
    room = y - 8 * MM - bottom - 8 * MM - 2 * pad
    qr_size = min(130 * MM, max(68 * MM, room))
    spare = max(0.0, room - qr_size)
    gap = 10 * MM + min(spare * 0.2, 6 * MM)
    qy = y - gap - pad - qr_size
    qx = (PAGE_W - qr_size) / 2
    c.setLineWidth(1)
    c.rect(qx - pad, qy - pad, qr_size + 2 * pad, qr_size + 2 * pad, stroke=1, fill=0)
    _draw_qr(c, link or survey_url(token, request), qx, qy, qr_size)
    c.setFont(regular, 12)
    c.drawCentredString(PAGE_W / 2, qy - pad - 8 * MM, _shape(caption))
    c.save()
    return buf.getvalue()
