/**
 * Spec 34 — render + behaviour tests for the branded-auth controls.
 *
 * These exercise the Clerk-free presentational pieces and the cooldown hook
 * (the parts that don't require a live Clerk client): the OAuth gate rendering,
 * the error alert, the OTP input's typing/paste/auto-submit behaviour, and the
 * resend cooldown timer.
 */
import {
  act,
  fireEvent,
  render,
  renderHook,
  screen,
} from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ErrorAlert,
  OAuthRow,
  OtpInput,
  useResendCooldown,
} from "./auth-fields.cloud";

describe("OAuthRow (gated)", () => {
  it("renders nothing while OAUTH_PROVIDERS is empty (v1 default)", () => {
    const { container } = render(<OAuthRow onSelect={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("ErrorAlert", () => {
  it("renders nothing without a message", () => {
    const { container } = render(<ErrorAlert message={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders an ARIA alert with the themed message", () => {
    render(<ErrorAlert message="That password is incorrect." />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("That password is incorrect.");
  });
});

/** A controlled wrapper so the OTP input behaves as it does in a flow. */
function ControlledOtp({
  onComplete,
}: {
  onComplete?: (code: string) => void;
}) {
  const [value, setValue] = useState("");
  return <OtpInput value={value} onChange={setValue} onComplete={onComplete} />;
}

describe("OtpInput", () => {
  it("exposes six individually-labelled digit boxes in a labelled group", () => {
    render(<ControlledOtp />);
    expect(
      screen.getByRole("group", { name: "Verification code" }),
    ).toBeTruthy();
    for (let i = 1; i <= 6; i += 1) {
      expect(screen.getByLabelText(`Digit ${i}`)).toBeTruthy();
    }
  });

  it("fires onComplete once all six digits are present (auto-submit)", () => {
    const onComplete = vi.fn();
    render(<ControlledOtp onComplete={onComplete} />);
    const boxes = Array.from({ length: 6 }, (_, i) =>
      screen.getByLabelText(`Digit ${i + 1}`),
    );
    for (let i = 0; i < 6; i += 1) {
      fireEvent.change(boxes[i], { target: { value: String(i + 1) } });
    }
    expect(onComplete).toHaveBeenCalledWith("123456");
  });

  it("fills all boxes from a pasted 6-digit code", () => {
    const onComplete = vi.fn();
    render(<ControlledOtp onComplete={onComplete} />);
    const first = screen.getByLabelText("Digit 1");
    fireEvent.paste(first, {
      clipboardData: { getData: () => "987654" },
    });
    expect(onComplete).toHaveBeenCalledWith("987654");
    expect(screen.getByLabelText<HTMLInputElement>("Digit 6").value).toBe("4");
  });

  it("ignores non-numeric input", () => {
    const onComplete = vi.fn();
    render(<ControlledOtp onComplete={onComplete} />);
    fireEvent.change(screen.getByLabelText("Digit 1"), {
      target: { value: "a" },
    });
    expect(screen.getByLabelText<HTMLInputElement>("Digit 1").value).toBe("");
    expect(onComplete).not.toHaveBeenCalled();
  });
});

describe("useResendCooldown", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("starts idle (ready to send)", () => {
    const { result } = renderHook(() => useResendCooldown(30));
    expect(result.current.remaining).toBe(0);
    expect(result.current.isCoolingDown).toBe(false);
  });

  it("counts down once per second and clears at zero", () => {
    const { result } = renderHook(() => useResendCooldown(3));
    act(() => result.current.start());
    expect(result.current.remaining).toBe(3);
    expect(result.current.isCoolingDown).toBe(true);

    act(() => void vi.advanceTimersByTime(1000));
    expect(result.current.remaining).toBe(2);
    act(() => void vi.advanceTimersByTime(2000));
    expect(result.current.remaining).toBe(0);
    expect(result.current.isCoolingDown).toBe(false);
  });

  it("re-arming restarts the full countdown", () => {
    const { result } = renderHook(() => useResendCooldown(5));
    act(() => result.current.start());
    act(() => void vi.advanceTimersByTime(2000));
    expect(result.current.remaining).toBe(3);
    act(() => result.current.start());
    expect(result.current.remaining).toBe(5);
  });
});
