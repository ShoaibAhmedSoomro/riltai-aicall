"""Social-Cangaroo-specific subclasses of pipecat realtime LLM services.

Each subclass wires Social Cangaroo engine integration quirks (user-mute gating,
TTSSpeakFrame greeting trigger, node-transition handling, function-call
deferral, etc.) onto the corresponding pipecat realtime service.

The pipecat fork's services stay close to upstream — Social Cangaroo behavior lives
here.
"""
