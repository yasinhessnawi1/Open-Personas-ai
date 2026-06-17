"use client";

import { ArrowRight, Quote } from "lucide-react";
import { useTranslations } from "next-intl";
import type { CSSProperties } from "react";
import { Stack } from "@/components/layout";
import {
  ACCENT_OKLCH,
  PERSONA_EXAMPLE_CATEGORIES,
  type PersonaExample,
  type PersonaExampleCategory,
} from "@/lib/persona-examples";
import { cn } from "@/lib/utils";

/**
 * Starter-persona gallery for the new-persona page.
 *
 * Replaces the prior three-line `example1..3` list. Picking a card hands its
 * `seed` to `onSelect` — the AuthorWizard writes it into the describe textarea,
 * so the existing author → review → create flow is untouched. This component is
 * presentation + a single callback; it never calls the API.
 *
 * Design (editorial-instrument, D-09-7): warm paper cards on the warm-paper
 * canvas, a per-category accent rail keyed to the four typed-memory store hues
 * (identity·teal / self_facts·green / worldview·indigo / episodic·rose) plus the
 * vermilion core. Calm motion only (staggered fade on load, token-resolved hover
 * lift); the global reduced-motion path (globals.css) zeroes durations.
 *
 * Color discipline (no-literals gate, D-F2-6): accent hues are pre-composed into
 * full OKLCH strings in JS and applied as inline `--accent` / `--accent-soft` /
 * `--accent-faint` custom properties. Class names reference them via
 * `bg-[var(--accent)]` etc. — `var(` does NOT trip the gate's color-literal
 * regex, and no `oklch(` literal appears in any class string.
 */

const CATEGORY_LABEL_KEY: Record<PersonaExampleCategory["id"], string> = {
  work: "gallery.categoryWork",
  learning: "gallery.categoryLearning",
  creative: "gallery.categoryCreative",
  wellness: "gallery.categoryWellness",
  experts: "gallery.categoryExperts",
  companionship: "gallery.categoryCompanionship",
};

/**
 * Pre-composed accent custom properties for a category. Three strengths cover
 * the rail/solid (`--accent`), the icon wash (`--accent-faint`, 12% alpha), and
 * the hover ring (`--accent-soft`, 40% alpha).
 */
function accentStyle(accent: PersonaExampleCategory["accent"]): CSSProperties {
  const { h, c, l } = ACCENT_OKLCH[accent];
  return {
    "--accent": `oklch(${l} ${c} ${h})`,
    "--accent-soft": `oklch(${l} ${c} ${h} / 0.4)`,
    "--accent-faint": `oklch(${l} ${c} ${h} / 0.12)`,
  } as CSSProperties;
}

export function ExampleGallery({
  onSelect,
  selectedId,
}: {
  /** Called with the chosen example when a card is picked. */
  onSelect: (example: PersonaExample) => void;
  /** Id of the most recently picked example, for the selected affordance. */
  selectedId?: string | null;
}) {
  const t = useTranslations("author");

  return (
    <section data-slot="example-gallery" aria-label={t("gallery.title")}>
      <Stack gap={8}>
        {PERSONA_EXAMPLE_CATEGORIES.map((category, categoryIndex) => (
          <CategorySection
            key={category.id}
            category={category}
            label={t(CATEGORY_LABEL_KEY[category.id])}
            useNamed={(name) => t("gallery.useNamed", { name })}
            selectedLabel={t("gallery.selected")}
            categoryIndex={categoryIndex}
            onSelect={onSelect}
            selectedId={selectedId}
          />
        ))}
      </Stack>
    </section>
  );
}

function CategorySection({
  category,
  label,
  useNamed,
  selectedLabel,
  categoryIndex,
  onSelect,
  selectedId,
}: {
  category: PersonaExampleCategory;
  label: string;
  useNamed: (name: string) => string;
  selectedLabel: string;
  categoryIndex: number;
  onSelect: (example: PersonaExample) => void;
  selectedId?: string | null;
}) {
  return (
    <div
      data-slot="example-category"
      style={accentStyle(category.accent)}
      className="flex flex-col gap-4"
    >
      <div className="flex items-center gap-3">
        <span
          aria-hidden="true"
          className="h-4 w-1 rounded-full bg-[var(--accent)]"
        />
        <h2 className="type-heading">{label}</h2>
      </div>
      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {category.examples.map((example, exampleIndex) => (
          <li key={example.id}>
            <ExampleCard
              example={example}
              useNamed={useNamed}
              selectedLabel={selectedLabel}
              isSelected={selectedId === example.id}
              // Stagger reveal across the page (capped) — calm load choreography.
              index={categoryIndex * 4 + exampleIndex}
              onSelect={onSelect}
            />
          </li>
        ))}
      </ul>
    </div>
  );
}

function ExampleCard({
  example,
  useNamed,
  selectedLabel,
  isSelected,
  index,
  onSelect,
}: {
  example: PersonaExample;
  useNamed: (name: string) => string;
  selectedLabel: string;
  isSelected: boolean;
  index: number;
  onSelect: (example: PersonaExample) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(example)}
      data-slot="example-card"
      data-selected={isSelected ? "true" : undefined}
      aria-label={useNamed(example.name)}
      // animation-delay is a motion knob, not a design color/size literal; the
      // global reduced-motion path zeroes animation duration so it stays inert.
      style={{ animationDelay: `${Math.min(index, 8) * 40}ms` }}
      className={cn(
        "motion-safe:fade-in-0 motion-safe:slide-in-from-bottom-1 group/example flex h-full w-full flex-col gap-3 rounded-xl bg-card p-4 text-left ring-1 ring-foreground/10 outline-none transition-[transform,box-shadow,border-color] duration-[var(--motion-duration-normal)] ease-[var(--motion-ease-emphasized)] motion-safe:animate-in",
        "hover:-translate-y-0.5 hover:shadow-[var(--elevation-2)] hover:ring-[var(--accent-soft)]",
        "focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        "data-[selected=true]:ring-2 data-[selected=true]:ring-[var(--accent)]",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="type-heading truncate leading-tight">{example.name}</p>
          <p className="type-ui truncate text-muted-foreground">
            {example.role}
          </p>
        </div>
        <span
          aria-hidden="true"
          className="grid size-8 shrink-0 place-items-center rounded-full bg-[var(--accent-faint)] text-[var(--accent)]"
        >
          <Quote className="size-3.5" />
        </span>
      </div>

      <p className="type-body text-foreground/80">{example.hook}</p>

      <p className="type-ui line-clamp-3 text-muted-foreground">
        {example.seed}
      </p>

      <span
        className={cn(
          "type-caption mt-auto inline-flex items-center gap-1.5 pt-1 font-mono uppercase",
          isSelected
            ? "text-[var(--accent)]"
            : "text-muted-foreground transition-colors group-hover/example:text-foreground",
        )}
        aria-hidden={isSelected ? undefined : "true"}
      >
        {isSelected ? (
          selectedLabel
        ) : (
          <ArrowRight className="size-3 transition-transform duration-[var(--motion-duration-fast)] group-hover/example:translate-x-0.5" />
        )}
      </span>
    </button>
  );
}
