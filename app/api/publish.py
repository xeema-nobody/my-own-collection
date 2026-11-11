from fastapi import APIRouter, HTTPException, Query

from app.api.deps import get_db
from app.db.models import PublishConfirmIn, PublishResultIn
from app.services import publish_queue as svc

router = APIRouter(prefix="/api/publish", tags=["publish"])


async def _run(coro):
    try:
        return await coro
    except svc.QueueError as e:
        raise HTTPException(e.status, str(e))


@router.post("/confirm", status_code=201)
async def confirm(body: PublishConfirmIn):
    """The user's per-item confirmation in the Publish table: these items may be published by the Claude session."""
    return await svc.confirm(get_db(), body)


@router.get("/queue")
async def queue(state: list[str] | None = Query(None), item_id: str | None = Query(None, max_length=40)):
    if state and any(s not in svc.STATES for s in state):
        raise HTTPException(422, f"state must be one of {', '.join(svc.STATES)}")
    return await svc.list_queue(get_db(), state, item_id=item_id)


@router.post("/queue/next")
async def next_item():
    """Claim the oldest confirmed item (-> publishing) and write its photos to publish_tmp/<id>/. Null when empty."""
    return await _run(svc.claim_next(get_db()))


@router.post("/queue/{qid}/result")
async def result(qid: str, body: PublishResultIn):
    return await _run(svc.report(get_db(), qid, body))


@router.post("/queue/{qid}/release")
async def release(qid: str):
    return await _run(svc.release(get_db(), qid))


@router.post("/queue/{qid}/cancel")
async def cancel(qid: str):
    return await _run(svc.cancel(get_db(), qid))


@router.post("/queue/{qid}/retry")
async def retry(qid: str):
    return await _run(svc.retry(get_db(), qid))
