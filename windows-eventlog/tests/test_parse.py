"""Parsing tests: XML shapes, time formats, exception codes."""

from hermes_windows_eventlog.parse import (
    app_name,
    decode_exception,
    describe_exception,
    format_time,
    parse_event,
    parse_time,
    payload_text,
    truncate,
)

APP_ERROR = """<Event xmlns='http://schemas.microsoft.com/win/2004/08/events/event'><System><Provider Name='Application Error'/><EventID>1000</EventID><Level>2</Level><TimeCreated SystemTime='2026-10-20T00:14:27.6104775Z'/><EventRecordID>12345</EventRecordID><Execution ProcessID='4242' ThreadID='1'/><Channel>Application</Channel><Computer>PC</Computer></System><EventData><Data Name='Application Name'>hermes.exe</Data><Data Name='Application Version'>0.22.2</Data><Data Name='Application Path'>C:\\Program Files\\Hermes\\hermes.exe</Data><Data Name='Faulting module name'>kernelbase.dll</Data><Data Name='Faulting module path'>C:\\Windows\\System32\\kernelbase.dll</Data><Data Name='Exception code'>0xc0000005</Data><Data Name='Fault offset'>0x0000000000012345</Data><Data Name='Report Id'>11111111-2222-3333-4444-555555555555</Data></EventData></Event>"""

WER_EVENT = """<Event xmlns='http://schemas.microsoft.com/win/2004/08/events/event'><System><Provider Name='Windows Error Reporting'/><EventID>1001</EventID><Level>4</Level><TimeCreated SystemTime='2026-10-20T03:00:08.0130020Z'/><Execution ProcessID='900' ThreadID='1'/><Channel>Application</Channel></System><EventData><Data Name='Bucket'>2219081324101382324</Data><Data Name='EventName'>RADAR_PRE_LEAK_64</Data><Data Name='P1'>ego.exe</Data><Data Name='P2'>0.6.0.12</Data><Data Name='ReportId'>51a7d1d4-a23d-4599-93b5-ea257210ac15</Data></EventData></Event>"""

POSITIONAL_EVENT = """<Event xmlns='http://schemas.microsoft.com/win/2004/08/events/event'><System><Provider Name='CodexSandboxService.OpenAI.Codex'/><EventID>1000</EventID><Level>4</Level><TimeCreated SystemTime='2026-10-20T00:14:27.6104775Z'/><Channel>Application</Channel></System><EventData><Data>The Codex sandbox service is running.</Data></EventData></Event>"""


def test_parse_event_reads_system_and_named_data():
    record = parse_event(APP_ERROR)
    assert record["event_id"] == 1000
    assert record["level"] == "error"
    assert record["provider"] == "Application Error"
    assert record["channel"] == "Application"
    assert record["process_id"] == 4242
    assert record["data"]["Application Name"] == "hermes.exe"
    assert record["data"]["Exception code"] == "0xc0000005"
    assert app_name(record) == "hermes.exe"


def test_parse_event_keeps_positional_data():
    record = parse_event(POSITIONAL_EVENT)
    assert record["data_list"] == ["The Codex sandbox service is running."]
    assert record["data"]["#0"] == "The Codex sandbox service is running."
    assert record["level"] == "information"


def test_payload_text_includes_list_and_named_values():
    text = payload_text(parse_event(POSITIONAL_EVENT))
    assert "Codex sandbox service" in text


def test_parse_time_accepts_seven_digit_fractions():
    moment = parse_time("2026-10-20T03:00:08.0130020Z")
    assert moment is not None
    assert format_time(moment) == "2026-10-20T03:00:08.013002Z"


def test_parse_time_rejects_garbage():
    assert parse_time("not-a-time") is None
    assert parse_time("") is None
    assert parse_time(None) is None


def test_parse_time_accepts_offset_forms():
    assert format_time(parse_time("2026-10-20T11:00:08.5+08:00")) == "2026-10-20T03:00:08.500000Z"
    assert format_time(parse_time("2026-10-20T03:00:08Z")) == "2026-10-20T03:00:08.000000Z"


def test_decode_exception_names_the_common_codes():
    assert decode_exception("0xc0000005") == "ACCESS_VIOLATION"
    assert decode_exception("c00000fd") == "STACK_OVERFLOW"
    assert decode_exception("0xE0434352") == "CLR_EXCEPTION"
    assert decode_exception("0xdeadbeef") is None
    assert decode_exception(None) is None


def test_describe_exception_formats_known_and_unknown_codes():
    assert describe_exception("0xc0000005") == "0xC0000005 (ACCESS_VIOLATION)"
    assert describe_exception("0x1234") == "0x1234"
    assert describe_exception("") is None


def test_truncate_marks_cut_text():
    assert truncate("abc", 10) == "abc"
    shortened = truncate("x" * 20, 5)
    assert shortened.startswith("xxxxx") and "truncated" in shortened
    assert truncate(7) == 7


def test_wer_event_shape():
    record = parse_event(WER_EVENT)
    assert record["event_id"] == 1001
    assert record["data"]["EventName"] == "RADAR_PRE_LEAK_64"
    assert app_name(record) == "ego.exe"
