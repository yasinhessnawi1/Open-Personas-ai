"use client";

import Editor from "@monaco-editor/react";
import { useTheme } from "next-themes";

// Monaco wrapped for YAML (D-09-8). Default export so the parent can lazy-load it
// via `next/dynamic({ ssr: false })`, keeping Monaco off the chat-page bundle that
// Lighthouse #10 measures. @monaco-editor/react fetches Monaco from a CDN, so it
// adds nothing to our own bundle.
export default function YAMLEditor({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const { resolvedTheme } = useTheme();
  return (
    <div className="overflow-hidden rounded-md border">
      <Editor
        height="440px"
        language="yaml"
        value={value}
        onChange={(v) => onChange(v ?? "")}
        theme={resolvedTheme === "dark" ? "vs-dark" : "light"}
        options={{
          minimap: { enabled: false },
          fontSize: 13,
          fontFamily: "var(--font-geist-mono), ui-monospace, monospace",
          lineNumbers: "on",
          scrollBeyondLastLine: false,
          tabSize: 2,
          wordWrap: "on",
          padding: { top: 12, bottom: 12 },
          renderLineHighlight: "none",
        }}
      />
    </div>
  );
}
