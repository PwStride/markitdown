import sys
from typing import BinaryIO, Any, List, Optional
from datetime import datetime, date, timedelta

from .._base_converter import DocumentConverter, DocumentConverterResult
from .._stream_info import StreamInfo
from .._mono_format import h1, h2, h3, bullet, meta

ACCEPTED_MIME_TYPE_PREFIXES = [
    "text/calendar",
]
ACCEPTED_FILE_EXTENSIONS = [".ics"]

MISSING_DEPENDENCY_MESSAGE = """
Install the required dependency with: pip install icalendar

Alternatively, install markitdown with the ics option: pip install 'markitdown[ics]'
"""

_dependency_exc_info = None
try:
    import icalendar
except ImportError:
    _dependency_exc_info = sys.exc_info()


def _format_datetime(dt_value) -> str:
    """Format a datetime, date, or timedelta value to a human-readable string."""
    if isinstance(dt_value, datetime):
        return dt_value.strftime("%B %d, %Y, %I:%M %p")
    elif isinstance(dt_value, date):
        return dt_value.strftime("%B %d, %Y")
    elif isinstance(dt_value, timedelta):
        total_seconds = int(dt_value.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes = remainder // 60
        parts = []
        if hours:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes:
            parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
        return ", ".join(parts) if parts else "0 minutes"
    return str(dt_value)


def _get_text(event, prop: str) -> Optional[str]:
    """Safely extract a text property from an event."""
    val = event.get(prop)
    if val is None:
        return None
    if isinstance(val, list):
        val = val[0]
    return str(val).strip() or None


def _get_attendees(event) -> List[str]:
    """Extract and format attendee list from an event."""
    attendees = event.get("ATTENDEE")
    if attendees is None:
        return []
    if not isinstance(attendees, list):
        attendees = [attendees]

    results = []
    for attendee in attendees:
        cal_address = str(attendee).replace("mailto:", "")
        params = attendee.params if hasattr(attendee, "params") else {}
        cn = params.get("CN", "")
        role = params.get("ROLE", "")
        partstat = params.get("PARTSTAT", "")

        display = cn if cn else cal_address
        meta_parts = []
        if role and role.upper() != "REQ-PARTICIPANT":
            meta_parts.append(role.replace("-", " ").title())
        if partstat:
            status_map = {
                "ACCEPTED": "Accepted",
                "DECLINED": "Declined",
                "TENTATIVE": "Tentative",
                "NEEDS-ACTION": "Pending",
            }
            meta_parts.append(status_map.get(partstat.upper(), partstat.title()))

        if meta_parts:
            display = f"{display} ({', '.join(meta_parts)})"

        results.append(display)
    return results


def _event_sort_key(event) -> tuple:
    """Generate a sort key for ordering events by start date/time."""
    dtstart = event.get("DTSTART")
    if dtstart is None:
        return (datetime.min,)
    dt = dtstart.dt
    if isinstance(dt, date) and not isinstance(dt, datetime):
        dt = datetime(dt.year, dt.month, dt.day)
    return (dt,)


class IcsConverter(DocumentConverter):
    """
    Converts ICS (iCalendar) files to Markdown.
    Events are organized by date, with sections for title, date/time,
    location, organizer, attendees, and description.
    """

    def __init__(self):
        super().__init__()

    def accepts(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,
    ) -> bool:
        mimetype = (stream_info.mimetype or "").lower()
        extension = (stream_info.extension or "").lower()
        if extension in ACCEPTED_FILE_EXTENSIONS:
            return True
        for prefix in ACCEPTED_MIME_TYPE_PREFIXES:
            if mimetype.startswith(prefix):
                return True
        return False

    def convert(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,
    ) -> DocumentConverterResult:
        if _dependency_exc_info is not None:
            raise ImportError(MISSING_DEPENDENCY_MESSAGE) from _dependency_exc_info[1].with_traceback(
                _dependency_exc_info[2]
            )

        content = file_stream.read()
        cal = icalendar.Calendar.from_ical(content)

        # Collect all VEVENT components
        events = [
            component
            for component in cal.walk()
            if component.name == "VEVENT"
        ]

        # Sort events by start date
        events.sort(key=_event_sort_key)

        # Extract calendar-level title if available
        cal_title = _get_text(cal, "X-WR-CALNAME")

        sections: List[str] = []

        if cal_title:
            sections.append(h1(cal_title))

        for event in events:
            event_sections: List[str] = []

            # Title (SUMMARY)
            title = _get_text(event, "SUMMARY")
            if title:
                event_sections.append(h2(title))

            # Date / Time
            date_lines: List[str] = []
            dtstart = event.get("DTSTART")
            dtend = event.get("DTEND")
            duration = event.get("DURATION")

            if dtstart:
                date_lines.append(meta("Start", _format_datetime(dtstart.dt)))
            if dtend:
                date_lines.append(meta("End", _format_datetime(dtend.dt)))
            if duration:
                date_lines.append(meta("Duration", _format_datetime(duration.dt)))

            if date_lines:
                event_sections.append(h3("Date and Time"))
                event_sections.append("".join(date_lines))

            # Location
            location = _get_text(event, "LOCATION")
            event_sections.append(h3("Location"))
            event_sections.append(f"{location}\n" if location else "No location specified\n")

            # Organizer
            organizer = event.get("ORGANIZER")
            if organizer:
                org_address = str(organizer).replace("mailto:", "")
                org_params = organizer.params if hasattr(organizer, "params") else {}
                org_cn = org_params.get("CN", "")
                org_display = f"{org_cn} <{org_address}>" if org_cn else org_address

                event_sections.append(h3("Organizer"))
                event_sections.append(f"{org_display}\n")

            # Attendees
            attendees = _get_attendees(event)
            if attendees:
                event_sections.append(h3("Attendees"))
                event_sections.append(
                    "".join(bullet(a) for a in attendees)
                )

            # Description
            description = _get_text(event, "DESCRIPTION")
            if description:
                event_sections.append(h3("Description"))
                event_sections.append(f"{description}\n")

            if event_sections:
                sections.append("\n".join(event_sections))

        markdown = "\n".join(sections)
        return DocumentConverterResult(markdown=markdown, title=cal_title)
