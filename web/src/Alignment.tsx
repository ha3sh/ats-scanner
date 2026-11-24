import type {
  Alignment as AlignmentReport,
  AlignmentCheck,
  AlignmentStatus,
} from "./api/types";

const STATUS_TEXT: Record<AlignmentStatus, string> = {
  aligned: "Aligned",
  differs: "Differs",
  unknown: "Not enough information",
};

const STATUS_SYMBOL: Record<AlignmentStatus, string> = {
  aligned: "✓",
  differs: "≠",
  unknown: "–",
};

const STATUS_CLASS: Record<AlignmentStatus, string> = {
  aligned: "text-teal",
  differs: "text-ink",
  unknown: "text-muted",
};

// Informational comparison only: statuses are written out and symbols repeat
// them for quick scanning; no state implies a verdict or a coverage figure.
export default function Alignment({ alignment }: { alignment: AlignmentReport }) {
  const rows: { label: string; check: AlignmentCheck }[] = [
    { label: "Title", check: alignment.title },
    { label: "Seniority", check: alignment.seniority },
    { label: "Experience", check: alignment.experience },
  ];

  return (
    <section className="mt-10 border-t border-rule pt-10" aria-labelledby="alignment-heading">
      <h2
        id="alignment-heading"
        className="font-serif text-2xl font-semibold text-ink"
      >
        Alignment
      </h2>
      <p className="mt-1 text-sm italic text-muted">
        Informational only. Alignment never changes the coverage figure.
      </p>

      <ul className="mt-6 list-none space-y-3">
        {rows.map(({ label, check }) => (
          <li key={label} className="rounded-sm border border-rule bg-paper p-3">
            <p className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm">
              <span className="font-semibold text-ink">{label}</span>
              <span aria-hidden="true" className={STATUS_CLASS[check.status]}>
                {STATUS_SYMBOL[check.status]}
              </span>
              <span className={STATUS_CLASS[check.status]}>
                {STATUS_TEXT[check.status]}
              </span>
            </p>
            <div className="mt-2 grid gap-2 min-[700px]:grid-cols-2">
              <Evidence
                label="JD evidence"
                text={check.jd_evidence.text}
                where={
                  check.jd_evidence.line === null
                    ? null
                    : `line ${check.jd_evidence.line}`
                }
              />
              <Evidence
                label="Resume evidence"
                text={check.resume_evidence.text}
                where={
                  check.resume_evidence.page === null ||
                  check.resume_evidence.line === null
                    ? null
                    : `page ${check.resume_evidence.page}, line ${check.resume_evidence.line}`
                }
              />
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Evidence({
  label,
  text,
  where,
}: {
  label: string;
  text: string | null;
  where: string | null;
}) {
  const location = where === null ? "no clear location" : where;
  return (
    <p className="text-sm text-muted [overflow-wrap:anywhere]">
      <span className="font-medium text-ink">{label}</span>
      {` — ${location}`}
      {text === null ? "." : `: ${text}`}
    </p>
  );
}
