import type { CoverageScore, SectionName, TermAnalysis } from "./api/types";

const SECTION_LABELS: Record<SectionName, string> = {
  contact: "Contact",
  summary: "Summary",
  experience: "Experience",
  education: "Education",
  skills: "Skills",
  projects: "Projects",
  certifications: "Certifications",
};

// The coverage headline and the term ledger. Symbols repeat the state in text,
// never colour alone; missing and near-match rows stay neutral.
export default function Coverage({
  score,
  terms,
}: {
  score: CoverageScore;
  terms: TermAnalysis;
}) {
  const caption =
    `Required terms: ${score.required.covered} of ${score.required.total} · ` +
    `Other terms: ${score.other.covered} of ${score.other.total} · ` +
    "required terms count double.";

  return (
    <section className="mt-10 border-t border-rule pt-10" aria-labelledby="coverage-heading">
      <h2
        id="coverage-heading"
        className="font-serif text-2xl font-semibold text-ink"
      >
        Job description coverage
      </h2>

      <div className="mt-6 grid gap-6 min-[700px]:grid-cols-2">
        <div>
          {score.state === "no_terms" ? (
            <p className="text-sm text-ink [overflow-wrap:anywhere]">
              No dictionary terms were found in the job description
            </p>
          ) : (
            <>
              <p className="font-serif text-4xl font-semibold text-ink">
                {score.pct}%
              </p>
              <div
                aria-hidden="true"
                className="mt-3 h-2 w-full overflow-hidden rounded-sm bg-paper-dim"
              >
                <div className="h-full bg-teal" style={{ width: `${score.pct}%` }} />
              </div>
              <p className="mt-1 text-xs text-muted">Weighted term coverage</p>
            </>
          )}
        </div>
        <div className="rounded-sm border border-rule bg-paper-dim p-3 text-sm text-ink [overflow-wrap:anywhere]">
          <p className="font-medium">How the figure is calculated</p>
          <p className="mt-1">{score.definition}</p>
        </div>
      </div>

      <p className="mt-3 text-sm text-muted [overflow-wrap:anywhere]">{caption}</p>

      <div className="mt-8 grid gap-8 min-[900px]:grid-cols-2">
        <div>
          <h3 className="font-semibold text-ink">Matched</h3>
          {terms.matched.length === 0 ? (
            <p className="mt-2 text-sm text-muted">No matched terms.</p>
          ) : (
            <ul className="mt-2 list-none space-y-3">
              {terms.matched.map((item) => {
                const section =
                  item.resume_span.section === null
                    ? "section not identified"
                    : SECTION_LABELS[item.resume_span.section];
                const where =
                  section +
                  ` · page ${item.resume_span.page}, line ${item.resume_span.line}`;
                return (
                  <li
                    key={`${item.term}-${item.resume_span.page}-${item.resume_span.line}-${item.resume_span.start_char}`}
                    className="rounded-sm border border-rule bg-paper p-3"
                  >
                    <p className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm text-ink">
                      <span aria-hidden="true" className="text-teal">
                        ✓
                      </span>
                      <span className="font-medium [overflow-wrap:anywhere]">
                        {item.term}
                      </span>
                      <span className="text-xs text-muted">
                        weight {item.weight.toFixed(1)}
                      </span>
                    </p>
                    <p className="mt-1 text-xs text-muted [overflow-wrap:anywhere]">
                      {where}
                    </p>
                    <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-ink [overflow-wrap:anywhere]">
                      {item.resume_context}
                    </p>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div>
          <h3 className="font-semibold text-ink">Missing</h3>
          {terms.missing.length === 0 ? (
            <p className="mt-2 text-sm text-muted">No missing terms.</p>
          ) : (
            <ul className="mt-2 list-none space-y-3">
              {terms.missing.map((item) => (
                <li
                  key={item.term}
                  className="rounded-sm border border-rule bg-paper-dim p-3"
                >
                  <p className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm text-ink">
                    <span aria-hidden="true" className="text-muted">
                      –
                    </span>
                    <span className="font-medium [overflow-wrap:anywhere]">
                      {item.term}
                    </span>
                    <span className="text-xs text-muted">
                      weight {item.weight.toFixed(1)}
                    </span>
                  </p>
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-muted [overflow-wrap:anywhere]">
                    {item.jd_context}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="mt-8">
        <h3 className="font-semibold text-ink">Near matches</h3>
        {terms.near_misses.length === 0 ? (
          <p className="mt-2 text-sm text-muted">No near matches.</p>
        ) : (
          <ul className="mt-2 grid list-none gap-3 min-[900px]:grid-cols-2">
            {terms.near_misses.map((item) => (
              <li
                key={item.term}
                className="rounded-sm border border-rule bg-paper p-3 text-sm text-ink [overflow-wrap:anywhere]"
              >
                <p className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <span aria-hidden="true" className="text-muted">
                    ≈
                  </span>
                  <span className="font-medium text-muted">
                    possible match, not counted
                  </span>
                </p>
                <p className="mt-1">
                  {item.term} → {item.found_variant} · distance {item.distance}
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
