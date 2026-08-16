"""
Pitch-front profile graph construction (Plotly).

This chart intentionally does NOT use a plain numerical Y-axis of section
numbers. Instead it reproduces the physical NALCO Pitch-Front Profile Sheet:

    TOP band    -> Exhaust Ramp Section    (label only — no input, no trace)
    MIDDLE band -> 1st preceding section   (trace)
    BOTTOM band -> 2nd preceding section   (trace)

Within every band the four holes are stacked P4 (top) .. P1 (bottom), exactly
as on the paper profile sheet.

The X-axis is always FW1..FW9 in that fixed order, and there is exactly ONE
pitch-front point per FW — wherever that FW's actual pitch front currently
sits (1st preceding section or 2nd preceding section, whichever one holds a
real P1-P4 value for that FW). A single line connects consecutive FWs
strictly in FW order (FW1->FW2->FW3->...->FW9), regardless of whether
consecutive FWs happen to sit in the same section or different sections.
The section number is NEVER used as a condition for whether a line segment
is drawn — only FW adjacency matters.

If a FW has no pitch front at all for either preceding section (both left
blank / both explicitly marked 'No Pitch Front'), that FW contributes no
point — Plotly's gap handling means the line simply does not draw across
that missing FW; it does not fabricate a point, and it does not silently
skip past it to join the previous valid FW directly to the next valid FW's
non-adjacent neighbour (the gap is exactly one FW wide, matching reality).

If, unusually, both the 1st and 2nd preceding sections have a real value for
the same FW, the 1st preceding section's value is used (it is physically
closer to the exhaust ramp / current flame position).
"""

import plotly.graph_objects as go

from config import FW_COUNT

P_VALUE = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}

# Vertical "base" for each band. A value X in a band occupies base+1 .. base+4.
BAND_BASE = {
    "section_1": 12,  # top    -> 13-16 (exhaust ramp, label only)
    "section_2": 6,   # middle -> 7-10  (1st preceding section, trace)
    "section_3": 0,   # bottom -> 1-4   (2nd preceding section, trace)
}

BAND_COLOR = {
    "section_2": "#1f5fa6",   # blue
    "section_3": "#b6261e",   # red
}

BAND_DISPLAY_NAME = {
    "section_2": "1st Preceding Section",
    "section_3": "2nd Preceding Section",
}


def _band_y(role, p_label):
    return BAND_BASE[role] + P_VALUE[p_label]


def build_profile_figure(fire, sections, fw_pitch_data, fw_process_data=None,
                          shift_incharge=None, observation_datetime=None):
    """
    fire: str, e.g. "Fire-1"
    sections: dict {'section_1': int, 'section_2': int, 'section_3': int}
              (physical section numbers; section_1 = exhaust ramp, at TOP)
    fw_pitch_data: { fw_number(int): { 'section_2': 'P1'|'P2'|'P3'|'P4'|'NO_PF'|None,
                                        'section_3': same } }
    fw_process_data: { fw_number(int): {'fw_temperature': float|None, 'draft': float|None} }
    shift_incharge, observation_datetime: optional strings shown in hover text.
    """
    fw_process_data = fw_process_data or {}
    fig = go.Figure()

    fw_x = list(range(1, FW_COUNT + 1))

    # ---- Build exactly ONE point per FW, then draw ONE connected line ----
    # For each FW, pick whichever preceding section actually holds a real
    # P1-P4 value (1st preceding section takes priority if both are set).
    xs, ys, hover, text_labels, marker_colors = [], [], [], [], []

    for fw in fw_x:
        fw_entry = fw_pitch_data.get(fw) or {}
        val_2 = fw_entry.get("section_2")
        val_3 = fw_entry.get("section_3")
        proc = fw_process_data.get(fw, {}) or {}

        chosen_role, chosen_value = None, None
        if val_2 not in (None, "NO_PF"):
            chosen_role, chosen_value = "section_2", val_2
        elif val_3 not in (None, "NO_PF"):
            chosen_role, chosen_value = "section_3", val_3

        if chosen_role is None:
            # No real pitch-front value for this FW at all -> genuine gap.
            # Preserve the FW's x-position; plot no point, fabricate nothing.
            xs.append(fw)
            ys.append(None)
            hover.append(None)
            text_labels.append("")
            marker_colors.append(BAND_COLOR["section_2"])
            continue

        section_number = sections[chosen_role]
        y = _band_y(chosen_role, chosen_value)
        xs.append(fw)
        ys.append(y)
        text_labels.append(chosen_value)
        marker_colors.append(BAND_COLOR[chosen_role])

        temp = proc.get("fw_temperature")
        draft = proc.get("draft")
        hover_lines = [
            f"Fire: {fire}",
            f"FW: FW{fw}",
            f"Section: S{section_number}",
            f"Pitch Front: {chosen_value}",
        ]
        if shift_incharge:
            hover_lines.append(f"Shift Incharge: {shift_incharge}")
        if temp is not None:
            hover_lines.append(f"FW Temperature: {temp}")
        if draft is not None:
            hover_lines.append(f"Draft: {draft}")
        if observation_datetime:
            hover_lines.append(f"Time: {observation_datetime}")
        hover.append("<br>".join(hover_lines))

    fig.add_trace(go.Scatter(
        x=xs, y=ys,
        mode="lines+markers+text",
        name="Pitch Front Profile",
        line=dict(color="#2f2f2f", width=3),
        marker=dict(size=11, color=marker_colors, line=dict(color="#2f2f2f", width=1)),
        text=text_labels,
        textposition="top center",
        textfont=dict(size=11, color="#2f2f2f"),
        hovertext=hover,
        hoverinfo="text",
        connectgaps=False,   # a genuine gap (no pitch front that FW) breaks the line;
                             # it never fabricates a point and never jumps straight over it.
    ))

    # Small legend proxies so the marker-color meaning (which section) is still visible,
    # even though there is now only one connected line.
    for role in ("section_2", "section_3"):
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers",
            marker=dict(size=11, color=BAND_COLOR[role]),
            name=f"S{sections[role]} ({BAND_DISPLAY_NAME[role]})",
            showlegend=True, hoverinfo="skip",
        ))

    # ---- Grid / band structure (shapes + annotations) ---------------------
    shapes = []
    annotations = []
    x_min, x_max = 0.5, FW_COUNT + 0.5

    for role in ("section_1", "section_2", "section_3"):
        base = BAND_BASE[role]
        section_number = sections[role]

        for p_label, p_val in P_VALUE.items():
            y = base + p_val
            shapes.append(dict(
                type="line", x0=x_min, x1=x_max, y0=y, y1=y,
                line=dict(color="rgba(150,150,150,0.35)", width=1, dash="dot"),
                layer="below",
            ))

        header = f"S{section_number}"
        if role == "section_1":
            header += "  (Exhaust Ramp — current, no entry)"
        annotations.append(dict(
            x=x_min, y=base + 5.0, xref="x", yref="y",
            text=f"<b>{header}</b>",
            showarrow=False, xanchor="left", font=dict(size=13, color="#1a1a1a"),
        ))

        if role != "section_3":  # separator below every band except the last
            shapes.append(dict(
                type="line", x0=x_min, x1=x_max, y0=base - 0.6, y1=base - 0.6,
                line=dict(color="black", width=1.5),
            ))

    tickvals, ticktext = [], []
    for role in ("section_1", "section_2", "section_3"):
        base = BAND_BASE[role]
        for p_label in ("P4", "P3", "P2", "P1"):
            tickvals.append(base + P_VALUE[p_label])
            ticktext.append(p_label)

    fig.update_layout(
        title=f"Pitch Front Profile — {fire}",
        xaxis=dict(
            title="FW",
            tickmode="array",
            tickvals=fw_x,
            ticktext=[f"FW{i}" for i in fw_x],
            range=[x_min, x_max],
            showgrid=False,
            zeroline=False,
        ),
        yaxis=dict(
            title="",
            tickmode="array",
            tickvals=tickvals,
            ticktext=ticktext,
            range=[-1, 18],
            showgrid=False,
            zeroline=False,
        ),
        shapes=shapes,
        annotations=annotations,
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1),
        plot_bgcolor="white",
        height=680,
        margin=dict(l=70, r=30, t=90, b=60),
    )

    return fig
