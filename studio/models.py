from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator

class Section(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    name: str = Field(min_length=1, max_length=60)
    bars: int = Field(default=8, ge=1, le=32)
    vocal: Literal['A', 'B', 'C', 'D', 'none'] = 'A'
    instrumental: Literal['A', 'B', 'C', 'D', 'hybrid'] = 'B'
    start_a: float = Field(default=0, ge=0, le=3600)
    start_b: float = Field(default=0, ge=0, le=3600)
    start_c: float = Field(default=0, ge=0, le=3600)
    start_d: float = Field(default=0, ge=0, le=3600)
    backing_stem: Literal['instrumental', 'drums', 'bass', 'other', 'piano', 'electric_guitar', 'acoustic_guitar', 'synthesizer', 'strings', 'wind'] = 'instrumental'
    effect: Literal['normal', 'intro', 'build', 'drop', 'outro'] = 'normal'
    vocal_db: float = Field(default=0, ge=-18, le=12)
    instrumental_db: float = Field(default=0, ge=-18, le=12)
    vocal_offset: float = Field(default=0, ge=-8, le=8)

class RenderRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    track_a: str
    track_b: str
    track_c: str | None = None
    track_d: str | None = None

    def track_ids(self):
        return {name: getattr(self, "track_"+name.lower()) for name in "ABCD" if getattr(self, "track_"+name.lower())}
    target_bpm: float | None = Field(default=None, ge=60, le=200)
    bpm_a: float | None = Field(default=None, ge=40, le=240)
    bpm_b: float | None = Field(default=None, ge=40, le=240)
    bpm_c: float | None = Field(default=None, ge=40, le=240)
    bpm_d: float | None = Field(default=None, ge=40, le=240)
    pitch_c: float | None = Field(default=None, ge=-6, le=6)
    pitch_d: float | None = Field(default=None, ge=-6, le=6)
    key_match: bool = True
    pitch_b: float | None = Field(default=None, ge=-6, le=6)
    separation_quality: Literal['auto', 'standard', 'hq', 'lalal', 'lalal_full'] = 'auto'
    protect_vocal_phrases: bool = True
    preview: bool = False
    sections: list[Section] = Field(min_length=1, max_length=16)

    @model_validator(mode='after')
    def sources_exist(self):
        available = self.track_ids()
        for section in self.sections:
            used = {section.vocal, section.instrumental} - {'none', 'hybrid'}
            if not used <= available.keys():
                raise ValueError('Für jede verwendete Spur muss ein Song ausgewählt sein.')
        return self

class PairRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    track_a: str
    track_b: str
    track_c: str | None = None
    track_d: str | None = None

    def track_ids(self):
        return {name: getattr(self, "track_"+name.lower()) for name in "ABCD" if getattr(self, "track_"+name.lower())}
    target_bpm: float | None = Field(default=None, ge=60, le=200)
    use_score: bool = True

    separation_quality: Literal['auto', 'standard', 'hq', 'lalal', 'lalal_full'] = 'auto'

class LalalQuoteRequest(PairRequest):
    mode: Literal['vocals', 'all'] = 'vocals'

class LalalKeyRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=1024, repr=False)

class LalalStartRequest(BaseModel):
    quote_id: str
    consent: Literal[True]
