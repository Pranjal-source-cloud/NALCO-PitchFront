"""
Core pitch-front business logic:
    - circular (wrap-around) section calculation for both furnaces
    - FW / section data-structure builders
    - form validation

This module contains NO Streamlit code so it can be unit-tested in isolation.
"""

from config import FURNACES, FIRE_TO_FURNACE, FW_COUNT, INPUT_SECTION_ROLES


def get_furnace_for_fire(fire):
    """Fire-1/2/3 -> ABF-II, Fire-4/5 -> ABF-III."""
    return FIRE_TO_FURNACE.get(fire)


def get_total_sections(furnace):
    return FURNACES[furnace]["total_sections"]


def circular_previous_section(section, total_sections):
    """
    Return the section immediately preceding `section` in a circular furnace.
    Section 1's previous section wraps around to `total_sections`.
    """
    prev = section - 1
    if prev < 1:
        prev += total_sections
    return prev


def calculate_profile_sections(exhaust_ramp_section, furnace):
    """
    Given the exhaust ramp section and furnace, return the three physical
    section numbers used for the pitch-front profile:

        section_1 -> exhaust ramp section        (top of profile, no P input)
        section_2 -> first preceding section      (circular -1)
        section_3 -> second preceding section      (circular -2)
    """
    total_sections = get_total_sections(furnace)
    section_1 = exhaust_ramp_section
    section_2 = circular_previous_section(section_1, total_sections)
    section_3 = circular_previous_section(section_2, total_sections)
    return {"section_1": section_1, "section_2": section_2, "section_3": section_3}


def validate_exhaust_ramp_section(exhaust_ramp_section, furnace):
    total_sections = get_total_sections(furnace)
    if exhaust_ramp_section is None:
        return False, "Exhaust Ramp Section is required."
    if not (1 <= exhaust_ramp_section <= total_sections):
        return False, f"Exhaust Ramp Section must be between 1 and {total_sections} for {furnace}."
    return True, ""


def build_empty_pitch_front_state():
    """
    Build an empty in-memory structure for FW1..FW9 pitch-front entries.
    Returns: { fw_number: { 'section_2': None, 'section_3': None } }
    """
    return {fw: {role: None for role in INPUT_SECTION_ROLES} for fw in range(1, FW_COUNT + 1)}


def validate_observation_form(shift_incharge, fire, furnace, exhaust_ramp_section, pitch_front_state):
    """
    Validate the full new-observation form before locking.
    Returns (is_valid: bool, errors: list[str]).
    """
    errors = []

    if not fire:
        errors.append("Fire must be selected.")

    if not furnace:
        errors.append("Furnace could not be determined automatically — select a valid Fire.")

    if not shift_incharge or not shift_incharge.strip():
        errors.append("Shift Incharge is required.")

    if furnace:
        ok, msg = validate_exhaust_ramp_section(exhaust_ramp_section, furnace)
        if not ok:
            errors.append(msg)

    if pitch_front_state:
        for fw in range(1, FW_COUNT + 1):
            fw_data = pitch_front_state.get(fw, {})
            # A field is "filled" once the user has made an intentional choice —
            # a real P1-P4 hole OR an explicit 'No Pitch Front'. Only an
            # unanswered/placeholder field (None) counts as blank.
            value_2 = fw_data.get("section_2")
            value_3 = fw_data.get("section_3")
            if value_2 is None and value_3 is None:
                errors.append(
                    f"FW{fw}: Enter pitch-front information in at least one of the two preceding sections."
                )
            # If at least one of the two is filled, this FW is valid — the
            # other field is allowed to remain blank.

    return (len(errors) == 0), errors
