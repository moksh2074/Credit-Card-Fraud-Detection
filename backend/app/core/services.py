import asyncio
from app.generator.synthetic.generator import SyntheticTransactionGenerator
from typing import Optional

class ServiceManager:
    _generator: Optional[SyntheticTransactionGenerator] = None
    broadcast_queue: asyncio.Queue = asyncio.Queue()

    @classmethod
    def get_generator(cls) -> SyntheticTransactionGenerator:
        if cls._generator is None:
            # Default initialization
            cls._generator = SyntheticTransactionGenerator(
                tps=1.0, 
                fraud_injection_rate=0.05
            )
        return cls._generator

service_manager = ServiceManager()
