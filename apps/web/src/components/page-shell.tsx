import type { ReactNode } from "react";

type Props = {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
};

/**
 * WorkPage — 铺满可用宽度的工作型页（对话、操控舱、任务、Agents、技能）。
 * 不强制 max-width，左右少内边距，子内容自然撑开。
 */
export function WorkPage({ title, subtitle, actions, children }: Props) {
  return (
    <div className="flex h-full min-h-0 w-full flex-col">
      {(title || actions) && (
        <header className="flex items-center justify-between border-b border-zinc-200 bg-white px-4 py-2.5">
          <div className="min-w-0">
            {title && (
              <div className="truncate text-sm font-semibold text-zinc-800">{title}</div>
            )}
            {subtitle && (
              <div className="truncate text-xs text-zinc-500">{subtitle}</div>
            )}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="flex-1 min-h-0 overflow-auto">{children}</div>
    </div>
  );
}

/**
 * ReadPage — 文档型页（设置里的通用/关于、help markdown），保留可读宽度。
 */
export function ReadPage({ title, subtitle, actions, children }: Props) {
  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-auto">
      <div className="mx-auto w-full max-w-4xl px-6 py-6">
        {(title || actions) && (
          <header className="mb-4 flex items-center justify-between">
            <div>
              {title && <h1 className="text-xl font-semibold">{title}</h1>}
              {subtitle && <p className="mt-1 text-sm text-zinc-500">{subtitle}</p>}
            </div>
            {actions && <div className="flex items-center gap-2">{actions}</div>}
          </header>
        )}
        {children}
      </div>
    </div>
  );
}
