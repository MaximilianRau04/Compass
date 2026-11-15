from fastapi import APIRouter, Response

from app.api.deps import SessionDep
from app.services import export
from app.services.clock import local_today

router = APIRouter(prefix="/export", tags=["export"])


@router.get("", response_class=Response)
def export_all(session: SessionDep) -> Response:
    """Everything as a zip with a JSON file per table; secrets and raw health records stay out."""
    name = f"compass-export-{local_today().isoformat()}.zip"
    return Response(
        export.export_zip(session),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
