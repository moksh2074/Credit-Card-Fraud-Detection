import asyncio
import json
import logging
from typing import Set

logger = logging.getLogger(__name__)

class Broadcaster:
    def __init__(self):
        self.subscribers: Set[asyncio.Queue] = set()

    async def subscribe(self) -> asyncio.Queue:
        queue = asyncio.Queue()
        self.subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue):
        self.subscribers.remove(queue)

    async def broadcast(self, message: dict):
        if not self.subscribers:
            return
        
        json_msg = json.dumps(message)
        # Create a list to avoid "Set changed size during iteration" errors
        for queue in list(self.subscribers):
            try:
                await queue.put(json_msg)
            except Exception as e:
                logger.error(f"Error broadcasting to queue: {e}")

broadcaster = Broadcaster()
