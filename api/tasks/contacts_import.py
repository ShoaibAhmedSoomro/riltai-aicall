from api.services.contacts.import_service import run_contact_import


async def process_contact_import(_ctx, import_uuid: str) -> None:
    """ARQ entry point. The work, and its failure handling, are in the service."""
    await run_contact_import(import_uuid)
