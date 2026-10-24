"""Schema dùng chung."""

import re
import unicodedata
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def normalize_class(value: str) -> str:
    match = re.fullmatch(r"(?:lớp\s*[:=]?\s*)?(10|11|12)\s*([a-z])\s*(\d{1,3})", value.strip(), re.I)
    if not match or int(match[3]) == 0:
        raise ValueError("Mã lớp phải có dạng 10C2, 11C3 hoặc 12C9.")
    return f"{match[1]}{match[2].upper()}{int(match[3])}"


def normalize_name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).split()).title()


class Student(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ten: str = Field(min_length=1, max_length=200)
    loai: Literal["P", "K"] | None

    @field_validator("ten")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = normalize_name(value)
        if not value or not any(char.isalpha() for char in value):
            raise ValueError("Tên học sinh không được để trống.")
        return value

    @field_validator("loai", mode="before")
    @classmethod
    def clean_status(cls, value):
        if value in (None, "", "?"):
            return None
        return value.strip().upper() if isinstance(value, str) else value


class ClassRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ten_lop: str
    si_so: int | None = Field(ge=0, le=10000)
    so_vang_khai_bao: int | None = Field(ge=0, le=10000)
    hoc_sinh: list[Student] = Field(max_length=1000)

    @field_validator("ten_lop")
    @classmethod
    def clean_class(cls, value: str) -> str:
        return normalize_class(value)


class GroupCount(BaseModel):
    loai: Literal["P", "K"]
    khai_bao: int | None = Field(ge=0, le=10000)
    thuc_te: int = Field(ge=0, le=1000)


class ParsedClass(ClassRecord):
    raw: str = ""
    reported: bool = True
    overwritten: int = 0
    groups: list[GroupCount] = Field(default_factory=list)
    unrecognized: list[str] = Field(default_factory=list)
    parse_notes: list[str] = Field(default_factory=list)
    excluded_late: list[str] = Field(default_factory=list)
    defaulted_k: list[str] = Field(default_factory=list)


class ParsedReport(BaseModel):
    lop: list[ParsedClass] = Field(default_factory=list, max_length=500)
    unrecognized: list[str] = Field(default_factory=list)


class SessionInfo(BaseModel):
    buoi: Literal["Sáng", "Chiều"]
    ngay: date
    ca: int = Field(ge=1, le=99)


class ExportRequest(SessionInfo):
    text: str = Field(min_length=1, max_length=100000)
    source_data: ParsedReport | None = None

