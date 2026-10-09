import type { ButtonHTMLAttributes, ReactNode } from "react";
import { useRef } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { FolderOpen, X } from "lucide-react";
import { desktopInvoke } from "../desktop";
export function Button({
  variant = "secondary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "quiet" | "danger";
}) {
  return (
    <button
      type="button"
      className={`button button-${variant} ${className}`}
      {...props}
    />
  );
}
export function PathField({
  label,
  value,
  field,
  disabled,
  onChange,
  onCommit,
  onError,
}: {
  label: string;
  value: string;
  field: string;
  disabled: boolean;
  onChange: (value: string) => void;
  onCommit: (value: string) => Promise<void>;
  onError: (message: string) => void;
}) {
  const choose = async () => {
    try {
      const value = await desktopInvoke<string | null>("choose_path", {
        field,
        initial: valueProp,
      });
      if (value !== null) {
        onChange(value);
        await onCommit(value);
      }
    } catch (error) {
      onError(String(error));
    }
  };
  const valueProp = value;
  return (
    <div className="field">
      <label htmlFor={field}>{label}</label>
      <div className="path-control">
        <input
          id={field}
          type="text"
          value={value}
          disabled={disabled}
          placeholder="Choose a folder"
          spellCheck={false}
          onChange={(event) => onChange(event.target.value)}
          onBlur={() => {
            void onCommit(value).catch(() => {});
          }}
          title={value}
        />
        <Button
          disabled={disabled}
          onClick={() => void choose()}
          aria-label={`Browse ${label.toLowerCase()}`}
        >
          <FolderOpen size={17} />
          Browse
        </Button>
      </div>
    </div>
  );
}
export function CheckField({
  label,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="check-field">
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span>{label}</span>
    </label>
  );
}
export function Section({
  title,
  children,
  actions,
}: {
  title: string;
  children: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section className="form-section" aria-label={title}>
      <div className="section-heading">
        <h2>{title}</h2>
        {actions && <div className="section-actions">{actions}</div>}
      </div>
      {children}
    </section>
  );
}
export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  children: ReactNode;
  footer: ReactNode;
}) {
  const returnFocus = useRef<HTMLElement | null>(null);
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content
          className="dialog-content"
          onOpenAutoFocus={() => {
            returnFocus.current = document.activeElement as HTMLElement;
          }}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            returnFocus.current?.focus();
          }}
        >
          <div className="dialog-heading">
            <Dialog.Title>{title}</Dialog.Title>
            <Dialog.Close asChild>
              <Button
                variant="quiet"
                className="icon-button"
                aria-label="Close dialog"
              >
                <X size={20} />
              </Button>
            </Dialog.Close>
          </div>
          <Dialog.Description className="dialog-description">
            {description}
          </Dialog.Description>
          <div className="dialog-body">{children}</div>
          <div className="dialog-footer">{footer}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
