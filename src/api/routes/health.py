from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health")
async def health(version: str = "unknown") -> JSONResponse:
    return JSONResponse({"status": "ok", "version": version})
