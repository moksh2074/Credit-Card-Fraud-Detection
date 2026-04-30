from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import asyncio
import json
from typing import Any
from app.core.broadcaster import broadcaster

router = APIRouter()

async def event_generator():
    queue = await broadcaster.subscribe()
    try:
        while True:
            try:
                # Wait for a message with a 15s timeout for keep-alive
                msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                yield f"data: {msg}\n\n"
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'status': 'keep-alive'})}\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        broadcaster.unsubscribe(queue)

@router.get("/transactions")
async def stream_transactions() -> Any:
    """
    Server-Sent Events endpoint to push real-time transaction scores to the dashboard.
    """
    return StreamingResponse(event_generator(), media_type="text/event-stream")
