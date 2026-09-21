from fastapi import APIRouter

router = APIRouter()


@router.get("/demo")
async def demo():
    return {"module": "demo", "status": "ok"}
