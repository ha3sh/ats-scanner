// Hand-written API types for the report and error envelope.
// Replaced by generated types from the OpenAPI document on Day 8.

export type ExtractionWarningCode = "columns_suspected";

export type ExtractionWarning = {
  code: ExtractionWarningCode;
  message: string;
  page: number | null;
};

export type ReadingOrder = "row" | "column";

export type SectionName =
  | "contact"
  | "summary"
  | "experience"
  | "education"
  | "skills"
  | "projects"
  | "certifications";

export type SectionFinding = {
  name: SectionName;
  found: boolean;
  heading: string | null;
  page: number | null;
  line: number | null;
};

export type ContactItem = {
  found: boolean;
  value: string | null;
  page: number | null;
  line: number | null;
};

export type ContactInfo = {
  email: ContactItem;
  phone: ContactItem;
  linkedin: ContactItem;
};

export type BlockKind = "requirements" | "preferred" | "responsibilities" | "other";

export type RemovalReason =
  | "equal_opportunity"
  | "benefits"
  | "about_company"
  | "how_to_apply";

export type KeptBlock = {
  text: string;
  start_line: number;
  kind: BlockKind;
};

export type RemovedBlock = {
  text: string;
  start_line: number;
  reason: RemovalReason;
};

export type CleanedJd = {
  kept: KeptBlock[];
  removed: RemovedBlock[];
};

export type SkillCategory =
  | "language"
  | "framework"
  | "library"
  | "database"
  | "cloud"
  | "devops"
  | "data"
  | "testing"
  | "practice"
  | "tool";

export type JdTerm = {
  canonical: string;
  category: SkillCategory;
  weight: number;
  required: boolean;
  occurrences: number;
  surface: string;
  line: number;
  context: string;
};

export type JdAnalysis = {
  cleaned: CleanedJd;
  terms: JdTerm[];
};

export type ResumeSpan = {
  page: number;
  line: number;
  start_char: number;
  end_char: number;
  section: SectionName | null;
};

export type MatchedTerm = {
  term: string;
  canonical: string;
  weight: number;
  jd_context: string;
  resume_context: string;
  resume_span: ResumeSpan;
};

export type MissingTerm = {
  term: string;
  weight: number;
  jd_context: string;
};

export type NearMiss = {
  term: string;
  found_variant: string;
  distance: number;
  counted: false;
};

export type TermAnalysis = {
  matched: MatchedTerm[];
  missing: MissingTerm[];
  near_misses: NearMiss[];
};

export type CoveragePart = {
  covered: number;
  total: number;
};

export type CoverageScore = {
  covered_weight: number;
  total_weight: number;
  pct: number;
  required: CoveragePart;
  other: CoveragePart;
  definition: string;
  state: "terms" | "no_terms";
};

export type AlignmentStatus = "aligned" | "differs" | "unknown";

export type JdEvidence = {
  text: string | null;
  line: number | null;
};

export type ResumeEvidence = {
  text: string | null;
  page: number | null;
  line: number | null;
};

export type AlignmentCheck = {
  status: AlignmentStatus;
  jd_evidence: JdEvidence;
  resume_evidence: ResumeEvidence;
};

export type Alignment = {
  title: AlignmentCheck;
  seniority: AlignmentCheck;
  experience: AlignmentCheck;
};

export type ReportMeta = {
  filename: string;
  size_bytes: number;
  page_count: number;
  method: string;
  duration_ms: number;
  warnings: ExtractionWarning[];
};

export type ExtractedTextPage = {
  page_number: number;
  row_text: string;
  column_text: string | null;
};

export type ExtractedText = {
  pages: ExtractedTextPage[];
  char_count: number;
  method: string;
  warnings: ExtractionWarning[];
};

export type AnalysisReport = {
  schema_version: number;
  engine_version: string;
  dictionary_version: number;
  meta: ReportMeta;
  extracted_text: ExtractedText;
  reading_order: ReadingOrder[];
  sections: SectionFinding[];
  contact: ContactInfo;
  jd: JdAnalysis;
  terms: TermAnalysis;
  score: CoverageScore;
  alignment: Alignment;
};

export type ErrorEnvelope = {
  code: string;
  message: string;
};

export type Health = {
  version: string;
  engine_version: string;
  dictionary_version: number;
  limits: {
    max_file_bytes: number;
    max_pages: number;
    max_jd_chars: number;
    min_jd_chars: number;
  };
};
