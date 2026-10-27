# File: backend/app/presentation/api/bulk_composition.py
from app.application.bulk_import_review import BulkReviewService
from app.application.bulk_import_settlement import BulkImportSettlement
from app.application.use_cases.create_bulk_batch_job import CreateBulkBatchJobUseCase
from app.application.use_cases.preview_bulk_batch_job import PreviewBulkBatchJobUseCase

_preview = _create = _review = _settlement = None


def configure_bulk_services(uow_factory, connections):
    global _preview, _create, _review, _settlement
    _preview = PreviewBulkBatchJobUseCase(uow_factory, connections)
    _create = CreateBulkBatchJobUseCase(uow_factory, connections)
    _review = BulkReviewService(uow_factory, connections)
    _settlement = BulkImportSettlement(_create)
    return _review


def get_bulk_preview():
    if _preview is None:
        raise RuntimeError("Bulk services are not configured")
    return _preview


def get_bulk_create():
    if _create is None:
        raise RuntimeError("Bulk services are not configured")
    return _create


def get_bulk_review():
    if _review is None:
        raise RuntimeError("Bulk services are not configured")
    return _review


def get_bulk_settlement():
    if _settlement is None:
        raise RuntimeError("Bulk services are not configured")
    return _settlement


async def shutdown_bulk_imports():
    if _settlement is not None:
        await _settlement.shutdown()
