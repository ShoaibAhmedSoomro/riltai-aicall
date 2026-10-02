import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const getTopic = vi.hoisted(() => vi.fn());

vi.mock('@/client/sdk.gen', () => ({
    getPromptingGuideTopicApiV1PromptingGuideTopicIdGet: getTopic,
}));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));

import { SinglePromptEditor } from './SinglePromptEditor';

const base = { prompt: 'You are a helpful agent.', greeting: 'Hello!', greetingIsAudio: false };

function setup(over: Partial<React.ComponentProps<typeof SinglePromptEditor>> = {}) {
    const onChange = vi.fn();
    const onSwitchToFlow = vi.fn();
    render(
        <SinglePromptEditor
            values={base}
            onChange={onChange}
            recordings={[]}
            readOnly={false}
            onSwitchToFlow={onSwitchToFlow}
            {...over}
        />,
    );
    return { onChange, onSwitchToFlow };
}

beforeEach(() => getTopic.mockReset());

describe('SinglePromptEditor', () => {
    it('shows the prompt and greeting of the start node', () => {
        setup();
        expect((screen.getByLabelText('Greeting') as HTMLInputElement).value).toBe('Hello!');
        expect(screen.getByDisplayValue('You are a helpful agent.')).toBeDefined();
    });

    it('writes edits back as a patch to the one field that changed', () => {
        const { onChange } = setup();
        fireEvent.change(screen.getByLabelText('Greeting'), { target: { value: 'Hi there' } });
        expect(onChange).toHaveBeenCalledWith({ greeting: 'Hi there' });
        fireEvent.change(screen.getByDisplayValue('You are a helpful agent.'), { target: { value: 'New prompt' } });
        expect(onChange).toHaveBeenCalledWith({ prompt: 'New prompt' });
    });

    it('offers the way out to the flow editor', () => {
        const { onSwitchToFlow } = setup();
        fireEvent.click(screen.getByRole('button', { name: /switch to the flow editor/i }));
        expect(onSwitchToFlow).toHaveBeenCalledTimes(1);
    });

    it('does not let a text edit overwrite an audio greeting', () => {
        setup({ values: { ...base, greetingIsAudio: true } });
        expect((screen.getByLabelText('Greeting') as HTMLInputElement).disabled).toBe(true);
    });

    it('is read-only on a historical version: no handbook button, edits ignored', () => {
        const { onChange } = setup({ readOnly: true });
        expect(screen.queryByRole('button', { name: /insert starter handbook/i })).toBeNull();
        expect((screen.getByLabelText('Greeting') as HTMLInputElement).disabled).toBe(true);
        fireEvent.change(screen.getByDisplayValue('You are a helpful agent.'), { target: { value: 'x' } });
        expect(onChange).not.toHaveBeenCalled();
    });

    it('adds the handbook after what is written, fetched from the server', async () => {
        getTopic.mockResolvedValue({ data: { starter_template: '#goal\nStarter' } });
        const { onChange } = setup();
        fireEvent.click(screen.getByRole('button', { name: /insert starter handbook/i }));
        await waitFor(() => expect(onChange).toHaveBeenCalled());
        expect(getTopic).toHaveBeenCalledWith({ path: { topic_id: 'common_guidelines' } });
        expect(onChange).toHaveBeenCalledWith({ prompt: 'You are a helpful agent.\n\n#goal\nStarter' });
    });

    it('leaves the prompt alone when the handbook cannot be loaded', async () => {
        getTopic.mockResolvedValue({ error: { detail: 'nope' } });
        const { onChange } = setup();
        fireEvent.click(screen.getByRole('button', { name: /insert starter handbook/i }));
        await waitFor(() => expect(getTopic).toHaveBeenCalled());
        expect(onChange).not.toHaveBeenCalled();
    });
});
