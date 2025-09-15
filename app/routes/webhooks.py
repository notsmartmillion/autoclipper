from fastapi import APIRouter

router = APIRouter(prefix="/webhooks")


@router.post("/youtube/processing-complete")
def yt_processing_complete():
    return {"ok": True}
