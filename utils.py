"""
Utility helpers: stable widget keys, formatting, and export helpers.
"""

import io
import pandas as pd


def make_widget_key(*parts):
    """Build a stable, collision-free Streamlit widget key from any parts."""
    safe_parts = [str(p).replace(" ", "_") for p in parts]
    return "wkey__" + "__".join(safe_parts)


def format_date(dt):
    """e.g. datetime(2026, 8, 16, 14, 30) -> '16 Aug 2026'"""
    if dt is None:
        return ""
    return dt.strftime("%d %b %Y")


def format_time(dt):
    """e.g. datetime(2026, 8, 16, 14, 30) -> '14:30'"""
    if dt is None:
        return ""
    return dt.strftime("%H:%M")


def format_datetime(dt):
    """e.g. datetime(2026, 8, 16, 14, 30) -> '16 Aug 2026, 14:30'"""
    if dt is None:
        return ""
    return f"{format_date(dt)}, {format_time(dt)}"


def observations_to_dataframe(observations):
    """
    Flatten a list of Observation ORM objects (with relationships loaded)
    into a pandas DataFrame suitable for history display / export.
    """
    rows = []
    for obs in observations:
        row = {
            "ID": obs.id,
            "Fire": obs.fire,
            "Furnace": obs.furnace,
            "Shift Incharge": obs.shift_incharge,
            "Observation Date/Time": obs.observation_datetime,
            "Exhaust Ramp Section": f"S{obs.exhaust_ramp_section}",
            "1st Preceding Section": f"S{obs.section_2}",
            "2nd Preceding Section": f"S{obs.section_3}",
            "Remark Type": obs.remark_type or "",
            "Remark": obs.remark or "",
            "Status": obs.status,
            "Locked At": obs.locked_at,
        }

        entry_map = {(e.fw_number, e.section_role): e for e in obs.pitch_front_entries}
        reading_map = {r.fw_number: r for r in obs.process_readings}

        for fw in range(1, 10):
            e2 = entry_map.get((fw, "section_2"))
            e3 = entry_map.get((fw, "section_3"))
            row[f"FW{fw} - S{obs.section_2}"] = (
                "No Pitch Front" if (e2 and e2.is_no_pitch_front) else (e2.pitch_position if e2 else "")
            )
            row[f"FW{fw} - S{obs.section_3}"] = (
                "No Pitch Front" if (e3 and e3.is_no_pitch_front) else (e3.pitch_position if e3 else "")
            )
            reading = reading_map.get(fw)
            row[f"FW{fw} Temperature"] = reading.fw_temperature if reading else None
            row[f"FW{fw} Draft"] = reading.draft if reading else None

        rows.append(row)

    return pd.DataFrame(rows)


def dataframe_to_csv_bytes(df):
    return df.to_csv(index=False).encode("utf-8")


def dataframe_to_excel_bytes(df):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Observations")
    return buffer.getvalue()
