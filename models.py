"""
SQLAlchemy ORM models.

Normalized schema (see README.md for rationale):

    observations         one row per locked/draft pitch-front observation
    pitch_front_entries  one row per FW per input section (section_2 / section_3)
    process_readings     one row per FW (FW temperature + draft)

Nothing is ever overwritten or deleted by normal application flow: locking
an observation simply inserts a new row, so full history is preserved.
"""

import datetime

from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, ForeignKey, Float, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Observation(Base):
    __tablename__ = "observations"

    id = Column(Integer, primary_key=True, autoincrement=True)

    fire = Column(String(20), nullable=False, index=True)
    furnace = Column(String(20), nullable=False, index=True)
    shift_incharge = Column(String(120), nullable=False)

    observation_datetime = Column(DateTime, nullable=False)

    exhaust_ramp_section = Column(Integer, nullable=False)   # section_1
    section_2 = Column(Integer, nullable=False)              # first preceding section
    section_3 = Column(Integer, nullable=False)              # second preceding section

    remark_type = Column(String(40), nullable=True)
    remark = Column(Text, nullable=True)

    status = Column(String(10), nullable=False, default="DRAFT", index=True)

    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    locked_at = Column(DateTime, nullable=True, index=True)

    pitch_front_entries = relationship(
        "PitchFrontEntry",
        back_populates="observation",
        cascade="all, delete-orphan",
        order_by="PitchFrontEntry.fw_number",
    )
    process_readings = relationship(
        "ProcessReading",
        back_populates="observation",
        cascade="all, delete-orphan",
        order_by="ProcessReading.fw_number",
    )


class PitchFrontEntry(Base):
    __tablename__ = "pitch_front_entries"
    __table_args__ = (
        UniqueConstraint("observation_id", "fw_number", "section_role", name="uq_entry_fw_role"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    observation_id = Column(Integer, ForeignKey("observations.id"), nullable=False, index=True)

    fw_number = Column(Integer, nullable=False)           # 1-9
    section_role = Column(String(20), nullable=False)     # 'section_2' or 'section_3'
    section_number = Column(Integer, nullable=False)      # actual physical section number

    pitch_position = Column(String(5), nullable=True)     # 'P1'..'P4' or None
    is_no_pitch_front = Column(Boolean, nullable=False, default=False)

    observation = relationship("Observation", back_populates="pitch_front_entries")


class ProcessReading(Base):
    __tablename__ = "process_readings"
    __table_args__ = (
        UniqueConstraint("observation_id", "fw_number", name="uq_reading_fw"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    observation_id = Column(Integer, ForeignKey("observations.id"), nullable=False, index=True)

    fw_number = Column(Integer, nullable=False)  # 1-9
    fw_temperature = Column(Float, nullable=True)
    draft = Column(Float, nullable=True)

    observation = relationship("Observation", back_populates="process_readings")
