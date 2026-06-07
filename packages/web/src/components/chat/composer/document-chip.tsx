/**
 * F5 T07 (D-F5-X-document-primitives-f2-promotion) — strangler-fig re-export shim.
 *
 * The canonical source-of-truth moved to
 * `packages/web/src/components/ui/document-chip.tsx` per F2 promotion
 * convention (D-F5-X-document-primitives-f2-promotion = 11th additive-
 * precedent chain entry). This shim preserves the existing F3-local
 * import paths so F3 + chat composer consumers see no churn during the
 * strangler-fig transition.
 *
 * Removable when all in-repo imports migrate to `@/components/ui/document-chip`
 * (no urgency — the shim cost is one re-export line).
 */
export {
  DocumentChip,
  type DocumentChipProps,
} from "@/components/ui/document-chip";
