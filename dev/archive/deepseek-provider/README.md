# DeepSeek

Adds **DeepSeek** to the Type list of **Admin → LLM / Assistant → Add configuration**, so the assistant and every LLM feature (prompt enhancement, chat, memory notes) can run on DeepSeek's hosted models.

Requires a PotionUI that lets plugins contribute LLM configuration types (the `llm_providers:` manifest section).

## Getting started

1. Enable the plugin in **Admin → Plugins**.
2. Open **Admin → LLM / Assistant → Add configuration** and pick the **DeepSeek** type. The Base URL fills in with `https://api.deepseek.com`.
3. Paste a DeepSeek API key (from the DeepSeek platform). It is stored encrypted, like any other configuration key.
4. Use the model picker to list the models your key can reach (`deepseek-flash`, `deepseek-v4-pro`), or type one.
5. Set **Max Tokens** to a few thousand or more: when DeepSeek thinks, its reasoning counts toward that limit.
6. **Test configuration**, then make it the default or assign it to users as usual.

The context window is read from DeepSeek's model listing, so you can leave that field blank.

## Settings

In **Admin → Plugins → DeepSeek → Settings**:

| Setting | Values | What it does |
|---|---|---|
| Thinking | Auto (default), Off | Auto lets DeepSeek reason before answering a request that offers no tools, and turns reasoning off as soon as tools are involved. Off never reasons. |
| Reasoning effort | Low, High (default), Max | How hard DeepSeek reasons when it does. |

Turn on **Show thinking to users** in the configuration to show the reasoning above the reply.

## Limits worth knowing

- **No reasoning in tool conversations.** When a request carries tools, DeepSeek wants the reasoning of every earlier turn sent back to it, and refuses the request otherwise. PotionUI's assistant does not keep that reasoning, so the plugin turns thinking off whenever tools are offered or the conversation already holds tool calls. Most assistant turns offer tools, so the assistant mostly answers without reasoning; tool-free features still reason.
- **No per-configuration option section.** The OpenAI-specific options (Top-P, penalties, seed, reasoning effort) do not show for this type; the plugin settings above cover thinking. DeepSeek ignores temperature while it thinks.
- **Images.** Leave **Supports Vision** off unless the model you chose accepts images.
- **Disabling the plugin** keeps your DeepSeek configurations, but they stop working ("Unsupported LLM type") until it is enabled again.
