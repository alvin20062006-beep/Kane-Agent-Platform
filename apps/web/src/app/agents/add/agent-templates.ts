import type { Agent } from "@/lib/octopus-types";

export type AddTemplate = {
  id: string;
  title: string;
  summary: string;
  honesty: string;
  defaults: {
    display_name: string;
    type: Agent["type"];
    adapter_id: string;
    integration_mode: NonNullable<Agent["integration_mode"]>;
    integration_channels: string[];
    control_depth: NonNullable<Agent["control_depth"]>;
    capabilities: Record<string, boolean>;
    control_plane: NonNullable<Agent["control_plane"]>;
  };
};

export const ADD_TEMPLATES: AddTemplate[] = [
  {
    id: "openclaw",
    title: "OpenClaw",
    summary: "经 Local Bridge 转发；若配置 OPENCLAW_WEBHOOK_URL 可走 HTTP，否则生成 handoff 文件。",
    honesty:
      "接入方式：External。通道：Bridge + Webhook + Handoff + Callback。控制深度：Partial（依赖对端 Webhook 行为）。",
    defaults: {
      display_name: "OpenClaw（自定义）",
      type: "external",
      adapter_id: "openclaw_http",
      integration_mode: "external",
      integration_channels: ["bridge", "webhook", "handoff", "callback"],
      control_depth: "partial",
      capabilities: {
        can_chat: true,
        can_code: false,
        can_browse: true,
        can_use_skills: false,
        can_stream: true,
        supports_structured_task: true,
        supports_handoff: true,
        supports_callback: true,
      },
      control_plane: {
        webhook_url: "",
        callback_public_base_url: "",
        working_directory: "",
      },
    },
  },
  {
    id: "cursor",
    title: "Cursor",
    summary:
      "闭源 IDE：平台生成 handoff，用户在 Cursor 内执行后通过 callback 回收结果。无保证无头全自动。",
    honesty:
      "接入方式：External。通道：Bridge + Handoff + Callback。控制深度：Assisted（非正式适配接口，不能宣称 Full control）。",
    defaults: {
      display_name: "Cursor（自定义）",
      type: "external",
      adapter_id: "cursor_cli",
      integration_mode: "external",
      integration_channels: ["bridge", "handoff", "callback"],
      control_depth: "assisted",
      capabilities: {
        can_chat: false,
        can_code: true,
        can_browse: false,
        can_use_skills: false,
        can_run_local_commands: true,
        supports_structured_task: true,
        supports_handoff: true,
        supports_callback: true,
      },
      control_plane: {
        cli_path: "",
        callback_public_base_url: "",
        working_directory: "",
      },
    },
  },
  {
    id: "claude_code",
    title: "Claude Code",
    summary:
      "闭源产品：若本机存在 claude CLI 可由 Bridge 同步执行；否则生成 handoff + callback 说明。",
    honesty:
      "接入方式：External / CLI-bridged。通道：Bridge + CLI + Handoff + Callback。控制深度：Partial（取决于 CLI 是否可用）。",
    defaults: {
      display_name: "Claude Code（自定义）",
      type: "external",
      adapter_id: "claude_code",
      integration_mode: "external",
      integration_channels: ["bridge", "cli", "handoff", "callback"],
      control_depth: "partial",
      capabilities: {
        can_chat: false,
        can_code: true,
        can_browse: false,
        can_use_skills: false,
        can_run_local_commands: true,
        supports_structured_task: true,
        supports_handoff: true,
        supports_callback: true,
      },
      control_plane: {
        cli_path: "",
        callback_public_base_url: "",
        working_directory: "",
      },
    },
  },
  {
    id: "local_script",
    title: "本地脚本 Agent",
    summary:
      "在 Bridge 主机上执行 shell 命令（Embedded on Bridge host）。需填写 shell_command。",
    honesty:
      "接入方式：Embedded（由 Bridge 执行命令）。通道：Bridge + Shell。控制深度：Partial（安全与超时由 Bridge 进程承担）。",
    defaults: {
      display_name: "本地脚本（自定义）",
      type: "external",
      adapter_id: "local_script",
      integration_mode: "embedded",
      integration_channels: ["bridge", "shell"],
      control_depth: "partial",
      capabilities: {
        can_chat: false,
        can_code: false,
        can_browse: false,
        can_use_skills: false,
        can_run_local_commands: true,
        supports_structured_task: true,
      },
      control_plane: {
        shell_command: "echo octopus-local-script-ok",
        working_directory: "",
        env: {},
      },
    },
  },
];
