/**
 * Unit tests for the framework-free branded-auth redirect targets.
 *
 * Guards the safe-path coercion (no open redirect) and the env-resolution that
 * fixes the post-sign-in / post-sign-up "lands on / not /personas" bug.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  DEFAULT_SIGN_IN_REDIRECT,
  DEFAULT_SIGN_UP_REDIRECT,
  safeRedirectPath,
  signInRedirectTarget,
  signUpRedirectTarget,
} from "./auth-redirect.cloud";

describe("safeRedirectPath", () => {
  it("returns the fallback for empty / whitespace / undefined", () => {
    expect(safeRedirectPath(undefined, "/personas")).toBe("/personas");
    expect(safeRedirectPath("", "/personas")).toBe("/personas");
    expect(safeRedirectPath("   ", "/personas")).toBe("/personas");
  });

  it("honours a same-origin absolute path", () => {
    expect(safeRedirectPath("/chat", "/personas")).toBe("/chat");
    expect(safeRedirectPath("  /runs  ", "/personas")).toBe("/runs");
  });

  it("rejects protocol-relative and absolute URLs (no open redirect)", () => {
    expect(safeRedirectPath("//evil.com", "/personas")).toBe("/personas");
    expect(safeRedirectPath("https://evil.com", "/personas")).toBe("/personas");
    expect(safeRedirectPath("javascript:alert(1)", "/personas")).toBe(
      "/personas",
    );
    // A path whose first segment carries a scheme-like colon is rejected too.
    expect(safeRedirectPath("/foo:bar", "/personas")).toBe("/personas");
  });

  it("rejects relative (non-absolute) paths", () => {
    expect(safeRedirectPath("personas", "/personas")).toBe("/personas");
  });
});

describe("env-resolved targets", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("defaults to /personas when the env override is unset", () => {
    vi.stubEnv("NEXT_PUBLIC_CLERK_SIGN_IN_FALLBACK_REDIRECT_URL", "");
    vi.stubEnv("NEXT_PUBLIC_CLERK_SIGN_UP_FALLBACK_REDIRECT_URL", "");
    expect(signInRedirectTarget()).toBe(DEFAULT_SIGN_IN_REDIRECT);
    expect(signUpRedirectTarget()).toBe(DEFAULT_SIGN_UP_REDIRECT);
    expect(DEFAULT_SIGN_IN_REDIRECT).toBe("/personas");
    expect(DEFAULT_SIGN_UP_REDIRECT).toBe("/personas");
  });

  it("honours a configured in-app override", () => {
    vi.stubEnv("NEXT_PUBLIC_CLERK_SIGN_IN_FALLBACK_REDIRECT_URL", "/chat");
    vi.stubEnv("NEXT_PUBLIC_CLERK_SIGN_UP_FALLBACK_REDIRECT_URL", "/runs");
    expect(signInRedirectTarget()).toBe("/chat");
    expect(signUpRedirectTarget()).toBe("/runs");
  });

  it("falls back when a configured override is unsafe", () => {
    vi.stubEnv(
      "NEXT_PUBLIC_CLERK_SIGN_IN_FALLBACK_REDIRECT_URL",
      "https://evil.com",
    );
    expect(signInRedirectTarget()).toBe("/personas");
  });
});
