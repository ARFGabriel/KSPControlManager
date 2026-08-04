"""Point d'entree du backend Mission Control.

    python run.py
"""

import uvicorn

from ksp_mc.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "ksp_mc.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level="info",
    )
