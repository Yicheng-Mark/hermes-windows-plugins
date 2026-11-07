"""Disk tools: what the storage stack says about every disk and volume."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from . import diskquery, enums

MAX_ROWS = 200
LOW_FREE_PCT = 10.0
CRITICAL_FREE_PCT = 5.0


def _ok(**payload: Any) -> str:
    payload.setdefault("ok", True)
    return json.dumps(payload, ensure_ascii=False, default=str)


def _fail(message: str, **extra: Any) -> str:
    payload: Dict[str, Any] = {"ok": False, "error": message}
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False, default=str)


def _truthy(raw: Any, default: bool) -> bool:
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _clip(text: Any, chars: int = 80) -> Any:
    if not isinstance(text, str):
        return text
    text = " ".join(text.split())
    return text if len(text) <= chars else text[:chars] + "…"


def _gib(size: Any) -> Any:
    try:
        return round(int(size) / (1024 ** 3), 1)
    except (TypeError, ValueError):
        return None


def _pct(free: Any, capacity: Any) -> Any:
    try:
        free, capacity = int(free), int(capacity)
    except (TypeError, ValueError):
        return None
    if capacity <= 0:
        return None
    return round(free * 100.0 / capacity, 1)


def _free_verdict(pct: Any) -> str:
    if pct is None:
        return "unknown"
    if pct < CRITICAL_FREE_PCT:
        return "critical"
    if pct < LOW_FREE_PCT:
        return "low"
    return "fine"


def _letter_of(row: Dict[str, Any]) -> Any:
    return row.get("letter") or None


def _norm(text: Any) -> str:
    return str(text or "").strip().rstrip(":").casefold()


def _health_reading(health: str, operational: List[str]) -> str:
    if health == "healthy":
        return "the disk reports healthy"
    if health in {"warning", "unhealthy"}:
        return f"the disk reports {health} - back up before anything else"
    # 'unknown': the writing machine's healthy NVMe answers exactly this
    if operational == ["ok"]:
        return ("the storage stack's health word is unknown - it answers exactly this on a "
                "healthy NVMe; OperationalStatus, ok here, is the other signal")
    return ("the storage stack's health word is unknown - it answers exactly this on a healthy "
            f"NVMe; OperationalStatus here says {', '.join(operational) or 'nothing'}")


def _build(raw: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
    """The raw five listings joined into disk rows and volume rows.

    Every listing is normalized here, not only in the query layer: PowerShell
    unwraps a one-element array into a bare object, and any path that hands this
    function raw storage answers may carry either shape.
    """
    physical_rows = diskquery._rows(raw.get("physical"))
    disk_rows = diskquery._rows(raw.get("disks"))
    part_rows = diskquery._rows(raw.get("parts"))
    volume_rows = diskquery._rows(raw.get("volumes"))
    netconns = {_norm(n.get("local")): n for n in diskquery._rows(raw.get("netconns"))}

    disks: List[Dict[str, Any]] = []
    for phys in physical_rows:
        number = None
        try:
            number = int(str(phys.get("id")))
        except (TypeError, ValueError):
            number = None
        meta = next((d for d in disk_rows
                     if str(d.get("number")) == str(phys.get("id"))), {})
        operational = enums.decode_list(enums.OPERATIONAL_STATUS, phys.get("op"))
        media = enums.decode(enums.MEDIA_TYPE, phys.get("media"))
        spindle = phys.get("spindle")
        disks.append({
            "kind": "disk",
            "disk": number if number is not None else phys.get("id"),
            "model": _clip(phys.get("model")),
            "serial": phys.get("serial"),
            "media": media,
            "bus": enums.decode(enums.BUS_TYPE, phys.get("bus")),
            "size_bytes": phys.get("size"),
            "size_gib": _gib(phys.get("size")),
            "health": enums.decode(enums.HEALTH_STATUS, phys.get("health")),
            "operational": operational,
            "spindle_rpm": spindle if media != "ssd" else (0 if not spindle else spindle),
            "partition_style": enums.decode(enums.PARTITION_STYLE, meta.get("style")),
            "boot": bool(meta.get("boot")),
            "system": bool(meta.get("system")),
            "readonly": bool(meta.get("readonly")),
            "partitions": meta.get("partitions"),
            "free_extent_bytes": meta.get("free_extent"),
        })

    # a volume hangs off the disk whose partition carries its letter
    letter_to_disk: Dict[str, int] = {}
    for part in part_rows:
        letter = _norm(part.get("letter"))
        if letter:
            try:
                letter_to_disk[letter] = int(part.get("disk"))
            except (TypeError, ValueError):
                pass

    volumes: List[Dict[str, Any]] = []
    for vol in volume_rows:
        letter = _letter_of(vol)
        norm = _norm(letter)
        net = netconns.get(norm)
        capacity, free = vol.get("capacity"), vol.get("free")
        pct = _pct(free, capacity)
        volumes.append({
            "kind": "volume",
            "drive": letter,
            "label": _clip(vol.get("label"), 60),
            "filesystem": vol.get("fs"),
            "capacity_bytes": capacity,
            "size_gib": _gib(capacity),
            "free_bytes": free,
            "free_gib": _gib(free),
            "free_pct": pct,
            "free_verdict": _free_verdict(pct),
            "drive_type": enums.decode(enums.DRIVE_TYPE, vol.get("drive_type")),
            "disk": letter_to_disk.get(norm),
            "unc": net.get("remote") if net else None,
            "hidden": not bool(letter),
        })

    return {"disks": disks, "volumes": volumes}


def _matches(row: Dict[str, Any], query: str) -> bool:
    hay = " ".join(str(row.get(key) or "") for key in
                   ("model", "serial", "drive", "label", "filesystem"))
    return query.casefold() in hay.casefold()


def win_disk_table(args: Dict[str, Any], **kwargs: Any) -> str:
    """Every disk and every volume the storage stack reports, one table."""
    args = args or {}
    kind = str(args.get("kind") or "all").strip().lower()
    if kind not in {"disk", "volume", "all"}:
        kind = "all"
    include_letterless = _truthy(args.get("include_letterless"), False)
    query = str(args.get("query") or "").strip()

    try:
        model = _build(diskquery.query())
    except diskquery.PowerShellError as exc:
        return _fail(str(exc), code="disks_unavailable")

    disks, volumes = model["disks"], model["volumes"]
    hidden = [v for v in volumes if v["hidden"]]
    shown_volumes = [v for v in volumes if include_letterless or not v["hidden"]]

    rows: List[Dict[str, Any]] = []
    if kind in {"disk", "all"}:
        rows.extend(disks)
    if kind in {"volume", "all"}:
        rows.extend(shown_volumes)
    if query:
        rows = [row for row in rows if _matches(row, query)]
    total = len(rows)
    listed = rows[:MAX_ROWS]

    notes: List[str] = [
        f"{len(disks)} disk(s) and {len(shown_volumes)} volume(s) listed, "
        f"{len(disks)} disk(s) and {len(volumes)} volume(s) known"
    ]
    if hidden and not include_letterless:
        labels = ", ".join(str(v.get("label") or "unlabeled") for v in hidden[:6])
        notes.append(f"{len(hidden)} volume(s) without a drive letter hidden "
                     f"({labels}); include_letterless=true shows them")
    if total > len(listed):
        notes.append(f"stopped at {MAX_ROWS} rows; narrow the query")
    if not listed:
        notes.append("nothing matched; drop the query or the kind filter")

    for disk in disks:
        if disk["health"] in {"warning", "unhealthy"}:
            notes.append(f"disk {disk['disk']} ({disk['model']}) reports {disk['health']} - "
                         "back up before anything else; win_disk_detail reads it in full")
        elif disk["health"] == "unknown":
            notes.append(f"disk {disk['disk']} ({disk['model']}) health reads unknown - the "
                         "storage stack answers exactly this on a healthy NVMe; OperationalStatus "
                         "is the other signal")
    tight = [f"{v['drive']} {v['free_pct']}% free" for v in shown_volumes
             if v["drive"] and isinstance(v["free_pct"], (int, float))
             and v["free_pct"] < LOW_FREE_PCT]
    if tight:
        notes.append("low free space: " + "; ".join(tight))

    return _ok(rows=listed, notes=notes)


def _resolve(target: str, disks: List[Dict[str, Any]], volumes: List[Dict[str, Any]]) -> tuple:
    """target -> (row, candidates note). Tiers, most exact first."""
    norm = _norm(target)
    stripped = target.strip().casefold().lstrip("disk").strip()

    if norm:
        for vol in volumes:
            if _norm(vol.get("drive")) == norm:
                return vol, None

    if stripped.isdigit():
        for disk in disks:
            if str(disk.get("disk")) == stripped:
                return disk, None

    serial_hits = [d for d in disks if norm and norm in str(d.get("serial") or "").casefold()]
    if len(serial_hits) == 1:
        return serial_hits[0], None

    model_hits = [d for d in disks if norm and norm in str(d.get("model") or "").casefold()]
    if model_hits:
        note = None
        if len(model_hits) > 1:
            note = (f"{len(model_hits)} disks match '{target}'; reading disk "
                    f"{model_hits[0]['disk']} - name it by serial or number for the others "
                    f"({', '.join(str(d['disk']) for d in model_hits[1:])})")
        return model_hits[0], note

    label_hits = [v for v in volumes if norm and norm in str(v.get("label") or "").casefold()]
    if label_hits:
        note = None
        if len(label_hits) > 1:
            name = label_hits[0].get("drive") or label_hits[0].get("label")
            note = (f"{len(label_hits)} volumes match '{target}'; reading {name} - "
                    "name it by drive letter for the others")
        return label_hits[0], note

    return None, None


def _volume_detail(vol: Dict[str, Any], disks: List[Dict[str, Any]],
                   notes: List[str]) -> Dict[str, Any]:
    owner = next((d for d in disks if str(d.get("disk")) == str(vol.get("disk"))), None)
    pct = vol.get("free_pct")
    verdict = vol.get("free_verdict")
    sentence = {
        "critical": f"{pct}% free - critical, the volume is about to fill",
        "low": f"{pct}% free - low, room for days not months",
        "fine": f"{pct}% free - fine",
        "unknown": "free space unknown - the volume did not report a capacity",
    }.get(verdict, str(verdict))
    if vol.get("drive_type") == "network":
        notes.append("a network volume: the capacity is the server's answer, and the UNC path "
                     f"({vol.get('unc') or 'not in the mapped-drive table'}) is where it lives")
    if owner:
        notes.append(f"the owning disk (disk {owner['disk']}, {owner['model']}) reports health "
                     f"{owner['health']}; win_disk_detail reads it by model")
    return {
        "matched": "volume",
        "volume": vol,
        "free_space": sentence,
    }


def _disk_detail(disk: Dict[str, Any], parts: List[Dict[str, Any]],
                 volumes: List[Dict[str, Any]], notes: List[str]) -> Dict[str, Any]:
    number = str(disk.get("disk"))
    own = sorted((p for p in parts if str(p.get("disk")) == number),
                 key=lambda p: int(p.get("partition") or 0))
    layout = []
    for part in own:
        layout.append({
            "partition": part.get("partition"),
            "type": enums.partition_kind(part.get("gpt"), part.get("mbr")),
            "size_bytes": part.get("size"),
            "size_gib": _gib(part.get("size")),
            "offset_bytes": part.get("offset"),
            "letter": (part.get("letter") + ":") if part.get("letter") else None,
            "boot": bool(part.get("boot")),
            "system": bool(part.get("system")),
        })
    own_volumes = [v for v in volumes if str(v.get("disk")) == number]
    volumes_block = []
    for vol in own_volumes:
        volumes_block.append({
            "drive": vol.get("drive"),
            "label": vol.get("label"),
            "filesystem": vol.get("filesystem"),
            "size_gib": vol.get("size_gib"),
            "free_gib": vol.get("free_gib"),
            "free_pct": vol.get("free_pct"),
            "free_verdict": vol.get("free_verdict"),
        })
    if disk.get("spindle_rpm") in (0, None) and disk.get("media") == "ssd":
        notes.append("no spindle - solid state")
    elif disk.get("spindle_rpm"):
        notes.append(f"spindle {disk['spindle_rpm']} rpm")
    if disk.get("free_extent_bytes"):
        notes.append(f"largest contiguous free extent {_gib(disk['free_extent_bytes'])} GiB - "
                     "the room another partition could take in one piece")
    return {
        "matched": "disk",
        "disk": disk,
        "health": _health_reading(disk.get("health", "unknown"), disk.get("operational", [])),
        "partitions": layout,
        "volumes": volumes_block,
    }


def win_disk_detail(args: Dict[str, Any], **kwargs: Any) -> str:
    """One disk or one volume in full, by letter, label, model, serial or number."""
    args = args or {}
    target = str(args.get("target") or "").strip()
    if not target:
        return _fail("a target is required: a drive letter ('C:'), a volume label, a disk "
                     "model, a serial number, or a disk number ('0', 'disk 0')", code="usage")

    try:
        raw = diskquery.query()
    except diskquery.PowerShellError as exc:
        return _fail(str(exc), code="disks_unavailable")
    model = _build(raw)

    row, note = _resolve(target, model["disks"], model["volumes"])
    if row is None:
        return _fail(f"nothing matched '{target}'; targets are a drive letter ('C:' or 'C'), "
                     "a volume label, a disk model, a serial number, or a disk number",
                     code="nothing_matched")

    notes: List[str] = []
    if note:
        notes.append(note)
    if row["kind"] == "volume":
        payload = _volume_detail(row, model["disks"], notes)
    else:
        payload = _disk_detail(row, diskquery._rows(raw.get("parts")),
                               model["volumes"], notes)
    return _ok(**payload, notes=notes)


__all__ = ["win_disk_detail", "win_disk_table"]
