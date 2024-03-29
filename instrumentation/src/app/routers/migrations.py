from fastapi import Depends
import sqlalchemy.ext.asyncio

from fastapi_laser import fastapi_ext

from app import app_config, deps
from app.database.migrations.cli import migration


router = fastapi_ext.get_router(dependencies=[Depends(deps.verify_sa_identity(app_config.functions_sa_email))])


@router.get("/upgrade/head")
def upgrade_head():
    migration.upgrade_head()


@router.get("/downgrade/{revision}")
def downgrade(revision: str):
    migration.downgrade(revision)


@router.get("/revisions/head")
def read_head_revision():
    return migration.head()


@router.get("/revisions/current")
async def read_current_revision(
    db_session: sqlalchemy.ext.asyncio.AsyncSession = Depends(deps.db_session),
):
    return await migration.current(db_session)


@router.get("/revisions/current/is-head")
async def is_current_revision_head(
    db_session: sqlalchemy.ext.asyncio.AsyncSession = Depends(deps.db_session),
):
    return await migration.is_current_head(db_session)


@router.get("/stamp/head")
def stamp_head_revision():
    migration.stamp_head()
