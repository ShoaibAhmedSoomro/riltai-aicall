import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const preview = vi.fn();
const startImport = vi.fn();
const startSuppressionImport = vi.fn();
const getImport = vi.fn();
const getReportUrl = vi.fn();
const createList = vi.fn();

vi.mock('@/client/sdk.gen', () => ({
    previewImportApiV1ContactsImportPreviewGet: (...a: unknown[]) => preview(...a),
    importContactsApiV1ContactsImportPost: (...a: unknown[]) => startImport(...a),
    importSuppressionsApiV1ContactsSuppressionsImportPost: (...a: unknown[]) => startSuppressionImport(...a),
    getImportApiV1ContactsImportsImportUuidGet: (...a: unknown[]) => getImport(...a),
    getImportErrorReportUrlApiV1ContactsImportsImportUuidErrorReportUrlGet: (...a: unknown[]) => getReportUrl(...a),
    createContactListApiV1ContactsListsPost: (...a: unknown[]) => createList(...a),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
// The real selector uploads to storage; here it is just "a file was chosen".
vi.mock('@/app/campaigns/CsvUploadSelector', () => ({
    default: ({ onFileUploaded }: { onFileUploaded: (k: string, n: string) => void }) => (
        <button onClick={() => onFileUploaded('campaigns/7/abc/people.csv', 'people.csv')}>choose file</button>
    ),
}));

import { ContactImportDialog } from './ContactImportDialog';

const PREVIEW = {
    headers: ['First Name', 'Mobile', 'Email', 'Employer'],
    rows: [['Ana', '+971501111111', 'ana@x.co', 'Acme']],
};

function renderDialog(mode: 'contacts' | 'suppression' = 'contacts') {
    const onDone = vi.fn();
    render(<ContactImportDialog open onOpenChange={() => undefined} onDone={onDone} lists={[]} mode={mode} />);
    return onDone;
}

async function reachMapping() {
    fireEvent.click(screen.getByText('choose file'));
    await screen.findByRole('button', { name: 'Import' });
}

beforeEach(() => {
    vi.clearAllMocks();
    preview.mockResolvedValue({ data: PREVIEW });
    startImport.mockResolvedValue({ data: { import_uuid: 'imp-1', status: 'pending', mode: 'contacts' } });
    getImport.mockResolvedValue({
        data: { import_uuid: 'imp-1', status: 'completed', created_count: 5, updated_count: 0, skipped_count: 1, invalid_count: 2, has_error_report: true },
    });
});

describe('ContactImportDialog', () => {
    it('opens the mapping step with the obvious columns already chosen, and sends exactly that', async () => {
        renderDialog();
        await reachMapping();

        fireEvent.click(screen.getByRole('button', { name: 'Import' }));

        await waitFor(() => expect(startImport).toHaveBeenCalledTimes(1));
        const body = startImport.mock.calls[0][0].body;
        expect(body.source_key).toBe('campaigns/7/abc/people.csv');
        expect(body.dedupe_strategy).toBe('skip');
        expect(body.column_mapping).toMatchObject({
            phone_number: 'Mobile',
            first_name: 'First Name',
            last_name: null,
            email: 'Email',
            // the leftover column is offered as a custom field, named safely
            attributes: { employer: 'Employer' },
        });
    });

    it('a column can be left out of the custom fields', async () => {
        renderDialog();
        await reachMapping();

        fireEvent.click(screen.getByRole('checkbox', { name: 'Keep Employer' }));
        fireEvent.click(screen.getByRole('button', { name: 'Import' }));

        await waitFor(() => expect(startImport).toHaveBeenCalled());
        expect(startImport.mock.calls[0][0].body.column_mapping.attributes).toEqual({});
    });

    it('will not start while a custom field name is unusable', async () => {
        renderDialog();
        await reachMapping();

        fireEvent.change(screen.getByLabelText('Field name for Employer'), { target: { value: 'email' } });

        expect((screen.getByRole('button', { name: 'Import' }) as HTMLButtonElement).disabled).toBe(true);
        expect(screen.getByText(/standard field/i)).toBeDefined();
    });

    it('reports the outcome and offers the rejected rows', async () => {
        const onDone = renderDialog();
        await reachMapping();
        fireEvent.click(screen.getByRole('button', { name: 'Import' }));

        await screen.findByText('Import complete', {}, { timeout: 5000 });
        expect(screen.getByText('5 new · 1 already existed · 2 rejected')).toBeDefined();
        expect(screen.getByRole('button', { name: /Download the 2 rejected rows/ })).toBeDefined();

        getReportUrl.mockResolvedValue({ data: { url: 'https://files.example/errors.csv' } });
        const open = vi.spyOn(window, 'open').mockReturnValue(null);
        fireEvent.click(screen.getByRole('button', { name: /Download the 2 rejected rows/ }));
        await waitFor(() => expect(open).toHaveBeenCalledWith('https://files.example/errors.csv', '_blank', 'noopener'));

        fireEvent.click(screen.getByRole('button', { name: 'Done' }));
        expect(onDone).toHaveBeenCalled();
    });

    it('shows why an import failed instead of a blank success', async () => {
        getImport.mockResolvedValue({
            data: { import_uuid: 'imp-1', status: 'failed', processing_error: 'Column "Telephone" (phone number) is not in the file' },
        });
        renderDialog();
        await reachMapping();
        fireEvent.click(screen.getByRole('button', { name: 'Import' }));

        await screen.findByText('Import failed', {}, { timeout: 5000 });
        expect(screen.getByText(/Telephone/)).toBeDefined();
    });

    it('says so when the file cannot be read', async () => {
        preview.mockResolvedValue({ error: { detail: 'The file is empty' } });
        renderDialog();
        fireEvent.click(screen.getByText('choose file'));
        await screen.findByText('The file is empty');
        expect(screen.queryByRole('button', { name: 'Import' })).toBeNull();
    });

    it('the do-not-call mode asks only for the number column and uses its own endpoint', async () => {
        startSuppressionImport.mockResolvedValue({ data: { import_uuid: 'imp-2', status: 'pending', mode: 'suppression' } });
        renderDialog('suppression');
        fireEvent.click(screen.getByText('choose file'));
        await screen.findByRole('button', { name: 'Add to do-not-call list' });

        expect(screen.queryByText('First name')).toBeNull();
        fireEvent.click(screen.getByRole('button', { name: 'Add to do-not-call list' }));

        await waitFor(() => expect(startSuppressionImport).toHaveBeenCalled());
        expect(startSuppressionImport.mock.calls[0][0].body).toMatchObject({ phone_column: 'Mobile' });
        expect(startImport).not.toHaveBeenCalled();
    });
});
