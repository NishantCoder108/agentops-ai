import type { FormEvent } from "react";

import Button from "../Button";

type Props = {
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
};

export default function ChatComposer({ value, disabled, onChange, onSubmit }: Props) {
  return (
    <form className="composer" onSubmit={onSubmit}>
      <label className="composer-label" htmlFor="chat-message">
        Message
      </label>
      <textarea
        id="chat-message"
        name="message"
        rows={3}
        maxLength={8000}
        placeholder="Ask about a policy, an order, or a calculation"
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            event.currentTarget.form?.requestSubmit();
          }
        }}
      />
      <Button type="submit" disabled={disabled || value.trim().length === 0}>
        Send
      </Button>
    </form>
  );
}
