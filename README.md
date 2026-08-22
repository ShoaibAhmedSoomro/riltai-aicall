# Social Cangaroo AI

<p align="center">
  <a href="https://www.producthunt.com/products/social-cangaroo">
    <img src="https://img.shields.io/badge/Product%20Hunt-%231%20Product%20of%20the%20Day-DA552F?style=for-the-badge&logo=producthunt&logoColor=white" alt="Social Cangaroo: #1 Product of the Day on Product Hunt">
  </a>
</p>

**The open-source, self-hostable alternative to Vapi & Retell** — build production voice agents with a visual workflow builder, test them in minutes, and let AI coding assistants help design and edit them through MCP.

<p align="center">
  <a href="https://app.socialcangaroo.com">
    <img src="https://img.shields.io/badge/▶_Try_the_Cloud-app.socialcangaroo.com-2563eb?style=for-the-badge" alt="Try the Cloud">
  </a>
  &nbsp;
  <a href="#-get-started">
    <img src="https://img.shields.io/badge/⚡_Self--host_in_60s-One_command-111827?style=for-the-badge" alt="Self-host in 60s">
  </a>
  &nbsp;
  <a href="https://join.slack.com/t/social-cangaroo-community/shared_invite/zt-4787daqcn-3TDiQUh~3xrr3pwAqR9wpQ">
    <img src="https://img.shields.io/badge/💬_Join_Slack-Community-4A154B?style=for-the-badge&logo=slack" alt="Join Slack">
  </a>
</p>

<p align="center">
  <a href="https://docs.socialcangaroo.com">📖 Docs</a> &nbsp;·&nbsp;
  <a href="LICENSE">📜 BSD 2-Clause</a> &nbsp;·&nbsp;
  <a href="README.zh-CN.md">🌐 中文</a> &nbsp;·&nbsp;
  <a href="README.ja-JP.md">🌐 日本語</a>
</p>

<p align="center">
  <img src="docs/images/hero.gif" alt="Social Cangaroo in action — build a workflow, launch a voice agent, talk to it" width="80%">
</p>

- **100% open source**, self-hostable — no vendor lock-in, unlike Vapi or Retell
- **Full control & transparency** — every line of code is open, with flexible LLM / TTS / STT integration
- **Maintained by YC alumni and exit founders**, committed to keeping voice AI open

<p align="center">
  <a href="https://www.producthunt.com/products/social-cangaroo?embed=true&utm_source=badge-top-post-badge&utm_medium=badge&utm_campaign=badge-social-cangaroo-3" target="_blank"><img src="https://api.producthunt.com/widgets/embed-image/v1/top-post-badge.svg?post_id=1217382&theme=light&period=daily&t=1786607298379" alt="Social Cangaroo - The open source VAPI alternative | Product Hunt" width="250" height="54"></a>
  &nbsp;
  <a href="https://trendshift.io/repositories/31007" target="_blank"><img src="https://trendshift.io/api/badge/repositories/31007" alt="ShoaibAhmedSoomro%2Fsocial-cangaroo | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>
  <br />
  <a href="https://www.producthunt.com/products/social-cangaroo?embed=true&utm_source=badge-top-post-badge&utm_medium=badge&utm_campaign=badge-social-cangaroo-3" target="_blank"><img src="https://api.producthunt.com/widgets/embed-image/v1/top-post-badge.svg?post_id=1217382&theme=light&period=weekly&t=1786966826740" alt="Social Cangaroo - The open source VAPI alternative | Product Hunt" width="250" height="54"></a>
  &nbsp;
  <a href="https://www.producthunt.com/products/social-cangaroo?embed=true&utm_source=badge-top-post-topic-badge&utm_medium=badge&utm_campaign=badge-social-cangaroo-3" target="_blank"><img src="https://api.producthunt.com/widgets/embed-image/v1/top-post-topic-badge.svg?post_id=1217382&theme=neutral&period=weekly&topic_id=267&t=1786969133488" alt="Social Cangaroo - The open source VAPI alternative | Product Hunt" width="250" height="54"></a>
</p>

## 🎥 Featured

<div align="center">
  <a href="https://www.youtube.com/watch?v=xD9JEvfCH9k">
    <img src="https://img.youtube.com/vi/xD9JEvfCH9k/maxresdefault.jpg" alt="Social Cangaroo featured by Better Stack" width="80%" style="border-radius: 8px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
  </a>
  <br>
  <em>Featured by <strong>Better Stack</strong> — a hands-on look at Social Cangaroo</em>
</div>

<details>
<summary>📺 Prefer a 2-minute product walkthrough? Click here.</summary>

<div align="center">
  <a href="https://youtu.be/9gPneyf9M9w">
    <img src="docs/images/video_thumbnail_1.png" alt="Watch Social Cangaroo AI Demo Video" width="70%" style="border-radius: 8px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
  </a>
</div>

</details>

## ⚖️ Social Cangaroo vs Vapi vs Retell

An honest comparison on the axes that matter most to teams evaluating voice AI platforms.

|  | **Social Cangaroo** | **Vapi** | **Retell** |
|---|---|---|---|
| **License** | BSD 2-Clause (open source) | Proprietary | Proprietary |
| **Self-hostable** | ✅ Yes — one Docker command | ❌ SaaS only | ❌ SaaS only |
| **Pricing** | Free (self-host) · usage-based (cloud) | Per-minute SaaS | Per-minute SaaS |
| **Bring your own LLM / STT / TTS** | ✅ Any provider, or use Social Cangaroo's stack | Configurable within their integrations | Configurable within their integrations |
| **Source-level customization** | ✅ Every line is yours to modify | ❌ Closed source | ❌ Closed source |
| **Data residency** | Your infra, your rules | Their cloud | Their cloud |
| **Vendor lock-in** | None | Full | Full |


## 🚀 Get Started

##### Download and setup Social Cangaroo on your Local Machine

> **Note**
> We collect anonymous usage data to improve the product. You can opt out by setting `ENABLE_TELEMETRY=false` before running the startup script.

> **Note**
> If you wish to run the platform on a remote server instead, checkout our [Documentation](https://docs.socialcangaroo.com/deployment/docker#option-2:-remote-server-deployment)

```bash
curl -o docker-compose.yaml https://raw.githubusercontent.com/ShoaibAhmedSoomro/social-cangaroo/main/docker-compose.yaml && curl -o start_docker.sh https://raw.githubusercontent.com/ShoaibAhmedSoomro/social-cangaroo/main/scripts/start_docker.sh && chmod +x start_docker.sh && ./start_docker.sh
```

> **⚡ Prefer an AI agent to set it up for you?**
> If you use **Claude Code** or **Codex**, install the official [Social Cangaroo setup skill](https://github.com/ShoaibAhmedSoomro/social-cangaroo-plugins) and let your agent handle installation, configuration, and troubleshooting — it detects your OS, picks the right deploy path, runs Social Cangaroo's own setup scripts, and verifies the result.
>
> ```text
> # In Claude Code
> /plugin marketplace add ShoaibAhmedSoomro/social-cangaroo-plugins
> /plugin install social-cangaroo@social-cangaroo
> ```
>
> Then start a new session and ask it to _"set up Social Cangaroo"_ (or run `/social-cangaroo-setup`). Codex is supported too — see the [plugin repo](https://github.com/ShoaibAhmedSoomro/social-cangaroo-plugins#install).

> **Note**
> First startup may take 2-3 minutes to download all images. Once running, open http://localhost:3010 to create your first AI voice assistant!
> For common issues and solutions, see 🔧 **[Troubleshooting](docs/getting-started/troubleshooting.mdx)**.

### 🎙️ Your First Voice Bot

1. Open [http://localhost:3010](http://localhost:3010) in your browser.
2. Pick **Inbound** or **Outbound**, name your bot (e.g. _Lead Qualification_), and describe the use case in 5–10 words (e.g. _Screen insurance form submissions for purchase intent_).
3. Click **Test Agent**.
4. Use **Test Audio** to talk to your agent in the browser, or **Test Chat** to iterate faster in text. In Test Chat, you can edit or replay user turns and Social Cangaroo will regenerate the agent's replies and node transitions from that point.

> 🔑 **No API keys needed.** Social Cangaroo ships with auto-generated keys and its own LLM / TTS / STT stack. Connect your own keys for LLM, TTS, STT, or Telephony (e.g. Twilio, Vonage, Telnyx) anytime.

> **Featured On & Community Validation:** Social Cangaroo was named **[#1 Product of the Day on Product Hunt](https://www.producthunt.com/products/social-cangaroo)**.

## Build Agents with MCP

Social Cangaroo ships with an MCP server, so coding agents can work directly inside your Social Cangaroo workspace.

Connect Codex, Claude Code, Cursor, or any MCP client to inspect existing agents, search Social Cangaroo docs, fetch node schemas, create new workflows, and save draft edits from natural language.

When asking your coding agent to build a voice agent, share a short script for
the use case instead of only a one-line prompt. Include the agent persona, call
flow, rules, objection handling, success criteria, and a sample conversation if
you have one.

See the [MCP guide](https://docs.socialcangaroo.com/integrations/mcp) to connect your assistant.

## Features

### Voice Agent Builder

- Visual workflow builder with start nodes, agent nodes, global instructions, tools, transitions, and end-call outcomes
- Test Agent panel with **Test Audio** for browser voice testing and **Test Chat** for fast prompt iteration
- QA node, knowledge bases, webhooks, embeds, and tool calling for production workflows

### Voice & Telephony

- Built-in telephony integrations including Twilio, Vonage, Telnyx, Plivo, Vobiz, Cloudonix, and Asterisk ARI
- Human handoff with call transfer on supported telephony providers
- Bring your own LLM, TTS, STT, and telephony providers; store artifacts in bundled MinIO or AWS/S3-compatible storage

### Developer Experience

- One-command Docker setup for self-hosting
- Python backend and modular provider architecture for customization
- Python and Node SDKs for programmatic agent creation and outbound calls

## Deployment Options

### Local Development

Refer [Local Setup](https://docs.socialcangaroo.com/contribution/setup)

### Self-Hosted Deployment

For detailed deployment instructions including remote server setup with HTTPS, see our [Docker Deployment Guide](https://docs.socialcangaroo.com/deployment/docker#option-2-remote-server-deployment).

### Cloud Version

Visit [https://www.socialcangaroo.com](https://www.socialcangaroo.com/) for our managed cloud offering.

## 📚Documentation

You can go to [https://docs.socialcangaroo.com](https://docs.socialcangaroo.com/) for our documentation.

## 📦 SDKs

- **Python SDK** — [pypi.org/project/social-cangaroo-sdk](https://pypi.org/project/social-cangaroo-sdk/)
- **Node SDK** — [npmjs.com/package/@social-cangaroo/sdk](https://www.npmjs.com/package/@social-cangaroo/sdk)

## 🤝Community & Support

> 👋 **Coming from the Better Stack video?** Drop your use case in our [pinned GitHub Discussion](https://github.com/orgs/ShoaibAhmedSoomro/discussions/291) — we read every reply and the founders personally onboard early adopters.

- **Slack** — the cornerstone of Social Cangaroo AI contributions. Connect with maintainers, discuss features before coding, get help with setup, and stay current on contribution sprints.
- **GitHub Discussions** — share use cases, ask questions, swap workflow recipes.
- **GitHub Issues** — report bugs or request features.

👉 Join us → [Social Cangaroo Community Slack](https://join.slack.com/t/social-cangaroo-community/shared_invite/zt-4787daqcn-3TDiQUh~3xrr3pwAqR9wpQ)

## 🙌 Contributing

We love contributions! Social Cangaroo AI is 100% open source and we intend to keep it that way.

### Getting Started

- Fork the repository
- Create your feature branch (git checkout -b feature/AmazingFeature)
- Commit your changes (git commit -m 'Add some AmazingFeature')
- Push to the branch (git push origin feature/AmazingFeature)
- Open a Pull Request

## ⭐ Star History

<img src="docs/images/star-history.png" alt="Social Cangaroo star history" width="80%">

## 📄 License

Social Cangaroo AI is licensed under the [BSD 2-Clause License](LICENSE)- the same license as projects that were used in building Social Cangaroo AI, ensuring compatibility and freedom to use, modify, and distribute.

## 🏢 About

Built with ❤️ by **Social Cangaroo**
Founded by YC alumni and exit founders committed to keeping voice AI open and accessible to everyone.

<br><br><br>

  <p align="center">
    <a href="https://github.com/ShoaibAhmedSoomro/social-cangaroo">⭐ Star us on GitHub</a> |
    <a href="https://app.socialcangaroo.com">☁️ Try Cloud Version</a> |
    <a href="https://join.slack.com/t/social-cangaroo-community/shared_invite/zt-4787daqcn-3TDiQUh~3xrr3pwAqR9wpQ">💬 Join Slack</a>
  </p>
