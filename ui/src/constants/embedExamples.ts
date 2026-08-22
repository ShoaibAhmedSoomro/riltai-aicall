export const HEADLESS_CHAT_EXAMPLE = `let chatState = 'idle';

function withSocialCangarooWidget(callback) {
  if (window.SocialCangarooWidget) {
    callback(window.SocialCangarooWidget);
    return;
  }

  const script = document.getElementById('social-cangaroo-widget');
  if (!script) {
    console.error('Social Cangaroo embed script not found');
    return;
  }

  script.addEventListener('load', () => {
    if (window.SocialCangarooWidget) callback(window.SocialCangarooWidget);
  }, { once: true });
}

withSocialCangarooWidget((widget) => {
  widget.onChatStateChange((state) => {
    chatState = state; // idle | starting | ready | waiting | ended | expired | error
  });

  widget.onMessage((text, turn) => {
    appendAgentBubble(text); // render however you want
  });

  document.getElementById('open-chat').addEventListener('click', () => {
    widget.startChat();
  });

  document.getElementById('send-btn').addEventListener('click', async () => {
    const input = document.getElementById('chat-input');
    appendVisitorBubble(input.value);
    const transcript = await widget.sendMessage(input.value);
    if (transcript !== null) input.value = '';
  });

  document.getElementById('end-chat')?.addEventListener('click', async () => {
    await widget.endChat();
  });
});`;
