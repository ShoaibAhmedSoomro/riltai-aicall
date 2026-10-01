import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/context/UnsavedChangesContext', () => ({ useUnsavedChanges: () => undefined }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import {
    DEFAULT_GOVERNANCE_CONFIGURATION,
    resolveWorkflowConfigurations,
    type WorkflowConfigurations,
} from '@/types/workflow-configurations';

import { GovernanceSection } from './GovernanceSection';

const onSave = vi.fn().mockResolvedValue(undefined);

function renderWith(governance: Partial<WorkflowConfigurations['governance_configuration']> = {}) {
    const configs = resolveWorkflowConfigurations({
        governance_configuration: { ...DEFAULT_GOVERNANCE_CONFIGURATION, ...governance },
    } as Partial<WorkflowConfigurations>);
    render(<GovernanceSection workflowConfigurations={configs} workflowName="Agent" onSave={onSave} />);
    return configs;
}

const saveButton = () => screen.getByRole('button', { name: /Save Data & Safety/i }) as HTMLButtonElement;

beforeEach(() => onSave.mockClear());

describe('GovernanceSection', () => {
    it('starts clean: nothing to save, and the defaults keep everything', () => {
        renderWith();
        expect(saveButton().disabled).toBe(true);
        expect(screen.getByLabelText(/Record the call audio/i).getAttribute('aria-checked')).toBe('true');
        expect(screen.getByLabelText(/Save the transcript/i).getAttribute('aria-checked')).toBe('true');
    });

    it('saves a change inside governance_configuration and leaves the rest of the config alone', () => {
        const configs = renderWith();
        fireEvent.click(screen.getByLabelText(/Record the call audio/i));
        expect(saveButton().disabled).toBe(false);

        fireEvent.click(saveButton());

        const saved = onSave.mock.calls[0][0] as WorkflowConfigurations;
        expect(saved.governance_configuration.record_audio).toBe(false);
        expect(saved.governance_configuration.store_transcript).toBe(true);
        expect(saved.max_call_duration).toBe(configs.max_call_duration);
        expect(onSave.mock.calls[0][1]).toBe('Agent');
    });

    it('basic-only shows both switches off and locks them, rather than letting them disagree', () => {
        renderWith({ storage_mode: 'basic_only' });
        const audio = screen.getByLabelText(/Record the call audio/i) as HTMLButtonElement;
        const transcript = screen.getByLabelText(/Save the transcript/i) as HTMLButtonElement;
        expect(audio.getAttribute('aria-checked')).toBe('false');
        expect(transcript.getAttribute('aria-checked')).toBe('false');
        expect(audio.disabled && transcript.disabled).toBe(true);
    });

    it('a ticked personal-detail kind is saved', () => {
        renderWith();
        fireEvent.click(screen.getByRole('checkbox', { name: /Email addresses/i }));
        fireEvent.click(saveButton());
        expect(
            (onSave.mock.calls[0][0] as WorkflowConfigurations).governance_configuration.redaction_categories,
        ).toEqual(['email']);
    });

    it('only asks what to do about an override attempt once the check is on', () => {
        renderWith();
        expect(screen.queryByText(/When one is caught/i)).toBeNull();
        fireEvent.click(screen.getByLabelText(/Catch callers trying to override/i));
        expect(screen.getByText(/When one is caught/i)).toBeDefined();
    });

    it('is honest that the agent replies are reviewed after the call, not blocked live', () => {
        renderWith();
        expect(screen.getByText(/not held back while the call is running/i)).toBeDefined();
    });
});

describe('resolveWorkflowConfigurations', () => {
    it('fills the governance block from defaults for an agent saved before it existed', () => {
        const c = resolveWorkflowConfigurations({ max_call_duration: 120 } as Partial<WorkflowConfigurations>);
        expect(c.governance_configuration).toEqual(DEFAULT_GOVERNANCE_CONFIGURATION);
    });

    it('merges the nested guardrails instead of replacing them', () => {
        const c = resolveWorkflowConfigurations({
            governance_configuration: { guardrails: { input_jailbreak: true } },
        } as unknown as Partial<WorkflowConfigurations>);
        expect(c.governance_configuration.guardrails).toEqual({
            input_jailbreak: true,
            output_categories: [],
            on_violation: 'log_only',
        });
    });
});
