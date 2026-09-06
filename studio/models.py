from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

class Section(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    name: str = Field(min_length=1, max_length=60)
    bars: int = Field(default=8, ge=1, le=32)
    vocal: Literal['A', 'B', 'none'] = 'A'
    instrumental: Literal['A', 'B', 'hybrid'] = 'B'
    start_a: float = Field(default=0, ge=0, le=3600)
    start_b: float = Field(default=0, ge=0, le=3600)
    effect: Literal['normal', 'intro', 'build', 'drop', 'outro'] = 'normal'
    vocal_db: float = Field(default=0, ge=-18, le=12)
    instrumental_db: float = Field(default=0, ge=-18, le=12)
    vocal_offset: float = Field(default=0, ge=-8, le=8)

class RenderRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    track_a: str
    track_b: str
    target_bpm: float | None = Field(default=None, ge=60, le=200)
    bpm_a: float | None = Field(default=None, ge=40, le=240)
    bpm_b: float | None = Field(default=None, ge=40, le=240)
    key_match: bool = True
    pitch_b: float | None = Field(default=None, ge=-6, le=6)
    separation_quality: Literal['auto', 'standard', 'hq'] = 'auto'
    protect_vocal_phrases: bool = True
    preview: bool = False
    sections: list[Section] = Field(min_length=1, max_length=16)

class PairRequest(BaseModel):
    track_a: str
    track_b: str
