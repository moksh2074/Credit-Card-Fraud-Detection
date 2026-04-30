from typing import Any
import logging

from fastapi import APIRouter, HTTPException, Query

from .schemas import GeneratorConfigUpdateRequest, GeneratorStatusResponse
from app.core.services import service_manager
from app.core.broadcaster import broadcaster

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post('/start')
async def start_generator(
    tps: float = Query(2.0, ge=0.1, le=200.0),
    fraud_injection_rate: float = Query(0.3, ge=0.0, le=1.0),
) -> Any:
    try:
        gen = service_manager.get_generator()
        gen.update_config(tps=tps, fraud_injection_rate=fraud_injection_rate)
        gen.start()
        await broadcaster.broadcast(
            {
                "event_type": "generator_started",
                "tps": tps,
                "fraud_rate": fraud_injection_rate,
            }
        )
        return {
            'message': 'Generator started successfully',
            'tps': tps,
            'fraud_rate': fraud_injection_rate,
        }
    except Exception as e:
        logger.error(f'Error starting generator: {e}', exc_info=True)
        raise HTTPException(status_code=500, detail='Internal server error')


@router.post('/stop')
async def stop_generator() -> Any:
    try:
        gen = service_manager.get_generator()
        gen.stop()
        await broadcaster.broadcast(
            {
                "event_type": "generator_stopped",
            }
        )
        return {'message': 'Generator stopped successfully'}
    except Exception as e:
        logger.error(f'Error stopping generator: {e}', exc_info=True)
        raise HTTPException(status_code=500, detail='Internal server error')


@router.get('/status', response_model=GeneratorStatusResponse)
async def get_generator_status() -> Any:
    try:
        gen = service_manager.get_generator()
        status_info = gen.status()
        return GeneratorStatusResponse(
            is_running=status_info.is_running,
            current_tps=status_info.current_tps,
            fraud_rate=gen.fraud_injection_rate,
            queue_depth=status_info.queue_depth,
            active_scenarios=gen.active_scenarios,
        )
    except Exception as e:
        logger.error(f'Error fetching generator status: {e}', exc_info=True)
        raise HTTPException(status_code=500, detail='Internal server error')


@router.patch('/config')
async def update_generator_config(config: GeneratorConfigUpdateRequest) -> Any:
    try:
        gen = service_manager.get_generator()
        gen.update_config(
            tps=config.tps,
            fraud_injection_rate=config.fraud_injection_rate,
            active_scenarios=config.active_scenarios,
        )
        return {'message': 'Configuration updated successfully'}
    except Exception as e:
        logger.error(f'Error updating generator config: {e}', exc_info=True)
        raise HTTPException(status_code=500, detail='Internal server error')
