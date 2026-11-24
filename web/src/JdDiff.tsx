import type { BlockKind, JdAnalysis, RemovalReason } from "./api/types";

const KIND_LABELS: Record<BlockKind, string> = {
  requirements: "Requirements",
  preferred: "Preferred",
  responsibilities: "Responsibilities",
  other: "Other",
};

const REASON_LABELS: Record<RemovalReason, string> = {
  equal_opportunity: "Equal opportunity",
  benefits: "Benefits",
  about_company: "About the company",
  how_to_apply: "How to apply",
};

// The JD view: kept blocks, removed boilerplate, and the dictionary terms that
// feed the coverage denominator. Text and aria-hidden symbols carry every
// state, so colour is never the only signal.
export default function JdDiff({ jd }: { jd: JdAnalysis }) {
  return (
    <section className="mt-10 border-t border-rule pt-10">
      <h2 className="font-serif text-2xl font-semibold text-ink">
        What was kept and removed from the job description
      </h2>
      <p className="mt-1 text-sm italic text-muted">
        Boilerplate is stripped before terms are counted, so the denominator is
        auditable.
      </p>

      <div className="mt-6 grid gap-6 min-[900px]:grid-cols-2">
        <div>
          <h3 className="font-semibold text-ink">Kept</h3>
          {jd.cleaned.kept.length === 0 ? (
            <p className="mt-2 text-sm text-muted">No blocks were kept.</p>
          ) : (
            <ul className="mt-3 list-none space-y-3">
              {jd.cleaned.kept.map((block) => (
                <li
                  key={`${block.start_line}-${block.kind}`}
                  className="rounded-sm border border-rule bg-paper p-3"
                >
                  <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                    <span className="inline-flex items-center gap-1 rounded-sm border border-teal px-1.5 py-0.5 font-medium text-ink">
                      <span aria-hidden="true" className="text-teal">
                        ✓
                      </span>
                      {KIND_LABELS[block.kind]}
                    </span>
                    <span>Line {block.start_line}</span>
                  </p>
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-ink [overflow-wrap:anywhere]">
                    {block.text}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <h3 className="font-semibold text-ink">Removed</h3>
          {jd.cleaned.removed.length === 0 ? (
            <p className="mt-2 text-sm text-muted">No boilerplate was removed.</p>
          ) : (
            <ul className="mt-3 list-none space-y-3">
              {jd.cleaned.removed.map((block) => (
                <li
                  key={`${block.start_line}-${block.reason}`}
                  className="rounded-sm border border-rule bg-paper-dim p-3 text-muted"
                >
                  <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                    <span className="inline-flex items-center gap-1 rounded-sm border border-muted px-1.5 py-0.5 font-medium">
                      <span aria-hidden="true">–</span>
                      {REASON_LABELS[block.reason]}
                    </span>
                    <span>Line {block.start_line}</span>
                  </p>
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed [overflow-wrap:anywhere]">
                    {block.text}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="mt-8">
        <h3 className="font-semibold text-ink">Terms</h3>
        {jd.terms.length === 0 ? (
          <p className="mt-2 text-sm text-muted">
            No dictionary terms were found in the kept text.
          </p>
        ) : (
          <ul className="mt-3 flex list-none flex-wrap gap-2">
            {jd.terms.map((term) => (
              <li
                key={term.canonical}
                className="inline-flex flex-wrap items-baseline gap-x-2 gap-y-1 rounded-sm border border-rule bg-paper px-2 py-1 text-sm text-ink"
              >
                <span aria-hidden="true" className="text-muted">
                  •
                </span>
                <span className="font-medium">{term.canonical}</span>
                <span className="text-xs text-muted">
                  weight {term.weight.toFixed(1)}
                </span>
                {term.required && (
                  <span className="inline-flex items-center gap-1 text-xs font-medium text-teal">
                    <span aria-hidden="true">★</span>
                    required
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
