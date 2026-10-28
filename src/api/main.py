"""FastAPI service for the NHS waiting-list project.

Run from the project root:
    pip install fastapi uvicorn pydantic
    py -m uvicorn main:app --app-dir src/api --reload
Then open http://127.0.0.1:8000/docs for the interactive documentation.

Endpoints
  GET  /health      is the service up, which model, which months
  POST /predict     forecast next month's % within 18 weeks for one trust + specialty, with drivers
  GET  /services    search trust/specialty combinations
  GET  /watchlist   services ranked by patients waiting 12-18 weeks
  GET  /summary     plain-English briefing (template, optional LLM)

Aggregate NHS statistics only. Nothing here concerns individual patients.
"""
import sys
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

SRC = Path(__file__).resolve().parents[1]
for sub in ("api", "app", "genai"):
    sys.path.insert(0, str(SRC / sub))

from dashboard_logic import service_table  # noqa: E402
from predictor import NotEnoughData, Predictor, ServiceNotFound  # noqa: E402
from weekly_summary import generate, make_anthropic_llm  # noqa: E402

app = FastAPI(title="NHS Waiting List Optimizer API", version="0.4",
              description="Illustrative student capstone built on NHS England RTT statistics. "
                          "Not an official NHS system; not for clinical decisions.")
# Open CORS is fine for a local demo. Restrict allow_origins to your frontend's address when deployed.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@lru_cache
def get_predictor() -> Predictor:
    return Predictor.from_files()


class PredictRequest(BaseModel):
    trust_code: str = Field(..., min_length=2, max_length=10, examples=["RA7"], description="NHS trust code")
    specialty_code: str = Field(..., min_length=2, max_length=10, examples=["C_100"],
                                description="Treatment function code, e.g. C_100 General Surgery")
    month: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}$", examples=["2026-08"],
                                 description="Month to forecast from (YYYY-MM). Default: latest month.")


class Driver(BaseModel):
    feature: str
    label: str
    value: Optional[float] = None
    typical_value: Optional[float] = None
    unit: str = ""
    effect_pp: float = Field(..., description="How far this input moves the forecast versus a typical value (percentage points)")


class ModelInfo(BaseModel):
    name: str
    test_mae_pp: Optional[float] = None
    same_as_last_month_mae_pp: Optional[float] = None
    test_months: Optional[list[str]] = None


class PredictResponse(BaseModel):
    trust_code: str
    trust_name: str
    specialty_code: str
    specialty: str
    icb_name: Optional[str] = None
    month: str
    forecast_month: str
    waiting_list: int
    current_pct_within_18w: float
    forecast_pct_within_18w: float
    forecast_change_pp: float
    patients_waiting_12_18w: int
    patients_to_treat_for_92: int
    drivers: list[Driver]
    model: ModelInfo
    notice: str


class HealthResponse(BaseModel):
    status: str
    model: str
    months: list[str]
    rows: int


ERRORS = {404: {"description": "Unknown trust, specialty or month"},
          422: {"description": "Service too small to forecast, or missing the previous month"},
          503: {"description": "Data or model files not found"}}


def _month(m: Optional[str]):
    return None if m is None else pd.Timestamp(m + "-01")


def _call(fn, *a, **k):
    try:
        return fn(*a, **k)
    except ServiceNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except NotEnoughData as e:
        raise HTTPException(status_code=422, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=f"Missing file: {e.filename}. Build the data and train the model first.")


@app.get("/", include_in_schema=False)
def root():
    """Send visitors (and the host's port check) to the interactive docs instead of a 404."""
    return RedirectResponse(url="/docs")


@app.get("/health", response_model=HealthResponse)
def health():
    p = _call(get_predictor)
    return {"status": "ok", "model": p.meta.get("model", "unknown"),
            "months": [f"{p.months[0]:%Y-%m}", f"{p.latest:%Y-%m}"], "rows": int(len(p.df))}


@app.post("/predict", response_model=PredictResponse, responses=ERRORS)
def predict(req: PredictRequest):
    p = _call(get_predictor)
    return _call(p.predict, req.trust_code.strip(), req.specialty_code.strip(), _month(req.month))


@app.get("/services")
def services(q: str = Query("", max_length=60, description="Part of a trust name, specialty, or a trust code"),
             month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
             limit: int = Query(20, ge=1, le=100)):
    p = _call(get_predictor)
    return _call(p.search_services, q, _month(month), limit)


@app.get("/watchlist")
def watchlist(month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
              tier: Optional[str] = Query(None, pattern="^(High|Medium|Low)$"),
              exclude_other: bool = True, min_list: int = Query(100, ge=0, le=5000),
              limit: int = Query(25, ge=1, le=200)):
    p = _call(get_predictor)
    m = _call(p._month, _month(month))
    cells = service_table(p.df, m, min_list, exclude_other)
    if tier:
        cells = cells[cells["risk_tier"] == tier]
    cells = cells.sort_values("at_risk_12_18", ascending=False).head(limit)
    return {"month": f"{m:%Y-%m}", "count": int(len(cells)), "services": [
        {"trust_code": r.trust_code, "trust_name": r.trust_name, "specialty_code": r.specialty_code,
         "specialty": r.specialty, "waiting_list": int(r.waiting_list),
         "pct_within_18w": round(float(r.pct_within_18w) * 100, 2), "patients_waiting_12_18w": int(r.at_risk_12_18),
         "share_12_18w_pct": round(float(r.at_risk_share) * 100, 2),
         "patients_to_treat_for_92": int(r.treat_to_reach_92), "risk_tier": r.risk_tier}
        for r in cells.itertuples()]}


@app.get("/summary")
def summary(month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
            use_llm: bool = Query(False, description="Use an LLM for wording (needs ANTHROPIC_API_KEY); falls back to the template")):
    p = _call(get_predictor)
    m = _call(p._month, _month(month))
    out = generate(p.df, m, make_anthropic_llm() if use_llm else None)
    return {"text": out["text"], "source": out["source"], "issues": out["issues"]}