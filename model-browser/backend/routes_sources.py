"""Routes that browse the sources: `GET /sources`, `GET /{source}/search`,
`GET /{source}/models/{id}`, `GET /{source}/models/{id}/nsfw-media` (PLAN.md §7.3).

Included by `backend/api.py` under `/api/plugins/model-browser`. Phase 1 fills this in.
"""

from fastapi import APIRouter

router = APIRouter()
