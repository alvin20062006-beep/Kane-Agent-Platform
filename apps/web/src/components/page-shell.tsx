import type { ReactNode } from "react";

type Props = {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
};

export function WorkPage({ title, subtitle, actions, children }: Props) {
  return (
    <div className="flex h-full min-h-0 w-full flex-col">
      {(title || actions) && (
        <header className="flex items-center justify-between border-b border-[var(--kane-border)] bg-[rgba(255,248,238,0.88)] px-[var(--kane-page-pad-x)] py-4">
          <div className="min-w-0">
            {title && (
              <div className="kane-page-title truncate">
                {title}
              </div>
            )}
            {subtitle && (
              <div className="kane-page-subtitle truncate">{subtitle}</div>
            )}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="min-h-0 flex-1 overflow-auto">{children}</div>
    </div>
  );
}

export function ReadPage({ title, subtitle, actions, children }: Props) {
  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-auto">
      <div className="mx-auto w-full max-w-4xl px-[var(--kane-page-pad-x)] py-[var(--kane-page-pad-y)]">
        {(title || actions) && (
          <header className="kane-page-header flex items-center justify-between">
            <div>
              {title && <h1 className="kane-page-title">{title}</h1>}
              {subtitle && <p className="kane-page-subtitle">{subtitle}</p>}
            </div>
            {actions && <div className="flex items-center gap-2">{actions}</div>}
          </header>
        )}
        {children}
      </div>
    </div>
  );
}
