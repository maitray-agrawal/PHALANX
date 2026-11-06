"""Configurable PayPal API Mock/Stub Server for Chaos and Performance Engineering.

Supports runtime mode switching:
- normal: Instant 201 SUCCESS responses for OAuth, Payouts, and Orders.
- delay: Configurable delay (default 2s) to simulate high-latency PayPal rails.
- 5xx: HTTP 500 Internal Server Error simulating PayPal upstream gateway failure.
- timeout: Sleeps beyond client timeout (15s) simulating dropped connections.
"""

import argparse
import asyncio
from typing import Literal

import uvicorn
from fastapi import FastAPI, Request, Response
from pydantic import BaseModel

app = FastAPI(title="PayPal Chaos Stub")

StubMode = Literal["normal", "delay", "5xx", "timeout"]

current_mode: StubMode = "normal"
delay_duration: float = 2.0


class ModeConfig(BaseModel):
    mode: StubMode
    delay_seconds: float = 2.0


@app.get("/mock/mode")
def get_mode():
    return {"mode": current_mode, "delay_seconds": delay_duration}


@app.post("/mock/mode")
def set_mode(config: ModeConfig):
    global current_mode, delay_duration
    current_mode = config.mode
    delay_duration = config.delay_seconds
    return {"status": "ok", "mode": current_mode, "delay_seconds": delay_duration}


@app.post("/v1/oauth2/token")
async def oauth2_token():
    if current_mode == "5xx":
        return Response(
            content='{"error":"server_error","error_description":"PayPal OAuth down"}',
            status_code=500,
            media_type="application/json",
        )
    if current_mode == "delay":
        await asyncio.sleep(delay_duration)

    return {
        "scope": "https://uri.paypal.com/services/payments/payouts",
        "access_token": "mock_paypal_access_token_phalanx",
        "token_type": "Bearer",
        "app_id": "APP-MOCK-PHALANX",
        "expires_in": 3600,
    }


@app.post("/v1/payments/payouts")
async def create_payout(request: Request):
    if current_mode == "5xx":
        return Response(
            content='{"name":"INTERNAL_SERVICE_ERROR","message":"An internal error occurred"}',
            status_code=500,
            media_type="application/json",
        )
    if current_mode == "timeout":
        await asyncio.sleep(15.0)
    elif current_mode == "delay":
        await asyncio.sleep(delay_duration)

    body = await request.json()
    batch_header = body.get("sender_batch_header", {})
    batch_id = batch_header.get("sender_batch_id", "payout_mock_12345")

    return Response(
        content=f'{{"batch_header":{{"payout_batch_id":"{batch_id}","batch_status":"SUCCESS"}}}}',
        status_code=201,
        media_type="application/json",
    )


@app.post("/v2/checkout/orders")
async def create_order():
    if current_mode == "5xx":
        return Response(
            content='{"name":"INTERNAL_SERVICE_ERROR","message":"Order creation failed"}',
            status_code=500,
            media_type="application/json",
        )
    if current_mode == "timeout":
        await asyncio.sleep(15.0)
    elif current_mode == "delay":
        await asyncio.sleep(delay_duration)

    return {
        "id": "MOCK-ORDER-999",
        "status": "APPROVED",
        "intent": "CAPTURE",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run PayPal Chaos Stub")
    parser.add_argument("--port", type=int, default=8089)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument(
        "--mode",
        type=str,
        default="normal",
        choices=["normal", "delay", "5xx", "timeout"],
    )
    args = parser.parse_args()

    current_mode = args.mode
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
