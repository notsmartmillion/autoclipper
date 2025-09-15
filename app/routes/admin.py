from fastapi import APIRouter
router = APIRouter(prefix="/admin")

@router.post("/rescan")
def rescan():
    from app.workers.tasks import poll_creators
    poll_creators.delay()
    return {"ok": True}

@router.get("/creators")
def list_creators():
    # return allowlist + db status
    pass
