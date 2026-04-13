from pydantic import BaseModel, Field
from typing import Optional

class PredictRequest(BaseModel):
    ticker: str = Field(..., json_schema_extra={"example": "^NSEI"})
    rsi_14:        float = Field(..., ge=0,   le=100)
    bb_width:      float = Field(..., ge=0)
    volatility_20: float = Field(..., ge=0)
    momentum_10:   float = Field(...)
    adx_14:        float = Field(..., ge=0)
    volume_ratio:  float = Field(..., ge=0)

class PredictResponse(BaseModel):
    ticker:        str
    regime:        str
    confidence:    float
    probabilities: dict

class HealthResponse(BaseModel):
    status:        str
    model_loaded:  bool
    version:       str