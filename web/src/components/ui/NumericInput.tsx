"use client";

import { useRef, type ChangeEvent, type InputHTMLAttributes } from "react";

type NumericInputProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "type" | "value" | "onChange" | "inputMode" | "pattern"
> & {
  value: string | number;
  onValueChange: (value: string) => void;
  integer?: boolean;
};

/** Keyboard-first numeric entry with decimal-safe paste and caret preservation. */
export default function NumericInput({
  value,
  onValueChange,
  integer = false,
  ...props
}: NumericInputProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  const validateBounds = (element: HTMLInputElement) => {
    const value = element.value.trim();
    const min = props.min === undefined ? undefined : Number(props.min);
    const max = props.max === undefined ? undefined : Number(props.max);
    const numeric = value === "" ? undefined : Number(value);
    let message = "";
    if (numeric !== undefined && !Number.isFinite(numeric)) message = "Enter a valid number.";
    else if (numeric !== undefined && min !== undefined && numeric < min) message = `Enter a value of at least ${min}.`;
    else if (numeric !== undefined && max !== undefined && numeric > max) message = `Enter a value no greater than ${max}.`;
    element.setCustomValidity(message);
  };

  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    const input = event.currentTarget;
    const raw = input.value;
    const caret = input.selectionStart ?? raw.length;
    const prefix = raw.slice(0, caret);
    let normalized = raw.replace(/[^0-9.]/g, "");
    if (integer) normalized = normalized.replace(/\./g, "");
    else {
      const dot = normalized.indexOf(".");
      if (dot >= 0) normalized = normalized.slice(0, dot + 1) + normalized.slice(dot + 1).replace(/\./g, "");
    }
    const safePrefix = prefix.replace(/[^0-9.]/g, "");
    const dotIndex = safePrefix.indexOf(".");
    const nextCaret = integer || dotIndex < 0
      ? safePrefix.replace(/\./g, "").length
      : safePrefix.slice(0, dotIndex + 1).length + safePrefix.slice(dotIndex + 1).replace(/\./g, "").length;
    onValueChange(normalized);
    requestAnimationFrame(() => {
      const element = inputRef.current;
      if (!element) return;
      element.setSelectionRange(nextCaret, nextCaret);
    });
  };

  return (
    <input
      {...props}
      ref={inputRef}
      type="text"
      inputMode={integer ? "numeric" : "decimal"}
      pattern={integer ? "[0-9]*" : "[0-9]*([.][0-9]*)?"}
      value={value}
      onChange={handleChange}
      onInput={(event) => validateBounds(event.currentTarget)}
      onBlur={(event) => {
        validateBounds(event.currentTarget);
        props.onBlur?.(event);
      }}
      onWheel={(event) => event.currentTarget.blur()}
    />
  );
}
