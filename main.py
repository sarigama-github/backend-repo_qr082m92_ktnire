import os
from datetime import date, datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional

from database import db, create_document, get_documents

app = FastAPI(title="Subscriptions Hub API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SubscriptionIn(BaseModel):
    name: str = Field(..., description="Service name, e.g., Netflix")
    amount: float = Field(..., ge=0, description="Billing amount")
    currency: str = Field("USD", min_length=3, max_length=3)
    billing_cycle: str = Field("monthly", description="monthly|annual|weekly")
    next_charge_date: Optional[date] = None
    payment_method: Optional[str] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None
    active: bool = True


@app.get("/")
def read_root():
    return {"message": "Subscriptions Hub Backend Running"}


@app.get("/test")
def test_database():
    """Verify DB connectivity and list collections"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": [],
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = (
                os.getenv("DATABASE_NAME") or getattr(db, "name", "") or "Unknown"
            )
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["connection_status"] = "Connected"
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:120]}"

    return response


@app.post("/api/subscriptions")
def create_subscription(payload: SubscriptionIn):
    """Create a manual subscription record."""
    try:
        inserted_id = create_document("subscription", payload.model_dump())
        return {"id": inserted_id, "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/subscriptions")
def list_subscriptions():
    """List all subscriptions."""
    try:
        docs = get_documents("subscription", {}, limit=None)
        # convert ObjectId and dates to strings
        for d in docs:
            if "_id" in d:
                d["id"] = str(d.pop("_id"))
            # serialize datetime/date fields
            for k, v in list(d.items()):
                if isinstance(v, (datetime, date)):
                    d[k] = v.isoformat()
        return {"items": docs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/insights/summary")
def monthly_summary():
    """Simple monthly cost summary and duplicate detection (by name)."""
    try:
        docs = get_documents("subscription", {}, limit=None)
        total_monthly = 0.0
        by_service = {}
        duplicates = []
        for d in docs:
            amount = float(d.get("amount", 0))
            cycle = d.get("billing_cycle", "monthly")
            name = (d.get("name") or "").strip().lower()
            if not name:
                continue
            # Normalize monthly cost
            if cycle == "annual":
                monthly = amount / 12.0
            elif cycle == "weekly":
                monthly = amount * 52.0 / 12.0
            else:
                monthly = amount
            total_monthly += monthly
            by_service.setdefault(name, 0)
            by_service[name] += monthly
        # duplicates: any service name seen more than once
        name_counts = {}
        for d in docs:
            n = (d.get("name") or "").strip().lower()
            if not n:
                continue
            name_counts[n] = name_counts.get(n, 0) + 1
        duplicates = [name for name, c in name_counts.items() if c > 1]
        return {
            "total_monthly": round(total_monthly, 2),
            "services": {k: round(v, 2) for k, v in by_service.items()},
            "duplicates": duplicates,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
