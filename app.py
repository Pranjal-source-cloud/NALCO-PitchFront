"""
NALCO Anode Baking Furnace — Pitch Front Digital Tracking System

Run with:
    streamlit run app.py
or, if the streamlit command is not on PATH (common on Windows):
    python -m streamlit run app.py
"""

import datetime

import streamlit as st
import pandas as pd
from sqlalchemy import func

import config
import pitchfront
from database import init_db, get_db_session, get_backend_label
from models import Observation, PitchFrontEntry, ProcessReading
from graph import build_profile_figure
from utils import (
    make_widget_key, observations_to_dataframe, dataframe_to_csv_bytes,
    dataframe_to_excel_bytes, format_date, format_time, format_datetime,
)

# ---------------------------------------------------------------------------
# App bootstrap
# ---------------------------------------------------------------------------

st.set_page_config(page_title=config.APP_TITLE, layout="wide", page_icon="🔥")
init_db()

if "pf_form_nonce" not in st.session_state:
    st.session_state["pf_form_nonce"] = 0


# ---------------------------------------------------------------------------
# Shared data-access helpers
# ---------------------------------------------------------------------------

def fetch_latest_locked_observation(session, fire):
    return (
        session.query(Observation)
        .filter(Observation.fire == fire, Observation.status == config.STATUS_LOCKED)
        .order_by(Observation.locked_at.desc(), Observation.id.desc())
        .first()
    )


def fetch_history(session, fire=None, furnace=None, shift_incharge=None,
                   date_from=None, date_to=None):
    q = session.query(Observation).filter(Observation.status == config.STATUS_LOCKED)
    if fire and fire != "All":
        q = q.filter(Observation.fire == fire)
    if furnace and furnace != "All":
        q = q.filter(Observation.furnace == furnace)
    if shift_incharge:
        q = q.filter(Observation.shift_incharge.ilike(f"%{shift_incharge}%"))
    if date_from:
        q = q.filter(Observation.observation_datetime >= datetime.datetime.combine(date_from, datetime.time.min))
    if date_to:
        q = q.filter(Observation.observation_datetime <= datetime.datetime.combine(date_to, datetime.time.max))
    return q.order_by(Observation.observation_datetime.desc()).all()


def observation_to_graph_inputs(obs):
    sections = {
        "section_1": obs.exhaust_ramp_section,
        "section_2": obs.section_2,
        "section_3": obs.section_3,
    }
    fw_pitch_data = {fw: {} for fw in range(1, config.FW_COUNT + 1)}
    for entry in obs.pitch_front_entries:
        fw_pitch_data.setdefault(entry.fw_number, {})
        fw_pitch_data[entry.fw_number][entry.section_role] = (
            "NO_PF" if entry.is_no_pitch_front else entry.pitch_position
        )
    fw_process_data = {}
    for reading in obs.process_readings:
        fw_process_data[reading.fw_number] = {
            "fw_temperature": reading.fw_temperature,
            "draft": reading.draft,
        }
    return sections, fw_pitch_data, fw_process_data


# ---------------------------------------------------------------------------
# PAGE: New Observation
# ---------------------------------------------------------------------------

def page_new_observation():
    st.header("📝 New Pitch Front Observation")

    nonce = st.session_state["pf_form_nonce"]

    top_col1, top_col2, top_col3 = st.columns([1, 1, 1])
    with top_col1:
        fire = st.selectbox("Fire", config.ALL_FIRES, key=make_widget_key("fire", nonce))
    furnace = pitchfront.get_furnace_for_fire(fire)
    with top_col2:
        st.text_input("Furnace (automatic)", value=furnace or "", disabled=True,
                       key=make_widget_key("furnace_display", nonce, fire))
    with top_col3:
        total_sections = pitchfront.get_total_sections(furnace) if furnace else 1
        exhaust_ramp_section = st.number_input(
            "Exhaust Ramp Section", min_value=1, max_value=total_sections, step=1, value=1,
            key=make_widget_key("exhaust_section", nonce, furnace),
        )

    col_a, col_b, col_c = st.columns([1, 1, 1])
    with col_a:
        shift_incharge = st.text_input("Shift Incharge", key=make_widget_key("shift_incharge", nonce))
    with col_b:
        obs_date = st.date_input("Observation Date", value=datetime.date.today(),
                                  key=make_widget_key("obs_date", nonce))
    with col_c:
        obs_time = st.time_input("Observation Time", value=datetime.datetime.now().time(),
                                  key=make_widget_key("obs_time", nonce))

    sections = pitchfront.calculate_profile_sections(exhaust_ramp_section, furnace)

    st.markdown(
        f"**Profile sections for this observation:** "
        f"S{sections['section_1']} (Exhaust Ramp, top) → "
        f"S{sections['section_2']} (1st preceding) → "
        f"S{sections['section_3']} (2nd preceding)"
    )

    st.divider()
    st.subheader("Pitch Front — FW1 to FW9")
    st.caption(
        f"No pitch-front entry is needed for S{sections['section_1']} — it is the exhaust ramp "
        f"section and is shown automatically. Enter the hole (or 'No Pitch Front') for "
        f"S{sections['section_2']} and S{sections['section_3']} only."
    )

    fw_pitch_data = {}
    fw_process_data = {}

    for fw in range(1, config.FW_COUNT + 1):
        with st.expander(f"FW{fw}", expanded=(fw <= 2)):
            st.markdown(f"**S{sections['section_1']}** — exhaust ramp section (no entry required)")

            c1, c2 = st.columns(2)
            with c1:
                val2 = st.selectbox(
                    f"S{sections['section_2']} — pitch front",
                    config.PITCH_FRONT_CHOICES,
                    key=make_widget_key("pf", nonce, fire, "fw", fw, "section_2"),
                )
            with c2:
                val3 = st.selectbox(
                    f"S{sections['section_3']} — pitch front",
                    config.PITCH_FRONT_CHOICES,
                    key=make_widget_key("pf", nonce, fire, "fw", fw, "section_3"),
                )

            fw_pitch_data[fw] = {
                "section_2": None if val2 == config.PLACEHOLDER_CHOICE else (
                    "NO_PF" if val2 == config.NO_PITCH_FRONT else val2
                ),
                "section_3": None if val3 == config.PLACEHOLDER_CHOICE else (
                    "NO_PF" if val3 == config.NO_PITCH_FRONT else val3
                ),
            }

            c3, c4 = st.columns(2)
            with c3:
                temp = st.number_input(
                    f"FW{fw} Temperature (°C)", value=0.0, step=1.0, format="%.1f",
                    key=make_widget_key("temp", nonce, fire, "fw", fw),
                )
            with c4:
                draft = st.number_input(
                    f"FW{fw} Draft", value=0.0, step=0.1, format="%.2f",
                    key=make_widget_key("draft", nonce, fire, "fw", fw),
                )
            fw_process_data[fw] = {"fw_temperature": temp, "draft": draft}

    st.divider()
    st.subheader("Remarks")
    rc1, rc2 = st.columns([1, 2])
    with rc1:
        remark_type = st.selectbox("Remark Type", config.REMARK_TYPES,
                                    key=make_widget_key("remark_type", nonce))
    with rc2:
        remark = st.text_area("Remark", key=make_widget_key("remark", nonce))

    st.divider()
    st.subheader("Live Preview")
    preview_fw_pitch = {
        fw: {
            "section_2": data["section_2"] if data["section_2"] else None,
            "section_3": data["section_3"] if data["section_3"] else None,
        }
        for fw, data in fw_pitch_data.items()
    }
    fig = build_profile_figure(
        fire=fire, sections=sections, fw_pitch_data=preview_fw_pitch,
        fw_process_data=fw_process_data, shift_incharge=shift_incharge,
        observation_datetime=f"{obs_date} {obs_time}",
    )
    st.plotly_chart(fig, use_container_width=True, key=make_widget_key("preview_chart", nonce, fire))

    st.divider()
    lock_col, reset_col = st.columns([1, 1])

    with lock_col:
        if st.button("🔒 Validate & Lock Pitch Front Observation", type="primary",
                      key=make_widget_key("lock_btn", nonce)):
            is_valid, errors = pitchfront.validate_observation_form(
                shift_incharge, fire, furnace, exhaust_ramp_section, fw_pitch_data
            )
            if not is_valid:
                st.error("Please fix the following before locking:")
                for e in errors:
                    st.write(f"- {e}")
            else:
                observation_datetime = datetime.datetime.combine(obs_date, obs_time)
                now = datetime.datetime.utcnow()

                with get_db_session() as session:
                    obs = Observation(
                        fire=fire,
                        furnace=furnace,
                        shift_incharge=shift_incharge.strip(),
                        observation_datetime=observation_datetime,
                        exhaust_ramp_section=sections["section_1"],
                        section_2=sections["section_2"],
                        section_3=sections["section_3"],
                        remark_type=remark_type,
                        remark=remark.strip() if remark else None,
                        status=config.STATUS_LOCKED,
                        created_at=now,
                        locked_at=now,
                    )
                    session.add(obs)
                    session.flush()  # obtain obs.id

                    for fw in range(1, config.FW_COUNT + 1):
                        for role in config.INPUT_SECTION_ROLES:
                            value = fw_pitch_data[fw][role]
                            is_no_pf = (value == "NO_PF")
                            session.add(PitchFrontEntry(
                                observation_id=obs.id,
                                fw_number=fw,
                                section_role=role,
                                section_number=sections[role],
                                pitch_position=None if is_no_pf else value,
                                is_no_pitch_front=is_no_pf,
                            ))
                        session.add(ProcessReading(
                            observation_id=obs.id,
                            fw_number=fw,
                            fw_temperature=fw_process_data[fw]["fw_temperature"],
                            draft=fw_process_data[fw]["draft"],
                        ))

                st.success(f"Observation locked for {fire} at {observation_datetime}. "
                           f"This is now the Current Profile for {fire}.")
                st.session_state["pf_form_nonce"] += 1
                st.rerun()

    with reset_col:
        if st.button("↺ Clear Form", key=make_widget_key("reset_btn", nonce)):
            st.session_state["pf_form_nonce"] += 1
            st.rerun()


# ---------------------------------------------------------------------------
# PAGE: Current Profile
# ---------------------------------------------------------------------------

def page_current_profile():
    st.header("📊 Current Pitch Front Profile")

    fire = st.selectbox("Select Fire", config.ALL_FIRES, key="current_profile_fire")

    with get_db_session() as session:
        obs = fetch_latest_locked_observation(session, fire)
        if obs is None:
            st.info(f"No locked observations yet for {fire}.")
            return

        sections, fw_pitch_data, fw_process_data = observation_to_graph_inputs(obs)

        meta_cols = st.columns(5)
        meta_cols[0].metric("Furnace", obs.furnace)
        meta_cols[1].metric("Shift Incharge", obs.shift_incharge)
        meta_cols[2].metric("Observation Date", format_date(obs.observation_datetime))
        meta_cols[3].metric("Observation Time", format_time(obs.observation_datetime))
        meta_cols[4].metric("Exhaust Ramp Section", f"S{obs.exhaust_ramp_section}")

        fig = build_profile_figure(
            fire=fire, sections=sections, fw_pitch_data=fw_pitch_data,
            fw_process_data=fw_process_data, shift_incharge=obs.shift_incharge,
            observation_datetime=format_datetime(obs.observation_datetime),
        )
        st.plotly_chart(fig, use_container_width=True, key=f"current_profile_chart_{obs.id}")

        if obs.remark or obs.remark_type:
            st.info(f"**Remark Type:** {obs.remark_type or '—'}  \n**Remark:** {obs.remark or '—'}")

        with st.expander("FW Temperature / Draft (process readings)"):
            rows = []
            for reading in sorted(obs.process_readings, key=lambda r: r.fw_number):
                rows.append({
                    "FW": f"FW{reading.fw_number}",
                    "Temperature (°C)": reading.fw_temperature,
                    "Draft": reading.draft,
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# PAGE: History
# ---------------------------------------------------------------------------

def page_history():
    st.header("🗂️ History")

    f1, f2, f3, f4, f5 = st.columns(5)
    with f1:
        fire_filter = st.selectbox("Fire", ["All"] + config.ALL_FIRES, key="hist_fire")
    with f2:
        furnace_filter = st.selectbox("Furnace", ["All"] + list(config.FURNACES.keys()), key="hist_furnace")
    with f3:
        shift_incharge_filter = st.text_input("Shift Incharge contains", key="hist_shift")
    with f4:
        date_from = st.date_input("From date", value=None, key="hist_from")
    with f5:
        date_to = st.date_input("To date", value=None, key="hist_to")

    with get_db_session() as session:
        records = fetch_history(
            session, fire=fire_filter, furnace=furnace_filter,
            shift_incharge=shift_incharge_filter or None,
            date_from=date_from if date_from else None,
            date_to=date_to if date_to else None,
        )

        if not records:
            st.info("No locked observations match these filters.")
            return

        st.caption(f"{len(records)} locked observation(s) found. All historical records are retained — "
                   f"nothing is ever overwritten when a new observation is locked.")

        df = observations_to_dataframe(records)
        display_cols = ["ID", "Fire", "Furnace", "Shift Incharge", "Observation Date/Time",
                         "Exhaust Ramp Section", "1st Preceding Section", "2nd Preceding Section",
                         "Remark Type", "Remark", "Status"]
        st.dataframe(df[display_cols], use_container_width=True, hide_index=True)

        exp_col1, exp_col2 = st.columns(2)
        with exp_col1:
            st.download_button("⬇️ Export CSV", data=dataframe_to_csv_bytes(df),
                                file_name="pitch_front_history.csv", mime="text/csv")
        with exp_col2:
            st.download_button("⬇️ Export Excel", data=dataframe_to_excel_bytes(df),
                                file_name="pitch_front_history.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        st.divider()
        st.subheader("View a specific record's profile")
        options = {f"#{r.id} — {r.fire} — {format_datetime(r.observation_datetime)} — "
                   f"{r.shift_incharge}": r.id for r in records}
        selected_label = st.selectbox("Select observation", list(options.keys()), key="hist_select")
        selected_id = options[selected_label]
        selected_obs = next(r for r in records if r.id == selected_id)

        sections, fw_pitch_data, fw_process_data = observation_to_graph_inputs(selected_obs)
        fig = build_profile_figure(
            fire=selected_obs.fire, sections=sections, fw_pitch_data=fw_pitch_data,
            fw_process_data=fw_process_data, shift_incharge=selected_obs.shift_incharge,
            observation_datetime=format_datetime(selected_obs.observation_datetime),
        )
        st.plotly_chart(fig, use_container_width=True, key=f"hist_chart_{selected_id}")


# ---------------------------------------------------------------------------
# PAGE: Database Summary
# ---------------------------------------------------------------------------

def page_db_summary():
    st.header("🗄️ Database Summary")
    st.caption(f"Backend: {get_backend_label()}")

    with get_db_session() as session:
        total_obs = session.query(func.count(Observation.id)).scalar() or 0
        locked_obs = (
            session.query(func.count(Observation.id))
            .filter(Observation.status == config.STATUS_LOCKED).scalar() or 0
        )

        c1, c2 = st.columns(2)
        c1.metric("Total Observations", total_obs)
        c2.metric("Locked Observations", locked_obs)

        st.subheader("Observations by Fire")
        by_fire = (
            session.query(Observation.fire, func.count(Observation.id))
            .filter(Observation.status == config.STATUS_LOCKED)
            .group_by(Observation.fire).all()
        )
        if by_fire:
            st.dataframe(pd.DataFrame(by_fire, columns=["Fire", "Locked Observations"]),
                         use_container_width=True, hide_index=True)
        else:
            st.write("No locked observations yet.")

        st.subheader("Observations by Furnace")
        by_furnace = (
            session.query(Observation.furnace, func.count(Observation.id))
            .filter(Observation.status == config.STATUS_LOCKED)
            .group_by(Observation.furnace).all()
        )
        if by_furnace:
            st.dataframe(pd.DataFrame(by_furnace, columns=["Furnace", "Locked Observations"]),
                         use_container_width=True, hide_index=True)
        else:
            st.write("No locked observations yet.")

        st.subheader("Latest Observation")
        latest = (
            session.query(Observation)
            .filter(Observation.status == config.STATUS_LOCKED)
            .order_by(Observation.locked_at.desc()).first()
        )
        if latest:
            lc1, lc2, lc3, lc4, lc5 = st.columns(5)
            lc1.metric("Fire", latest.fire)
            lc2.metric("Furnace", latest.furnace)
            lc3.metric("Shift Incharge", latest.shift_incharge)
            lc4.metric("Date", format_date(latest.observation_datetime))
            lc5.metric("Time", format_time(latest.observation_datetime))
        else:
            st.write("No locked observations yet.")


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

def main():
    st.sidebar.title(config.APP_TITLE)
    st.sidebar.caption(f"DB backend: {get_backend_label()}")
    page = st.sidebar.radio(
        "Navigate",
        ["Current Profile", "New Observation", "History", "Database Summary"],
        key="nav_page",
    )

    if page == "New Observation":
        page_new_observation()
    elif page == "Current Profile":
        page_current_profile()
    elif page == "History":
        page_history()
    elif page == "Database Summary":
        page_db_summary()


if __name__ == "__main__":
    main()
